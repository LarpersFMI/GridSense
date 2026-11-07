import numpy as np
import pandas as pd

from gridsense import config
from gridsense.data.calendar import build_calendar
from gridsense.data.price_snapshot import expand_a03
from gridsense.models.base import OUTPUT_COLUMNS
from gridsense.models.ensemble import PriceEnsemble
from gridsense.schemas import CALENDAR, COUNTRY_CALENDAR


def test_expand_a03_fills_repeated_prices_within_delivery_day():
    # A03 omits points that repeat the previous price; 23:00 UTC is midnight in Brussels in winter.
    day = pd.Timestamp("2024-01-14 23:00", tz="UTC")
    kept = [day, day + pd.Timedelta(hours=3), day + pd.Timedelta(hours=23)]
    df = pd.DataFrame(
        {
            "timestamp_utc": kept,
            "price": [10.0, -5.0, 80.0],
            "curve_type": "A03",
            "resolution": "PT60M",
            "document_id": "doc",
        }
    )
    out = expand_a03(df)
    assert len(out) == 24
    assert out["price"].tolist()[:5] == [10, 10, 10, -5, -5]
    assert out["price"].iloc[-2:].tolist() == [-5, 80]


def test_calendar_has_dst_days_and_holidays():
    cal = build_calendar(pd.Timestamp("2025-03-30").date(), pd.Timestamp("2025-12-25").date())
    # The builder retains the upstream country metadata while satisfying the core ML contract.
    assert cal[list(CALENDAR)].dtypes.astype(str).to_dict() == CALENDAR
    assert cal.dtypes.astype(str).to_dict() == COUNTRY_CALENDAR
    assert cal["country"].eq("Romania").all()
    local = cal["ts_utc"].dt.tz_convert(config.LOCAL_TZ)
    assert cal.loc[local.dt.date.astype(str) == "2025-03-30", "day_hours"].iloc[0] == 23
    assert cal.loc[local.dt.date.astype(str) == "2025-10-26", "day_hours"].iloc[0] == 25
    assert cal.loc[local.dt.date.astype(str) == "2025-12-25", "is_holiday"].all()


def _constant(p10, p50, p90):
    def predict(table):
        out = pd.DataFrame(np.nan, index=table.index, columns=list(OUTPUT_COLUMNS))
        out[["price_p10", "price_p50", "price_p90"]] = [p10, p50, p90]
        return out

    return predict


def test_ensemble_picks_the_better_member():
    val = pd.DataFrame({"y_price": np.full(50, 100.0), "horizon_days": 1})
    good, bad = _constant(90, 100, 110), _constant(0, 40, 60)
    assert PriceEnsemble(good, bad).fit(val).weight == 1.0
    assert PriceEnsemble(bad, good).fit(val).weight == 0.0
    out = PriceEnsemble(good, bad, weight=0.5).predict(val)
    assert out["price_p50"].iloc[0] == 70
