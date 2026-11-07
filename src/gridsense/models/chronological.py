"""Forward-only monthly development folds; never fit or score the final test split.

Stages: expanding fit history, early stopping, calibration, selection, later scoring.
Every horizon of a target stays together. Before the next stage's earliest issue,
purge the preceding stage's final delivery days (conservatively exclude issue-day
labels too). Day-ahead prices for a delivery day are published the preceding day.
This fixes label timing, not the documented historical source-vintage assumptions.
"""

import argparse
import hashlib
import itertools
import json
from pathlib import Path

import numpy as np
import pandas as pd

from gridsense import config
from gridsense.models.base import PRICE_COLUMNS, feature_columns
from gridsense.models.baselines import (
    NAIVE_COLUMN,
    PERSISTENCE_COLUMN,
    Climatology,
    PersistencePrice,
    SeasonalNaivePrice,
)
from gridsense.models.calibrate import conformal_offsets, fit_calibrator
from gridsense.models.classify import DEFAULT_PARAMS as CLASS_PARAMS
from gridsense.models.classify import LABELS, STEPS, LowPriceClassifier
from gridsense.models.ensemble import PriceEnsemble
from gridsense.models.error_analysis import (
    MAX_SLOT_HOURS,
    MAX_SLOTS_PER_DAY,
    MIN_SLOT_HOURS,
    MONTHLY_BUDGET_HOURS,
    SLOT_HOURS,
    budget_metrics,
)
from gridsense.models.lear import LEAR
from gridsense.models.price import DEFAULT_PARAMS as PRICE_PARAMS
from gridsense.models.price import PriceForecaster
from gridsense.models.regional_validation import price_scores
from gridsense.models.weather_validation import classification_scores
from gridsense.splits import assign_split

STAGES = ("fit", "early_stop", "calibration", "selection", "score")
PROFILES = {
    "default": {"half_life_days": 365.0},
    "recent": {"half_life_days": 180.0},
    "regularized": {"half_life_days": 365.0, "num_leaves": 15, "min_child_samples": 100},
}
TAUS = (0.0, 0.3, 0.5, 0.7, 0.8, 0.9, 0.95)
MAX_CANCELLATION = 0.10


def digest(path: Path) -> str:
    hasher = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


def default_score_months() -> list[str]:
    """The first three validation months supply early-stop/calibration/selection."""
    months = pd.period_range(config.VAL_START.date(), config.VAL_END.date(), freq="M")
    return [str(month) for month in months[3:]]


def month_fold(table: pd.DataFrame, score_month: str) -> tuple[dict, dict]:
    split = assign_split(table["target_ts_utc"])
    if not split.isin(["train", "val"]).all() or table["y_price"].isna().any():
        raise ValueError("Chronological inputs must contain labelled train/validation rows only")
    if table.duplicated(["issue_ts", "target_ts_utc", "horizon_days"]).any():
        raise ValueError("Duplicate forecast keys")
    # Reject conflicting labels across repeated horizons, before any fitting.
    if table.groupby("target_ts_utc")[list(LABELS.values()) + ["y_price"]].nunique().gt(1).any().any():
        raise ValueError("Repeated target labels must agree across horizons")
    month = pd.Period(score_month, freq="M")
    if str(month) not in default_score_months():
        raise ValueError("Score month must leave three earlier months within configured validation")
    local = table["target_ts_utc"].dt.tz_convert(config.LOCAL_TZ)
    months = local.dt.tz_localize(None).dt.to_period("M")
    stages = {"fit": table[months < month - 3].copy()}
    for name, offset in zip(STAGES[1:], (-3, -2, -1, 0), strict=True):
        stages[name] = table[months == month + offset].copy()
    purged = {}
    # Use each next block's original earliest issue, not its latest target date.
    for before, after in itertools.pairwise(STAGES):
        if stages[after].empty:
            raise ValueError(f"Empty chronological block: {after}")
        cutoff = stages[after]["issue_ts"].min().tz_convert(config.LOCAL_TZ).normalize()
        keep = stages[before]["target_ts_utc"].dt.tz_convert(config.LOCAL_TZ) < cutoff
        purged[before] = int((~keep).sum())
        stages[before] = stages[before][keep].copy()
    if any(part.empty for part in stages.values()):
        raise ValueError("Every chronological stage must contain rows after purging")
    # Drop columns based ONLY on fitting history, never score/calibration coverage.
    empty = [column for column in feature_columns(stages["fit"])
             if not stages["fit"][column].notna().any()]
    stages = {name: part.drop(columns=empty) for name, part in stages.items()}
    metadata = {"score_month": str(month), "purged_rows": purged, "dropped_features": empty,
                "stages": {}}
    for name, part in stages.items():
        metadata["stages"][name] = {
            "rows": len(part), "unique_targets": part["target_ts_utc"].nunique(),
            "target_min": part["target_ts_utc"].min().isoformat(),
            "target_max": part["target_ts_utc"].max().isoformat(),
            "issue_min": part["issue_ts"].min().isoformat(),
            "positives": {label: int(part.drop_duplicates("target_ts_utc")[label].sum())
                          for label in LABELS.values()},
        }
    return stages, metadata


