"""Validation error decomposition and announcement-budget metrics. Owner: ML-P.

Validation only: no test or unassigned labels are fitted or scored. The slot rule is an
ML-side proxy of project_plan §7 (contiguous 2–6 h blocks 09:00–18:00 local, at most two
per day, 70 free hours per month), not the agent planner, which is not implemented yet.
"""

import hashlib
import json

import numpy as np
import pandas as pd

from gridsense import config, io
from gridsense.agent.decision_rule import DecisionParams
from gridsense.models.ablate_price import validation_tables
from gridsense.models.base import feature_columns
from gridsense.models.baselines import (
    NAIVE_COLUMN,
    PERSISTENCE_COLUMN,
    Climatology,
    PersistencePrice,
    SeasonalNaivePrice,
)
from gridsense.models.classify import LowPriceClassifier
from gridsense.models.ensemble import PriceEnsemble
from gridsense.models.lear import LEAR
from gridsense.models.metrics import price_report
from gridsense.models.price import PriceForecaster
from gridsense.models.regional_validation import price_scores
from gridsense.models.weather_validation import classification_scores, cross_calibrated_predictions

PRICE_BANDS = (-np.inf, 0.0, 20.0, 60.0, 120.0, 200.0, np.inf)
BAND_LABELS = ("<=0", "0-20", "20-60", "60-120", "120-200", ">200")
SLOT_HOURS = tuple(range(9, 18))
MIN_SLOT_HOURS, MAX_SLOT_HOURS = 2, 6
_defaults = DecisionParams(tau_likely=0.0, tau_possible=0.0, cancel_penalty_eur=0.0)
MONTHLY_BUDGET_HOURS = _defaults.monthly_budget_hours
MAX_SLOTS_PER_DAY = _defaults.max_slots_per_day


def fit_models(train: pd.DataFrame, val: pd.DataFrame, price_index: pd.Index):
    """Default price models, ensemble and classifiers fitted from scratch on the given tables."""
    rows = val.loc[price_index]
    price, lear = PriceForecaster().fit(train, val), LEAR().fit(train, val)
    prices = {m.name: m.fit(train, val).predict(rows) for m in (SeasonalNaivePrice(), PersistencePrice())}
    prices[lear.name], prices[price.name] = lear.predict(rows), price.predict(rows)
    ensemble = PriceEnsemble(lambda _, p=prices[lear.name]: p, lambda _, p=prices[price.name]: p).fit(rows)
    prices[ensemble.name] = ensemble.predict(rows)
    classifier = LowPriceClassifier().fit(train, val)
    raw = classifier.predict(val, apply_calibration=False)
    classes = {
        "climatology": Climatology().fit(train).predict(val),
        "lgbm_raw": raw,
        "lgbm_platt_crossfit": cross_calibrated_predictions(val, raw, classifier.calibration),
    }
    info = {
        "train_rows": len(train), "val_rows": len(val), "price_scored_rows": len(rows),
        "lear_weight": ensemble.weight,
        "price_best_iterations": price.best_iterations(),
        "classifier_best_iterations": classifier.best_iterations(),
        "probability_order_violations_crossfit": int(
            classes["lgbm_platt_crossfit"].p_cheap.gt(classes["lgbm_platt_crossfit"].p_near_zero).sum()
        ),
    }
    return prices, classes, info


def _dimensions(rows: pd.DataFrame) -> dict[str, pd.Series]:
    local = rows["target_ts_utc"].dt.tz_convert(config.LOCAL_TZ)
    day_type = np.where(rows["f_is_holiday"].eq(1), "holiday",
                        np.where(rows["f_is_weekend"].eq(1), "weekend", "weekday"))
    return {
        "price_band": pd.cut(rows["y_price"], PRICE_BANDS, labels=BAND_LABELS).astype(str),
        "local_hour": local.dt.hour,
        "horizon": rows["horizon_days"],
        "day_type": pd.Series(day_type, index=rows.index),
        "month": local.dt.strftime("%Y-%m"),
    }


def price_breakdown(rows: pd.DataFrame, predictions: dict[str, pd.DataFrame]) -> pd.DataFrame:
    """MAE, bias, pinball and each group's share of the model's total absolute P50 error."""
    out = []
    dimensions = _dimensions(rows)
    for name, pred in predictions.items():
        if not pred.index.equals(rows.index):
            raise ValueError(f"Predictions must align with the scored rows: {name}")
        err = pred["price_p50"] - rows["y_price"]
        total = err.abs().sum()
        for dimension, key in dimensions.items():
            for group, index in rows.groupby(key).groups.items():
                report = price_report(rows.loc[index, "y_price"], pred.loc[index])
                out.append({
                    "model": name, "dimension": dimension, "group": str(group), "n": report["n"],
                    "mae": report["mae"], "bias": float(err.loc[index].mean()),
                    "abs_error_share": float(err.loc[index].abs().sum() / total),
                    "mean_pinball": report["mean_pinball"], "coverage": report["coverage"],
                    "width": report["width"],
                })
    return pd.DataFrame(out)


