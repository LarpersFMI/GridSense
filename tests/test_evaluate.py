import numpy as np
import pandas as pd
import pytest

from gridsense import config, io
from gridsense.features.build import build_training_table
from gridsense.models import evaluate, train
from gridsense.models.baselines import NAIVE_COLUMN, PERSISTENCE_COLUMN, SeasonalNaivePrice
from gridsense.models.lear import HOUR, LEAR
from gridsense.models.metrics import price_report
from gridsense.splits import assign_split
from gridsense.synthetic import market


@pytest.fixture
def table_with_naive(tiny_training_table):
    rng = np.random.default_rng(1)
    y = tiny_training_table["y_price"]
    local_hour = tiny_training_table["target_ts_utc"].dt.tz_convert(config.LOCAL_TZ).dt.hour
    return tiny_training_table.assign(
        **{
            NAIVE_COLUMN: y + rng.normal(0, 20, len(y)),
            PERSISTENCE_COLUMN: y + rng.normal(0, 15, len(y)),
            HOUR: local_hour,
        }
    )


@pytest.fixture(scope="module")
def fake_market_table() -> pd.DataFrame:
    # Each hourly LEAR model needs more train days than the expanded weather feature count.
    t = market.generate("2024-06-01", "2025-04-30")
    table = build_training_table(t["prices_hourly"], t["grid_hourly"], t["weather_fc"], t["calendar"])
    return table.dropna(subset=["y_price"])


def test_seasonal_naive_quantiles_ordered(table_with_naive):
    split = assign_split(table_with_naive["target_ts_utc"])
    model = SeasonalNaivePrice().fit(table_with_naive[split == "train"])
    out = model.predict(table_with_naive[split == "val"])
    assert (out["price_p10"] <= out["price_p50"]).all()
    assert (out["price_p50"] <= out["price_p90"]).all()


def test_evaluate_price_compares_models_by_horizon(table_with_naive, tmp_dirs):
    io.write(table_with_naive, "training_table")
    train.main(["--task", "price"])
    evaluate.main(["--task", "price"])

    result = (config.REPORTS_DIR / "eval" / "price_val.csv").read_text()
    for model in ("seasonal_naive", "persistence", "lear", "lgbm_quantile"):
        assert model in result


def test_lear_runs_on_fake_market(fake_market_table):
    """Check LEAR on limited fake history; the real comparison needs years."""
    split = assign_split(fake_market_table["target_ts_utc"])
    tr, val = fake_market_table[split == "train"], fake_market_table[split == "val"]
    val = val.dropna(subset=[NAIVE_COLUMN])

    lear = LEAR().fit(tr)
    out = lear.predict(val)
    assert out["price_p50"].notna().all()
    assert (out["price_p10"] <= out["price_p50"]).all() and (out["price_p50"] <= out["price_p90"]).all()

    naive = SeasonalNaivePrice().fit(tr).predict(val)
    assert price_report(val["y_price"], out)["mae"] < 1.2 * price_report(val["y_price"], naive)["mae"]


def test_final_evaluation_runs_once(table_with_naive, tmp_dirs):
    io.write(table_with_naive, "training_table")
    config.REPORTS_DIR.mkdir(parents=True)
    evaluate.final_marker().write_text("already done")
    with pytest.raises(SystemExit, match="already evaluated"):
        evaluate.main(["--final"])