def threshold_slots(rows: pd.DataFrame, probability: pd.Series, tau: float) -> dict:
    """Budget-cap proxy, not an online planner: every announced hour must exceed tau.

    Rank forecast blocks within a target month, without realised-price information.
    No quota: zero announcements is permitted. The retrospective monthly ranking
    is not a claim of causal day-by-day budget execution.
    """
    local = rows["target_ts_utc"].dt.tz_convert(config.LOCAL_TZ)
    frame = pd.DataFrame({"date": local.dt.date, "hour": local.dt.hour,
                          "p": probability.reindex(rows.index), "price": rows["y_price"]})
    frame = frame[frame.hour.isin(SLOT_HOURS)]
    if frame.duplicated(["date", "hour"]).any() or frame.p.isna().any():
        raise ValueError("Threshold slots require unique local hours and finite scores")
    if not frame.p.between(0, 1).all():
        raise ValueError("Slot probabilities must be within [0, 1]")
    wide = frame.pivot(index="date", columns="hour", values="p").reindex(columns=SLOT_HOURS)
    candidates = []
    for day, values in wide.iterrows():
        for start in SLOT_HOURS:
            for length in range(MIN_SLOT_HOURS, MAX_SLOT_HOURS + 1):
                block = values.reindex(range(start, start + length))
                if block.notna().all() and block.ge(tau).all():
                    candidates.append((float(block.mean()), length, day, start))
    candidates.sort(key=lambda item: (-item[0], -item[1], item[2], item[3]))
    used, hits, near, excess, count = 0, 0, 0, 0.0, 0
    monthly_used = {}
    occupied = {}
    price = frame.set_index(["date", "hour"])["price"]
    for _, length, day, start in candidates:
        month = (day.year, day.month)
        blocks = occupied.setdefault(day, [])
        if monthly_used.get(month, 0) + length > MONTHLY_BUDGET_HOURS or len(blocks) >= MAX_SLOTS_PER_DAY:
            continue
        if any(start < end and begin < start + length for begin, end in blocks):
            continue
        blocks.append((start, start + length))
        actual = price.loc[[(day, hour) for hour in range(start, start + length)]]
        cheap = actual.le(config.NEAR_ZERO_THRESHOLD_EUR)
        hits += int(cheap.all())
        near += int(cheap.sum())
        excess += float((actual - config.NEAR_ZERO_THRESHOLD_EUR).clip(lower=0).sum())
        used += length
        monthly_used[month] = monthly_used.get(month, 0) + length
        count += 1
    return {"tau": tau, "slots": count, "announced_hours": used,
            "slot_hit_rate": hits / count if count else None,
            "cancellation_rate": 1 - hits / count if count else None,
            "slot_hour_precision": near / used if used else None,
            "excess_eur_per_mwh": excess / used if used else None}


def select_policy(rows: pd.DataFrame, scores: dict[str, pd.Series]) -> tuple[dict, list]:
    """Choose ranker/tau per horizon only on the preceding selection block."""
    policies, candidates = {}, []
    for horizon, index in rows.groupby("horizon_days").groups.items():
        horizon = int(rows.loc[index, "horizon_days"].iloc[0])
        options = []
        for ranker, probability in scores.items():
            for tau in TAUS:
                result = threshold_slots(rows.loc[index], probability.loc[index], tau)
                result |= {"horizon": int(horizon), "ranker": ranker}
                candidates.append(result)
                if result["slots"] and result["cancellation_rate"] <= MAX_CANCELLATION:
                    options.append(result)
        # If no safe selection candidate exists, explicitly abstain on the score block.
        best = max(options, key=lambda row: (row["announced_hours"], row["slot_hit_rate"],
                                             -row["excess_eur_per_mwh"])) if options else None
        policies[int(horizon)] = None if best is None else {"ranker": best["ranker"], "tau": best["tau"]}
    return policies, candidates