def compare_variants(variants: dict[str, tuple[pd.DataFrame, pd.DataFrame]], price_index: pd.Index):
    """Fit every (train, val) variant from scratch and score all of them on the same rows."""
    prices, classes, budgets, runs = [], [], [], {}
    for name, (train, val) in variants.items():
        print(f"[{config.DATA_MODE}] fitting {name}: {len(feature_columns(train))} features", flush=True)
        price_pred, class_pred, info = fit_models(train, val, price_index)
        rows = val.loc[price_index]
        prices.append(price_scores(rows, price_pred).assign(variant=name))
        classes.extend(classification_scores(val, pred).assign(model=model, variant=name)
                       for model, pred in class_pred.items())
        budgets.append(budget_metrics(rows, decision_scores(rows, price_pred, class_pred)).assign(variant=name))
        runs[name] = {"features": feature_columns(train), **info}
    return (pd.concat(prices, ignore_index=True), pd.concat(classes, ignore_index=True),
            pd.concat(budgets, ignore_index=True), runs)


def print_comparison(prices: pd.DataFrame, classes: pd.DataFrame, budgets: pd.DataFrame) -> None:
    for metric in ("mae", "mae_low_price", "mean_pinball"):
        table = prices[prices.horizon.eq("all")].pivot(index="model", columns="variant", values=metric)
        print(f"{metric}\n{table.round(3).to_string()}")
    by_h = prices[prices.model.eq(PriceEnsemble.name)].pivot(index="horizon", columns="variant", values="mae")
    print(f"ensemble MAE by horizon\n{by_h.round(3).to_string()}")
    near = classes[classes.horizon.eq("all")].pivot_table(index=["model", "label"], columns="variant",
                                                          values=["pr_auc", "brier"])
    print(near.round(4).to_string())
    print(budgets[budgets.horizon.eq("all")].pivot(index="model", columns="variant", values=[
        "precision_at_budget", "slot_hit_rate", "excess_eur_per_mwh"]).round(3).to_string())


def plan_month(frame: pd.DataFrame) -> list[tuple]:
    """Greedy highest-mean-score blocks for one (horizon, month); columns date, hour, score."""
    grid = frame.pivot(index="date", columns="hour", values="score").reindex(columns=list(SLOT_HOURS))
    values, candidates = grid.to_numpy(dtype=float), []
    for i, day in enumerate(grid.index):
        for s in range(len(SLOT_HOURS)):
            for length in range(MIN_SLOT_HOURS, MAX_SLOT_HOURS + 1):
                block = values[i, s:s + length]
                if len(block) == length and not np.isnan(block).any():
                    candidates.append((float(block.mean()), length, day, SLOT_HOURS[s]))
    candidates.sort(key=lambda c: (-c[0], -c[1], c[2], c[3]))
    used, taken, chosen = 0, {}, []
    for _, length, day, start in candidates:
        blocks = taken.setdefault(day, [])
        if used + length > MONTHLY_BUDGET_HOURS or len(blocks) >= MAX_SLOTS_PER_DAY:
            continue
        if any(start < end and begin < start + length for begin, end in blocks):
            continue
        blocks.append((start, start + length))
        used += length
        chosen.append((day, start, length))
        if used == MONTHLY_BUDGET_HOURS:
            break
    return chosen


def decision_scores(rows: pd.DataFrame, prices: dict[str, pd.DataFrame],
                    classes: dict[str, pd.DataFrame]) -> dict[str, pd.Series]:
    """Higher = more likely cheap. `oracle` uses realised prices: an upper bound, not a model."""
    scores = {"oracle": -rows["y_price"]}
    for name in ("climatology", "lgbm_raw"):
        scores[name] = classes[name]["p_near_zero"].loc[rows.index]
    scores["ensemble_p50"] = -prices[PriceEnsemble.name]["price_p50"]
    return scores


