"""gridsense.pipelines: the registry, Run.append (what the Watchdog will read) and the demo pipelines, on files in a
temporary DATASET_DIR. Nothing is reported: the server calls are replaced by a list of what would have been sent."""
from __future__ import annotations

import json
import re

import pandas as pd
import pytest

from gridsense.pipelines import REGISTRY, Run, demo, pipeline, store
from gridsense.pipelines.__main__ import main

NAME = re.compile(r"^[a-z][a-z0-9-]*$")      # Pipeline.Name
CRON = re.compile(r"^\S+(\s+\S+){4}$")      # Pipeline.Schedule.Cron


@pytest.fixture
def reported(tmp_path, monkeypatch) -> list[tuple]:
    """DATASET_DIR is an empty temporary folder; reports are collected instead of sent."""
    calls: list[tuple] = []

    monkeypatch.setattr(store, "DATASET_DIR", tmp_path)
    monkeypatch.setattr(store, "report_dataset_updated", lambda dataset: calls.append(("dataset", dataset)))
    monkeypatch.setattr(store, "report_run", lambda path, version, issue_ts: calls.append(("run", version, issue_ts)))

    return calls


def hours(start: str, count: int) -> pd.DataFrame:
    ts = pd.date_range(start, periods=count, freq="h", tz="UTC")

    return pd.DataFrame({"ts_utc": ts, "price_mean": range(count), "price_min": 0.0, "price_max": 1.0})


def forecast_run(issue: str) -> pd.DataFrame:
    issue_ts = pd.Timestamp(issue)

    return pd.DataFrame({
        "issue_ts":      issue_ts,
        "target_ts_utc": pd.date_range(issue_ts.floor("D") + pd.Timedelta(hours=22), periods=168, freq="h"),
        "horizon_days":  1,
        "p_near_zero":   0.5,
        "data_quality":  "ok",
    })


def issued_rows(issue: str) -> pd.DataFrame:
    """A training table's rows for one issue: the key, two features, the labels."""
    return forecast_run(issue).drop(columns="p_near_zero").assign(f_ghi_mean=500.0, f_is_holiday=0, f_horizon_days=1, y_price=12.0, y_near_zero=True, y_cheap=False)


# --- The registry, as the PipelineRunner lists it -------------------------------------------------------------------

def test_every_pipeline_fits_the_server_schema():
    assert REGISTRY

    for name, registered in REGISTRY.items():
        definition = registered.definition()

        assert definition["name"] == name
        assert NAME.match(name)
        assert CRON.match(definition["defaultCron"])
        assert set(definition["outputs"]) <= set(store.FILES)


def test_two_pipelines_cant_share_a_name():
    with pytest.raises(ValueError):
        pipeline("prices", "again", outputs=["prices"], default_cron="0 * * * *")(lambda run: None)


def test_list_prints_the_definitions_as_json(monkeypatch, capsys):
    monkeypatch.setattr("sys.argv", ["gridsense.pipelines", "list"])
    main()

    listed = json.loads(capsys.readouterr().out)

    assert {item["name"] for item in listed} == set(REGISTRY)
    assert set(listed[0]) == {"name", "description", "outputs", "defaultCron"}


def test_run_exits_1_when_the_pipeline_raises(monkeypatch, capsys):
    def broken(run: Run) -> None:
        raise RuntimeError("no data today")

    monkeypatch.setitem(REGISTRY, "broken", REGISTRY["prices"].__class__("broken", "", ["prices"], "0 * * * *", broken))
    monkeypatch.setattr("sys.argv", ["gridsense.pipelines", "run", "broken"])

    with pytest.raises(SystemExit) as exited:
        main()

    assert exited.value.code == 1
    assert "no data today" in capsys.readouterr().err


# --- Run.append ------------------------------------------------------------------------------------------------------

def test_append_writes_reports_and_prints_the_marker(reported, capsys):
    appended = Run().append("prices", hours("2026-11-01T22:00Z", 24), key=["ts_utc"])

    assert appended == 24
    assert len(store.read("prices")) == 24
    assert reported == [("dataset", "prices")]

    marker = [line for line in capsys.readouterr().out.splitlines() if line.startswith(store.MARKER)]

    assert [json.loads(line[len(store.MARKER):]) for line in marker] == [{"rowsAppended": {"prices": 24}}]


def test_append_skips_rows_already_there(reported, capsys):
    Run().append("prices", hours("2026-11-01T22:00Z", 24), key=["ts_utc"])

    # Half old, half new.
    appended = Run().append("prices", hours("2026-11-02T10:00Z", 24), key=["ts_utc"])

    assert appended == 12
    assert len(store.read("prices")) == 36
    assert store.read("prices")["ts_utc"].is_unique