def calibrate_chain(classifier: LowPriceClassifier, calib: pd.DataFrame) -> None:
    """Fit each conditional chain step on its own calibration population only."""
    raw = classifier.step_probabilities(calib, apply_calibration=False)
    for step, (label, condition) in STEPS.items():
        selected = np.ones(len(calib), dtype=bool) if condition is None else calib[condition].to_numpy(
            dtype=bool)
        y = calib.loc[selected, label].to_numpy(dtype=int)
        if np.unique(y).size != 2:
            raise ValueError(f"Calibration block has a single class for chain step {step}")
        classifier.calibrators[step] = fit_calibrator(np.asarray(raw[step])[selected], y, "platt")


def fit_fold(stages: dict, profile: str = "default", smoke: bool = False) -> dict:
    """Models/calibrators consume only their designated earlier stages."""
    fit, stop, calib, selection, score = (stages[name] for name in STAGES)
    options = dict(PROFILES[profile])
    half_life = options.pop("half_life_days")
    options["n_jobs"] = 4
    if smoke:
        options["n_estimators"] = 8
    price = PriceForecaster(params=PRICE_PARAMS | options, half_life_days=half_life, conformal=False,
                            quantiles=tuple(config.QUANTILES) if smoke else PriceForecaster().quantiles)
    classifier = LowPriceClassifier(params=CLASS_PARAMS | options, half_life_days=half_life,
                                    calibration=None)
    price.fit(fit, stop)
    classifier.fit(fit, stop)
    raw_calib = price.predict_quantiles(calib)
    lo, _, hi = config.QUANTILES
    price.conformal_offsets = conformal_offsets(calib.y_price, raw_calib[lo], raw_calib[hi],
                                                calib.horizon_days, coverage=hi - lo)
    calibrate_chain(classifier, calib)
    lear = LEAR().fit(fit, calib)
    baselines = [model.fit(fit) for model in (SeasonalNaivePrice(), PersistencePrice())]
    selection_price = selection.dropna(subset=[NAIVE_COLUMN, PERSISTENCE_COLUMN])
    score_price = score.dropna(subset=[NAIVE_COLUMN, PERSISTENCE_COLUMN])
    ensemble = PriceEnsemble(lear.predict, price.predict).fit(selection_price)
    predictions = {model.name: model.predict(score_price) for model in [*baselines, lear, price, ensemble]}
    for name, pred in predictions.items():
        if not np.isfinite(pred[list(PRICE_COLUMNS)].to_numpy()).all():
            raise ValueError(f"Non-finite scored price predictions: {name}")
    raw = classifier.predict(score, apply_calibration=False)
    calibrated = classifier.predict(score)
    if calibrated.p_cheap.gt(calibrated.p_near_zero).any() or raw.p_cheap.gt(raw.p_near_zero).any():
        raise ValueError("Nested classifier probabilities violated logical ordering")
    classes = {"climatology": Climatology().fit(fit).predict(score), "lgbm_raw": raw,
               "lgbm_platt_forward": calibrated}
    for name, pred in classes.items():
        if not np.isfinite(pred[list(LABELS)].to_numpy()).all():
            raise ValueError(f"Non-finite scored probabilities: {name}")

    # Price-derived near-zero probability is fitted only on the calibration block.
    price_calibrator = fit_calibrator(
        1 / (1 + np.exp(np.clip((price.predict(calib).price_p50 - config.NEAR_ZERO_THRESHOLD_EUR)
                               / 20.0, -30, 30))), calib.y_near_zero, "platt")

    def rankers(rows):
        p = classifier.predict(rows).p_near_zero
        price_p = price_calibrator.predict(1 / (1 + np.exp(np.clip(
            (price.predict(rows).price_p50 - config.NEAR_ZERO_THRESHOLD_EUR) / 20.0, -30, 30))))
        price_p = pd.Series(price_p, index=rows.index)
        return {"classifier": p, "price": price_p, "combined": (p + price_p) / 2}

    policies, candidates = select_policy(selection_price, rankers(selection_price))
    later_rankers = rankers(score_price)
    selected = []
    for horizon, index in score_price.groupby("horizon_days").groups.items():
        policy = policies[int(horizon)]
        if policy is None:
            result = {"tau": None, "slots": 0, "announced_hours": 0, "slot_hit_rate": None,
                      "cancellation_rate": None, "slot_hour_precision": None,
                      "excess_eur_per_mwh": None, "ranker": "abstain"}
        else:
            result = threshold_slots(score_price.loc[index],
                                     later_rankers[policy["ranker"]].loc[index], policy["tau"])
            result["ranker"] = policy["ranker"]
        selected.append(result | {"horizon": int(horizon)})
    budgets = {"climatology": classes["climatology"].p_near_zero.loc[score_price.index],
               "lgbm_raw": raw.p_near_zero.loc[score_price.index],
               "ensemble_p50": -predictions[ensemble.name].price_p50}
    return {
        "price": price_scores(score_price, predictions),
        "classify": pd.concat([classification_scores(score, pred).assign(model=name)
                               for name, pred in classes.items()], ignore_index=True),
        "budget": budget_metrics(score_price, budgets),
        "selection": pd.DataFrame(candidates), "policy_score": pd.DataFrame(selected),
        "metadata": {"features": feature_columns(fit), "price_params": price.params,
                     "classifier_params": classifier.params, "half_life_days": half_life,
                     "classifier_structure": classifier.metadata().get("structure"),
                     "price_best_iterations": price.best_iterations(),
                     "classifier_best_iterations": classifier.best_iterations(),
                     "lear_weight": ensemble.weight, "conformal_offsets": price.conformal_offsets,
                     "policies": policies, "nesting_violations": int(calibrated.p_cheap.gt(
                         calibrated.p_near_zero).sum()), "smoke_only": smoke},
    }


