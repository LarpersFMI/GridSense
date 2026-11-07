"""Default features vs +extra forecast weather (humidity, precipitation, pressure, 10 m wind).

Both variants come from one in-memory build, so rows, labels and all other features are
identical. Never replaces production artifacts or the training table. No test evaluation.
"""

import hashlib
import json

import pandas as pd

from gridsense import config, io
from gridsense.features.build import EXTRA_WEATHER_VARS, build_training_table, drop_untrainable
from gridsense.models.ablate_price import validation_tables
from gridsense.models.baselines import NAIVE_COLUMN, PERSISTENCE_COLUMN
from gridsense.models.error_analysis import compare_variants, print_comparison

EXTRA_PREFIXES = tuple(f"f_{short}_" for short in EXTRA_WEATHER_VARS.values())


def main() -> None:
    if config.DATA_MODE != "real":
        raise SystemExit("Extra-weather validation requires real archived forecasts")
    table_bytes = (config.PROCESSED_DIR / "training_table.parquet").read_bytes()
    weather_fc = io.read("weather_fc")
    table = build_training_table(io.read("prices_hourly"), io.read("grid_hourly"), weather_fc,
                                 io.read("calendar"), weather_extra=True)
    table, dropped = drop_untrainable(table)
    extra = [c for c in table if c.startswith(EXTRA_PREFIXES)]
    current = table.drop(columns=extra)
    pd.testing.assert_frame_equal(current, io.read("training_table"))
    train, val = validation_tables(table)
    price_index = val.dropna(subset=[NAIVE_COLUMN, PERSISTENCE_COLUMN]).index
    variants = {"current": (train.drop(columns=extra), val.drop(columns=extra)),
                "weather_extra": (train, val)}
    prices, classes, budgets, runs = compare_variants(variants, price_index)
    if (config.PROCESSED_DIR / "training_table.parquet").read_bytes() != table_bytes:
        raise RuntimeError("Training table changed while the extras experiment was running")

    out = config.REPORTS_DIR / "eval"
    out.mkdir(parents=True, exist_ok=True)
    prices.to_csv(out / "price_weather_extra_val.csv", index=False)
    classes.to_csv(out / "classify_weather_extra_val.csv", index=False)
    budgets.to_csv(out / "decision_weather_extra_val.csv", index=False)
    split = pd.concat([pd.Series("train", index=train.index), pd.Series("val", index=val.index)])
    rows = pd.concat([train, val])
    availability = rows[extra].notna().groupby([split, rows.horizon_days]).mean()
    availability.to_csv(out / "weather_extra_availability.csv")
    metadata = {
        "run_at_utc": pd.Timestamp.now(tz="UTC").isoformat(), "data_mode": config.DATA_MODE,
        "test_evaluated": False, "production_artifacts_changed": False, "training_table_changed": False,
        "extra_features": extra, "dropped_untrainable": dropped,
        "training_table_sha256": hashlib.sha256(table_bytes).hexdigest(),
        "price_scored_rows": len(price_index), "runs": runs,
        "weather_fc_sha256": hashlib.sha256(
            (config.PROCESSED_DIR / "weather_fc.parquet").read_bytes()).hexdigest(),
        "caveats": [
            "Same GFS Previous Runs offsets and assumed 12 h publication buffer as weather_fc; not verified.",
            "Extra variables are archived only from late Feb 2024, so ~40% of train rows have them.",
            "Early stopping, conformal widening and ensemble weight reuse validation.",
            "Forecast rows across horizons repeat target labels and are not independent.",
        ],
    }
    (out / "weather_extra_validation.json").write_text(json.dumps(metadata, indent=2, default=str) + "\n")
    print(f"extra features ({len(extra)}): {extra}")
    print(availability.groupby(level=0).mean().mean(axis=1).round(3).to_string())
    print_comparison(prices, classes, budgets)


if __name__ == "__main__":
    main()