def test_append_with_nothing_new_writes_and_reports_nothing(reported, capsys):
    Run().append("prices", hours("2026-11-01T22:00Z", 24), key=["ts_utc"])
    before = store.path("prices").stat().st_mtime_ns

    assert Run().append("prices", hours("2026-11-01T22:00Z", 24), key=["ts_utc"]) == 0
    assert store.path("prices").stat().st_mtime_ns == before
    assert reported == [("dataset", "prices")]
    assert capsys.readouterr().out.count(store.MARKER) == 1


def test_append_leaves_no_partial_file(reported, tmp_path):
    Run().append("prices", hours("2026-11-01T22:00Z", 24), key=["ts_utc"])

    assert sorted(file.name for file in tmp_path.iterdir()) == ["prices_hourly.parquet"]


def test_predictions_are_reported_as_a_run(reported):
    Run().append("predictions", forecast_run("2026-11-01T08:00Z"), key=["issue_ts", "target_ts_utc"], model_version="lgbm-1")

    assert reported == [("run", "lgbm-1", pd.Timestamp("2026-11-01T08:00Z"))]


# --- The demo pipelines ----------------------------------------------------------------------------------------------

@pytest.fixture
def dummy(tmp_path, monkeypatch):
    """A small synthetic dummy: prices for 30 Oct – 2 Nov (local), runs issued 30 and 31 Oct."""
    folder = tmp_path / "synthetic"
    folder.mkdir()

    hours("2026-10-29T22:00Z", 24 * 4).to_parquet(folder / "prices_hourly_dummy.parquet")
    pd.concat([forecast_run("2026-10-30T08:00Z"), forecast_run("2026-10-31T08:00Z")]).to_parquet(folder / "predictions_dummy.parquet")

    monkeypatch.setattr(demo, "SYNTHETIC_DIR", folder)


def test_prices_appends_the_next_local_day(reported, dummy):
    Run().append("prices", hours("2026-10-29T22:00Z", 24), key=["ts_utc"])     # 30 Oct, local

    demo.prices(Run())

    added = store.read("prices")["ts_utc"].iloc[24:]

    assert len(added) == 24
    assert added.min() == pd.Timestamp("2026-10-30T22:00Z")                      # 31 Oct 00:00, Bucharest


def test_prices_across_the_dst_change_has_25_hours(reported, dummy, monkeypatch):
    # 25 Oct 2026, Bucharest: clocks go back, the day has 25 hours.
    folder = demo.SYNTHETIC_DIR
    hours("2026-10-23T21:00Z", 24 * 3).to_parquet(folder / "prices_hourly_dummy.parquet")
    Run().append("prices", hours("2026-10-23T21:00Z", 24), key=["ts_utc"])      # 24 Oct, local

    demo.prices(Run())

    assert len(store.read("prices")) == 24 + 25


def test_prices_repeats_the_last_day_past_the_dummy(reported, dummy):
    Run().append("prices", hours("2026-11-01T22:00Z", 24), key=["ts_utc"])      # 2 Nov, the dummy's last day

    demo.prices(Run())

    added = store.read("prices")["ts_utc"].iloc[24:]

    assert len(added) == 24
    assert added.min() == pd.Timestamp("2026-11-02T22:00Z")


def test_forecast_appends_the_next_run_then_rolls_forward(reported, dummy):
    Run().append("predictions", forecast_run("2026-10-30T08:00Z"), key=["issue_ts", "target_ts_utc"])

    demo.forecast(Run())
    demo.forecast(Run())

    predictions = store.read("predictions")

    assert sorted(predictions["issue_ts"].unique()) == [
        pd.Timestamp("2026-10-30T08:00Z"),
        pd.Timestamp("2026-10-31T08:00Z"),
        pd.Timestamp("2026-11-01T08:00Z"),                                      # past the dummy: the last run, a day later
    ]
    assert (predictions.groupby("issue_ts").size() == 168).all()
    assert [call[1] for call in reported[1:]] == [demo.MODEL_VERSION, demo.MODEL_VERSION]


