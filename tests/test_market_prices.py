from datetime import date

import pandas as pd
import pytest
import requests

from gridsense import config
from gridsense.data import build, entsoe
from gridsense.schemas import PRICES_HOURLY, WEATHER_FC


def price_xml(points, *, curve="A03", currency="EUR", resolution="PT15M"):
    entries = "".join(
        f"<Point><position>{position}</position><price.amount>{price}</price.amount></Point>"
        for position, price in points
    )
    return f"""
    <Publication_MarketDocument xmlns="urn:test">
      <mRID>example</mRID><revisionNumber>1</revisionNumber><type>A44</type>
      <createdDateTime>2025-09-30T12:00Z</createdDateTime>
      <TimeSeries>
        <in_Domain.mRID>{config.BIDDING_ZONE}</in_Domain.mRID>
        <out_Domain.mRID>{config.BIDDING_ZONE}</out_Domain.mRID>
        <contract_MarketAgreement.type>A01</contract_MarketAgreement.type>
        <currency_Unit.name>{currency}</currency_Unit.name>
        <price_Measure_Unit.name>MWH</price_Measure_Unit.name>
        <curveType>{curve}</curveType>
        <Period>
          <timeInterval><start>2025-09-30T22:00Z</start><end>2025-09-30T23:00Z</end></timeInterval>
          <resolution>{resolution}</resolution>
          {entries}
        </Period>
      </TimeSeries>
    </Publication_MarketDocument>
    """.encode()


def native_from_xml(payload):
    return entsoe.normalize_native(entsoe.parse_price_xml(payload, "sample.xml"), "entsoe_api")


def test_variable_blocks_and_hourly_schema():
    native = native_from_xml(price_xml([(1, -10), (3, 20)]))
    assert native["price_eur_mwh"].tolist() == [-10, -10, 20, 20]
    assert native["interval_end_utc"].iloc[-1] == pd.Timestamp("2025-09-30T23:00Z")
    hourly = entsoe.to_hourly(native)
    assert hourly.dtypes.astype(str).to_dict() == PRICES_HOURLY
    assert hourly.loc[0, ["price_mean", "price_min", "price_max"]].tolist() == [5, -10, 20]

    # A contract-level smoke test until the archived weather pipeline is implemented.
    weather = pd.DataFrame({"target_ts_utc": hourly["ts_utc"].astype(WEATHER_FC["target_ts_utc"])})
    joined = weather.merge(hourly, left_on="target_ts_utc", right_on="ts_utc", validate="m:1")
    assert joined["price_mean"].tolist() == [5]


def test_missing_fixed_interval_excludes_hour():
    native = native_from_xml(price_xml([(1, -10), (3, 20), (4, 0)], curve="A01"))
    hourly = entsoe.to_hourly(native)
    start = pd.Timestamp("2025-09-30T22:00Z")
    report = build.price_coverage(native, hourly, start, start + pd.Timedelta(hours=2))
    assert report["missing_native_intervals"] == 5
    assert report["missing_hours"] == 2
    assert report["incomplete_hours"] == 1


@pytest.mark.parametrize(
    ("payload", "error"),
    [
        (price_xml([(1, 1)], currency="RON"), "EUR/MWh"),
        (price_xml([(1, "NaN")]), "finite"),
        (price_xml([(1, "bad")]), "could not convert"),
        (price_xml([(1, 1), (1, 2)]), "Duplicate"),
        (price_xml([(2, 1)]), "no initial block"),
        (price_xml([(1, 1)], resolution="PT60M"), "Unexpected market resolution"),
        (price_xml([(1, 1)]).replace(b"22:00Z", b"22:00"), "timezone-aware"),
        (b"<Acknowledgement_MarketDocument/>", "did not return an A44"),
    ],
)
def test_rejects_invalid_data(payload, error):
    with pytest.raises(ValueError, match=error):
        native_from_xml(payload)


def test_overlapping_intervals_fail_even_if_prices_match():
    native = native_from_xml(price_xml([(1, 1)]))
    duplicate = pd.concat([native, native], ignore_index=True).sort_values("ts_utc")
    with pytest.raises(ValueError, match="Duplicate market interval"):
        entsoe.to_hourly(duplicate)