def budget_metrics(rows: pd.DataFrame, scores: dict[str, pd.Series]) -> pd.DataFrame:
    """Precision of the top budgeted hours and slot outcomes per horizon (months pooled)."""
    local = rows["target_ts_utc"].dt.tz_convert(config.LOCAL_TZ)
    base = pd.DataFrame({"horizon": rows["horizon_days"], "month": local.dt.strftime("%Y-%m"),
                         "date": local.dt.date, "hour": local.dt.hour, "y_price": rows["y_price"]},
                        index=rows.index)
    base = base[base["hour"].isin(SLOT_HOURS)]
    if base.duplicated(["horizon", "date", "hour"]).any():
        raise ValueError("Slot hours must be unique per horizon and local date")
    threshold = config.NEAR_ZERO_THRESHOLD_EUR
    out = []
    for name, score in scores.items():
        frame = base.assign(score=score.reindex(base.index))
        if frame["score"].isna().any():
            raise ValueError(f"Missing decision scores: {name}")
        hours, slots = [], []
        for (horizon, month), group in frame.groupby(["horizon", "month"]):
            top = group.nlargest(MONTHLY_BUDGET_HOURS, "score")
            hours.append(pd.DataFrame({"horizon": horizon, "near_zero": top["y_price"].le(threshold)}))
            price = group.set_index(["date", "hour"])["y_price"]
            for day, start, length in plan_month(group):
                p = price.loc[[(day, start + k) for k in range(length)]].to_numpy()
                slots.append({"horizon": horizon, "hours": length, "hit": bool((p <= threshold).all()),
                              "near_zero_hours": int((p <= threshold).sum()), "price_sum": float(p.sum()),
                              "excess_sum": float(np.clip(p - threshold, 0, None).sum())})
        hours, slots = pd.concat(hours), pd.DataFrame(slots)
        for horizon in ["all", *sorted(base["horizon"].unique())]:
            h = hours if horizon == "all" else hours[hours["horizon"].eq(horizon)]
            s = slots if horizon == "all" else slots[slots["horizon"].eq(horizon)]
            out.append({
                "model": name, "horizon": horizon,
                "precision_at_budget": float(h["near_zero"].mean()),
                "slots": len(s), "announced_hours": int(s["hours"].sum()),
                "slot_hit_rate": float(s["hit"].mean()),
                "slot_hour_precision": float(s["near_zero_hours"].sum() / s["hours"].sum()),
                "mean_price_announced": float(s["price_sum"].sum() / s["hours"].sum()),
                "excess_eur_per_mwh": float(s["excess_sum"].sum() / s["hours"].sum()),
            })
    return pd.DataFrame(out)


def main() -> None:
    if config.DATA_MODE != "real":
        raise SystemExit("Error analysis requires real data; never report fake numbers")
    train, val = validation_tables(io.read("training_table"))
    price_index = val.dropna(subset=[NAIVE_COLUMN, PERSISTENCE_COLUMN]).index
    prices, classes, info = fit_models(train, val, price_index)
    rows = val.loc[price_index]
    breakdown = price_breakdown(rows, prices)
    budget = budget_metrics(rows, decision_scores(rows, prices, classes))
    classification = pd.concat([classification_scores(val, pred).assign(model=name)
                                for name, pred in classes.items()], ignore_index=True)

    out = config.REPORTS_DIR / "eval"
    out.mkdir(parents=True, exist_ok=True)
    breakdown.to_csv(out / "error_breakdown_val.csv", index=False)
    budget.to_csv(out / "decision_metrics_val.csv", index=False)
    classification.to_csv(out / "error_analysis_classify_val.csv", index=False)
    metadata = {
        "run_at_utc": pd.Timestamp.now(tz="UTC").isoformat(), "data_mode": config.DATA_MODE,
        "test_evaluated": False, "production_artifacts_changed": False, **info,
        "slot_rule": {"local_hours": [SLOT_HOURS[0], SLOT_HOURS[-1] + 1],
                      "slot_hours": [MIN_SLOT_HOURS, MAX_SLOT_HOURS],
                      "max_slots_per_day": MAX_SLOTS_PER_DAY, "monthly_budget_hours": MONTHLY_BUDGET_HOURS,
                      "hit": f"every hour <= {config.NEAR_ZERO_THRESHOLD_EUR} EUR/MWh"},
        "inputs_sha256": {"training_table": hashlib.sha256(
            (config.PROCESSED_DIR / "training_table.parquet").read_bytes()).hexdigest()},
        "caveats": [
            "Each horizon is planned separately for every validation month; budget always fills (no tau).",
            "Greedy mean-probability slot proxy, not the agent planner; cancellation = 1 - slot_hit_rate.",
            "Platt cross-fit is monotone within a month, so its budget ranking equals lgbm_raw.",
            "Early stopping, conformal widening and ensemble weight reuse validation.",
            "oracle ranks by realised prices and is only an upper bound.",
            "Forecast rows across horizons repeat target labels and are not independent.",
        ],
    }
    (out / "error_analysis_val.json").write_text(json.dumps(metadata, indent=2, default=str) + "\n")

    ens = breakdown[breakdown.model.eq(PriceEnsemble.name)].set_index(["dimension", "group"])
    for dimension in ("price_band", "day_type", "horizon"):
        print(ens.loc[dimension][["n", "mae", "bias", "abs_error_share", "coverage"]].round(3).to_string())
    print(budget[budget.horizon.eq("all")].set_index("model").round(3).to_string())
    print(json.dumps(info, indent=2))


if __name__ == "__main__":
    main()