def test_forecast_rolled_across_the_dst_change_keeps_10_local(reported, dummy):
    # Issued Sat 24 Oct 10:00 (07:00Z, summer time); the dummy has nothing later.
    demo.SYNTHETIC_DIR.joinpath("predictions_dummy.parquet").unlink()
    forecast_run("2026-10-24T07:00Z").to_parquet(demo.SYNTHETIC_DIR / "predictions_dummy.parquet")
    Run().append("predictions", forecast_run("2026-10-24T07:00Z"), key=["issue_ts", "target_ts_utc"])

    demo.forecast(Run())

    issued = store.read("predictions")["issue_ts"].max()

    assert issued == pd.Timestamp("2026-10-25T08:00Z")                          # 10:00 winter time
    assert issued.tz_convert("Europe/Bucharest").hour == 10


# --- The replay: real tables, trained models, a past clock --------------------------------------------------------


@pytest.fixture
def replayed(reported, monkeypatch):
    """The team's tables as small stand-ins (prices 10 Apr – 5 May 2025, issues 24 – 30 Apr), models replaced by a
    function of the rows: no training, no parquet in data/processed."""
    from gridsense.pipelines import replay

    history = hours("2025-04-09T21:00Z", 24 * 26)
    issues = pd.concat([issued_rows(f"2025-04-{day}T07:00Z") for day in range(24, 31)], ignore_index=True)
    tables = {"prices_hourly": history, "training_table": issues}

    monkeypatch.setattr(replay.io, "read", lambda name: tables[name])
    monkeypatch.setattr(replay.artifacts, "load_latest", lambda name: (None, f"{name}-v1"))
    monkeypatch.setattr(replay, "build_predictions", lambda rows, classifier, price, version: rows.assign(model_version=version))
    monkeypatch.delenv("REPLAY_START", raising=False)

    return replay


def test_replay_prices_starts_with_two_weeks_of_history(replayed):
    replayed.prices(Run())

    added = store.read("prices")["ts_utc"]

    # 10 – 24 Apr, local: 15 days.
    assert added.min() == pd.Timestamp("2025-04-09T21:00Z")
    assert added.max() == pd.Timestamp("2025-04-24T20:00Z")


def test_replay_prices_never_runs_ahead_of_the_forecast(replayed, capsys):
    replayed.prices(Run())
    replayed.prices(Run())                                 # 25 Apr clears on the 24th: no forecast issued yet

    assert len(store.read("prices")) == 15 * 24
    assert "run forecast first" in capsys.readouterr().out

    replayed.forecast(Run())                               # issued 24 Apr: that afternoon, the 25th clears
    replayed.prices(Run())

    assert store.read("prices")["ts_utc"].max() == pd.Timestamp("2025-04-25T20:00Z")


def test_replay_prices_catches_up_to_the_day_after_the_last_forecast(replayed):
    replayed.forecast(Run())                               # issued 24 Apr, before any prices
    replayed.prices(Run())                                 # history, then the 25th

    added = store.read("prices")["ts_utc"]

    assert added.min() == pd.Timestamp("2025-04-09T21:00Z")
    assert added.max() == pd.Timestamp("2025-04-25T20:00Z")


def test_replay_forecast_scores_one_issue_a_run(replayed, reported):
    replayed.forecast(Run())
    replayed.forecast(Run())

    issued = store.read("predictions")["issue_ts"].unique()

    assert list(issued) == [pd.Timestamp("2025-04-24T07:00Z"), pd.Timestamp("2025-04-25T07:00Z")]
    assert reported[0][1] == "lgbm_classifier-v1+lgbm_quantile-v1"


def test_replay_refuses_the_test_split(replayed, monkeypatch):
    monkeypatch.setenv("REPLAY_START", "2026-03-01")

    with pytest.raises(RuntimeError, match="test split"):
        replayed.forecast(Run())


def test_replay_refuses_to_write_into_the_teams_data_folder(replayed, monkeypatch):
    monkeypatch.setattr(store, "DATASET_DIR", replayed.config.PROCESSED_DIR.resolve())

    with pytest.raises(RuntimeError, match="team's own data folder"):
        replayed.prices(Run())


def test_replay_refuses_a_folder_holding_another_clocks_files(replayed):
    Run().append("prices", hours("2026-05-01T21:00Z", 24), key=["ts_utc"])     # the synthetic demo's

    with pytest.raises(RuntimeError, match="isn't this replay's"):
        replayed.prices(Run())


def test_replay_forecast_writes_what_the_models_read_without_the_labels(replayed, reported):
    replayed.forecast(Run())

    features = store.read("features")

    assert len(features) == 168
    assert list(features.columns) == ["issue_ts", "target_ts_utc", "horizon_days", "ghi_mean", "is_holiday", "data_quality"]
    assert [call[0] for call in reported] == ["run"]                 # features are written, never reported