def run_job(input_path: Path, output: Path, *, months: list[str], profile: str, smoke: bool,
            expected_hash: str) -> dict:
    if digest(input_path) != expected_hash:
        raise ValueError("Experiment snapshot checksum mismatch")
    output.mkdir(parents=True, exist_ok=True)
    table = pd.read_parquet(input_path)
    metadata, reports = [], {}
    for month in months:
        print(f"[chronological] {input_path.stem}/{profile}/{month}; smoke={smoke}", flush=True)
        stages, protocol = month_fold(table, month)
        result = fit_fold(stages, profile=profile, smoke=smoke)
        metadata.append(protocol | result.pop("metadata"))
        for name, report in result.items():
            reports.setdefault(name, []).append(report.assign(score_month=month))
    if digest(input_path) != expected_hash:
        raise RuntimeError("Experiment input changed during fitting")
    hashes = {}
    for name, parts in reports.items():
        path = output / f"{name}.csv"
        pd.concat(parts, ignore_index=True).to_csv(path, index=False)
        hashes[path.name] = digest(path)
    result = {"completed_at_utc": pd.Timestamp.now(tz="UTC").isoformat(),
              "test_evaluated": False, "production_artifacts_changed": False,
              "input_sha256": expected_hash, "report_sha256": hashes,
              "profile": profile, "smoke_only": smoke, "folds": metadata,
              "caveats": ["Original source-vintage/weather publication assumptions remain unresolved.",
                          "All earlier validation months have already been explored during development.",
                          "Monthly budget ranking is retrospective, not a causal online planner.",
                          "10% cancellation is a selection target, not a scored guarantee.",
                          "Repeated horizons are not independent observations."]}
    (output / "completed.json").write_text(json.dumps(result, indent=2, allow_nan=False) + "\n")
    return result


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--sha256", required=True)
    parser.add_argument("--months", nargs="+", default=default_score_months())
    parser.add_argument("--profile", choices=PROFILES, default="default")
    parser.add_argument("--smoke", action="store_true")
    args = parser.parse_args(argv)
    if config.DATA_MODE != "real":
        parser.error("Chronological development experiments require explicit real mode")
    run_job(args.input, args.output, months=args.months, profile=args.profile, smoke=args.smoke,
            expected_hash=args.sha256)


if __name__ == "__main__":
    main()