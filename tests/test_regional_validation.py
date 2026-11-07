import numpy as np
import pandas as pd

from gridsense import config
from gridsense.features.regional import REGIONAL_COLUMNS
from gridsense.models.baselines import SeasonalNaivePrice
from gridsense.models.regional_validation import price_scores, variant_tables


def test_variants_keep_identical_rows_and_labels_without_mutating_source():
    issue = config.VAL_START + pd.Timedelta(hours=config.ISSUE_HOUR)
    table = pd.DataFrame({"issue_ts": [issue.tz_convert("UTC")],
                          "target_ts_utc": [(config.VAL_START + pd.Timedelta(days=1)).tz_convert("UTC")],
                          "horizon_days": [1], "y_price": [10.0], "f_hour": [0.0]}, index=[8])
    regional = table[["issue_ts", "target_ts_utc", "horizon_days"]].assign(
        **{c: 5000.0 if "load" in c else 10.0 for c in REGIONAL_COLUMNS}
    )
    original = table.copy()
    variants, missing = variant_tables(table, table, regional)
    assert missing == {"train": 0, "val": 0}
    for train, val in variants.values():
        pd.testing.assert_frame_equal(train[original.columns], original)
        pd.testing.assert_frame_equal(val[original.columns], original)
    assert len(variants["regional"][0].filter(regex="^f_").columns) == 12
    pd.testing.assert_frame_equal(table, original)


def test_price_reports_compare_models_on_the_supplied_index():
    rows = pd.DataFrame({"horizon_days": [1, 2], "y_price": [10.0, 20.0]}, index=[4, 8])
    naive = pd.DataFrame({"price_p10": [0.0, 10.0], "price_p50": [0.0, 10.0],
                          "price_p90": [20.0, 30.0]}, index=rows.index)
    good = naive.copy()
    good["price_p50"] = [10.0, 20.0]
    report = price_scores(rows, {SeasonalNaivePrice.name: naive, "good": good})
    assert report[report.horizon.eq("all")].n.eq(2).all()
    assert report[report.model.eq("good")].rmae.eq(0).all()
    assert np.isfinite(report.mean_pinball).all()