@pytest.mark.parametrize(
    ("day", "hours", "resolution"),
    [(date(2025, 3, 30), 23, "PT60M"), (date(2025, 10, 26), 25, "PT15M")],
)
def test_dst_delivery_days(day, hours, resolution):
    start = build.local_midnight(day)
    end = build.local_midnight(day + pd.Timedelta(days=1))
    step = entsoe.RESOLUTIONS[resolution]
    ts = pd.date_range(start, end, freq=step, inclusive="left")
    native = pd.DataFrame(
        {"ts_utc": ts, "resolution": resolution, "price_eur_mwh": -1, "interval_end_utc": ts + step}
    )
    hourly = entsoe.to_hourly(native)
    report = build.price_coverage(native, hourly, start, end)
    assert report["expected_hours"] == report["negative_hours"] == hours
    assert report["missing_native_intervals"] == 0


def test_http_failure_is_retried_without_exposing_token(tmp_path, monkeypatch):
    monkeypatch.setattr(entsoe.time, "sleep", lambda seconds: None)
    calls = []

    def fail(url, **kwargs):
        calls.append(url)
        raise requests.Timeout(f"{url}?securityToken=secret")

    path = tmp_path / "prices.xml"
    with requests.Session() as session:
        monkeypatch.setattr(session, "get", fail)
        with pytest.raises(ValueError, match="Download failed for prices.xml: Timeout") as error:
            entsoe.download(session, entsoe.API_URL, path, params={"securityToken": "secret"})
    assert len(calls) == 3
    assert "secret" not in str(error.value)
    assert not path.exists()


def test_api_reads_cached_xml_and_clips_returned_period(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "RAW_DIR", tmp_path)
    path = tmp_path / "entsoe_prices/api/20250930T2200Z_20250930T2300Z.xml"
    path.parent.mkdir(parents=True)
    # Query window contains the first hour of a two-hour source period.
    path.write_bytes(
        price_xml([(1, -1), (5, 20)]).replace(b"2025-09-30T23:00Z", b"2025-10-01T00:00Z")
    )
    start = pd.Timestamp("2025-09-30T22:00Z")
    native = entsoe.fetch_day_ahead_prices(start, start + pd.Timedelta(hours=1))
    assert len(native) == 4
    assert native["price_eur_mwh"].eq(-1).all()


def test_cli_gap_policy(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(config, "PROCESSED_DIR", tmp_path)
    monkeypatch.setattr(config, "DATA_MODE", "real")
    native = native_from_xml(price_xml([(1, -1)]))
    monkeypatch.setattr(build, "fetch_snapshot_prices", lambda start, end: native)
    args = ["--source", "snapshot", "--start", "2025-10-01", "--end", "2025-10-01"]

    with pytest.raises(SystemExit) as error:
        build.main(args)
    assert error.value.code == 1
    assert "Incomplete price coverage" in capsys.readouterr().err
    assert not list(tmp_path.iterdir())

    build.main([*args, "--allow-gaps"])
    assert (tmp_path / "prices_hourly.parquet").is_file()
    assert (tmp_path / "prices_quality.json").is_file()


def test_cli_refuses_to_replace_existing_data_without_explicit_opt_in(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(config, "PROCESSED_DIR", tmp_path)
    monkeypatch.setattr(config, "DATA_MODE", "real")
    first = native_from_xml(price_xml([(1, -1)]))
    replacement = native_from_xml(price_xml([(1, 20)]))
    monkeypatch.setattr(build, "fetch_snapshot_prices", lambda start, end: first)
    args = ["--source", "snapshot", "--start", "2025-10-01", "--end", "2025-10-01", "--allow-gaps"]
    build.main(args)
    before = {p.name: p.read_bytes() for p in tmp_path.iterdir()}

    monkeypatch.setattr(build, "fetch_snapshot_prices", lambda start, end: replacement)
    with pytest.raises(SystemExit) as error:
        build.main(args)
    assert error.value.code == 1
    assert "differs from the new build" in capsys.readouterr().err
    assert {p.name: p.read_bytes() for p in tmp_path.iterdir()} == before

    build.main([*args, "--replace-existing"])
    assert pd.read_parquet(tmp_path / "prices_hourly.parquet").price_mean.iloc[0] == 20
