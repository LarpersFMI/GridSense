"""Bounded, D+1-only cancellation research using rolling earlier policy history.

No production promotion, observed-weather substitution or final-test evaluation.
This separate module preserves both the original queue and the prior slot run.
"""

import argparse
import fcntl
import itertools
import json
from dataclasses import asdict, dataclass
from pathlib import Path

import lightgbm as lgb
import numpy as np
import pandas as pd

from experiments import slot_validation as slots
from gridsense import config
from gridsense.models.base import feature_columns, recency_weights
from gridsense.models.chronological import PROFILES, default_score_months, digest
from gridsense.models.classify import DEFAULT_PARAMS, NEAR_ZERO
from gridsense.models.metrics import classification_report
from gridsense.models.overnight import atomic_json, verify_plan
from gridsense.splits import assign_split

PREDICTORS = ("hourly_pooled", "hourly_d1", "slot_d1")


@dataclass(frozen=True)
class Settings:
    selection_months: int = 3
    max_cancellation: float = slots.MAX_CANCELLATION
    confidence: float = 0.90
    min_support_days: int = 15
    min_active_months: int = 2
    thresholds: tuple[float, ...] = (0.80, 0.85, 0.90, 0.925, 0.95, 0.975, 0.99)
    max_lengths: tuple[int, ...] = (slots.MIN_SLOT_HOURS, 4, slots.MAX_SLOT_HOURS)
    cold_start_rounds: int = 200


def validate_table(table: pd.DataFrame) -> None:
    if table.empty or not assign_split(table.target_ts_utc).isin(["train", "val"]).all():
        raise ValueError("D+1 experiments accept development targets only")
    if table.y_price.isna().any() or not np.isfinite(table.y_price).all():
        raise ValueError("Missing/nonfinite development labels")
    if table.duplicated(["issue_ts", "target_ts_utc", "horizon_days"]).any():
        raise ValueError("Duplicate forecast keys")
    labels = table.groupby("target_ts_utc")[["y_price", "y_near_zero"]].nunique()
    if labels.gt(1).any().any() or not table.y_near_zero.eq(
            table.y_price.le(config.NEAR_ZERO_THRESHOLD_EUR)).all():
        raise ValueError("Inconsistent labels across forecasts")
    if not table.horizon_days.isin(config.HORIZONS_DAYS).all():
        raise ValueError("Invalid horizon")
    issue = table.issue_ts.dt.tz_convert(config.LOCAL_TZ)
    target = table.target_ts_utc.dt.tz_convert(config.LOCAL_TZ)
    difference = (target.dt.tz_localize(None).dt.normalize()
                  - issue.dt.tz_localize(None).dt.normalize()).dt.days
    if (not difference.eq(table.horizon_days).all()
            or not issue.dt.hour.eq(config.ISSUE_HOUR).all()
            or not issue.dt.minute.eq(0).all() or not issue.dt.second.eq(0).all()):
        raise ValueError("Invalid issue-time/horizon relationship")


def prediction_stages(table: pd.DataFrame, prediction_month: str) -> tuple[dict, dict]:
    """Fit < M-2, stop M-2, calibrate M-1, predict M. Purge all horizons together."""
    validate_table(table)
    month = pd.Period(prediction_month, freq="M")
    available = pd.period_range(config.VAL_START.date(), config.VAL_END.date(), freq="M")
    if month not in available:
        raise ValueError("Prediction month must be inside validation")
    local = table.target_ts_utc.dt.tz_convert(config.LOCAL_TZ)
    months = local.dt.tz_localize(None).dt.to_period("M")
    stages = {"fit": table[months < month - 2].copy(),
              "early_stop": table[months == month - 2].copy(),
              "calibration": table[months == month - 1].copy(),
              "prediction": table[months == month].copy()}
    purged = {}
    names = list(stages)
    for before, after in itertools.pairwise(names):
        if stages[after].empty:
            raise ValueError(f"Empty earlier/prediction stage: {after}")
        cutoff = stages[after].issue_ts.min().tz_convert(config.LOCAL_TZ).normalize()
        keep = stages[before].target_ts_utc.dt.tz_convert(config.LOCAL_TZ) < cutoff
        purged[before] = int((~keep).sum())
        stages[before] = stages[before][keep].copy()
    if any(part.empty for part in stages.values()):
        raise ValueError("Empty stage after label purging")
    empty = [name for name in feature_columns(stages["fit"])
             if not stages["fit"][name].notna().any()]
    stages = {name: part.drop(columns=empty) for name, part in stages.items()}
    metadata = {"prediction_month": str(month), "purged_rows": purged,
                "dropped_features": empty, "stages": {}}
    for name, part in stages.items():
        metadata["stages"][name] = {
            "targets": part.target_ts_utc.nunique(),
            "target_min": part.target_ts_utc.min().isoformat(),
            "target_max": part.target_ts_utc.max().isoformat(),
            "issue_min": part.issue_ts.min().isoformat(),
        }
    return stages, metadata


def history_before(predictions: dict[str, pd.DataFrame], score_month: str,
                   settings: Settings) -> pd.DataFrame:
    month = pd.Period(score_month, freq="M")
    names = [str(month - offset) for offset in range(settings.selection_months, 0, -1)]
    if any(name not in predictions for name in names) or score_month not in predictions:
        raise ValueError("Need all earlier out-of-sample policy months and later predictions")
    cutoff = predictions[score_month].issue_ts.min().tz_convert(config.LOCAL_TZ).normalize()
    history = pd.concat([predictions[name] for name in names], ignore_index=True)
    # End of each slot, rather than only its start, must precede scored issues.
    return history[history.slot_end_utc <= cutoff].reset_index(drop=True)


def fit_model(fit: pd.DataFrame, stop: pd.DataFrame, target: str, params: dict,
              half_life: float, settings: Settings, smoke: bool) -> tuple[lgb.LGBMClassifier, list, str]:
    if fit[target].nunique() != 2:
        raise ValueError("Earlier fitting data must contain both classes")
    features = [name for name in feature_columns(fit) if fit[name].notna().any()]
    options = dict(params)
    options["n_jobs"] = 1
    callbacks, kwargs, reason = [], {}, "earlier_block"
    if smoke:
        options["n_estimators"] = 8
    elif stop[target].nunique() != 2:
        options["n_estimators"] = settings.cold_start_rounds
        reason = "single-class earlier stop: predefined fixed rounds, not score-tuned"
    if stop[target].nunique() == 2:
        callbacks = [lgb.early_stopping(100, verbose=False)]
        kwargs = {"eval_X": (stop[features],), "eval_y": (stop[target].astype(int),)}
    weights = recency_weights(fit, half_life)
    if target == "y_slot":
        weights = weights * slots.date_weights(fit)
    model = lgb.LGBMClassifier(**options).fit(
        fit[features], fit[target].astype(int), sample_weight=weights, callbacks=callbacks, **kwargs)
    return model, features, reason


def positive_probability(model: lgb.LGBMClassifier, rows: pd.DataFrame) -> np.ndarray:
    """Binary predict_proba is dense; reject unexpected raw/multiclass outputs."""
    prediction = np.asarray(model.predict_proba(rows), dtype=float)
    if prediction.shape != (len(rows), 2) or not np.isfinite(prediction).all():
        raise ValueError("Expected finite binary probabilities")
    if not ((prediction >= 0) & (prediction <= 1)).all():
        raise ValueError("Invalid binary probabilities")
    return prediction[:, 1]


def calibrate_probability(raw_calibration: np.ndarray, calibration: pd.DataFrame,
                          raw_prediction: np.ndarray) -> tuple[np.ndarray, str]:
    eligible = calibration[calibration.quality_known]
    if eligible.empty or eligible.y_slot.nunique() != 2:
        # February has no near-zero hours. Do not fit unstable logits or substitute
        # later score labels; cold-start probability stays conservatively near zero.
        probability = float((eligible.y_slot.sum() + 1) / (len(eligible) + 2)) if len(eligible) else 0.0
        return np.full(len(raw_prediction), probability), "single-class/empty earlier calibration"
    mapping = slots.fit_mapping(raw_calibration, calibration)
    return slots.mapped_probability(mapping, raw_prediction), "earlier eligible date-weighted Platt"


def predict_month(table: pd.DataFrame, month: str, profile: str, settings: Settings,
                  smoke: bool = False) -> tuple[pd.DataFrame, pd.DataFrame, dict]:
    stages, metadata = prediction_stages(table, month)
    d1 = {name: part[part.horizon_days == 1].copy() for name, part in stages.items()}
    if any(part.empty for part in d1.values()):
        raise ValueError("Missing D+1 stage")
    options = dict(PROFILES[profile])
    options.pop("half_life_days")
    half_life = options.pop("step_half_lives")[NEAR_ZERO]
    params = DEFAULT_PARAMS | options
    candidate_frames = {name: slots.slot_table(part) for name, part in d1.items()}
    prediction = candidate_frames["prediction"].copy()
    calibration = candidate_frames["calibration"]
    classifications, models = [], {}
    for predictor in PREDICTORS:
        if predictor == "slot_d1":
            fit, stop, target = candidate_frames["fit"], candidate_frames["early_stop"], "y_slot"
        else:
            source = stages if predictor == "hourly_pooled" else d1
            fit, stop, target = source["fit"], source["early_stop"], "y_near_zero"
        model, features, reason = fit_model(fit, stop, target, params, half_life, settings, smoke)
        if predictor == "slot_d1":
            raw_calibration = positive_probability(model, calibration[features])
            raw_prediction = positive_probability(model, prediction[features])
        else:
            scores = {}
            for name in ("calibration", "prediction"):
                raw = pd.Series(positive_probability(model, d1[name][features]), index=d1[name].index)
                enriched = slots.slot_table(d1[name], raw)
                pd.testing.assert_frame_equal(enriched.drop(columns="hourly_min"), candidate_frames[name])
                scores[name] = enriched.hourly_min.to_numpy()
                if name == "prediction":
                    y = d1[name].y_near_zero.astype(int)
                    classifications.append(classification_report(y.to_numpy(), raw.to_numpy(), k=int(y.sum()))
                                           | {"predictor": predictor, "event": "hourly_raw",
                                              "n": len(y)})
            raw_calibration, raw_prediction = scores["calibration"], scores["prediction"]
        probability, calibration_reason = calibrate_probability(raw_calibration, calibration, raw_prediction)
        prediction[predictor] = probability
        eligible = prediction.quality_known
        if eligible.any():
            y = prediction.loc[eligible, "y_slot"].astype(int)
            classifications.append(classification_report(y.to_numpy(), probability[eligible], k=int(y.sum()))
                                   | {"predictor": predictor, "event": "whole_slot_eligible", "n": len(y)})
        models[predictor] = {"features": features, "fit_rows": len(fit),
                             "fit_horizons": sorted(int(h) for h in fit.horizon_days.unique()),
                             "best_iteration": model.best_iteration_, "params": model.get_params(),
                             "half_life_days": half_life, "stopping": reason,
                             "calibration": calibration_reason}
    return prediction, pd.DataFrame(classifications), metadata | {"models": models}


def choose_policy(history: pd.DataFrame, settings: Settings,
                  conservative: bool = True) -> tuple[dict | None, pd.DataFrame]:
    """Joint predictor/length/tau selection using ONLY prior forward predictions."""
    if history.empty or history.horizon_days.nunique() != 1 or not history.horizon_days.eq(1).all():
        raise ValueError("Policy history must contain D+1 slots")
    reports, accepted = [], []
    for predictor in PREDICTORS:
        for max_length in settings.max_lengths:
            candidates = history[history.length <= max_length]
            for tau in settings.thresholds:
                chosen = slots.plan_slots(candidates, candidates[predictor], tau)
                report = slots.outcomes(candidates, chosen)
                selected = candidates.loc[chosen]
                per_month = []
                for _, part in selected.groupby(pd.to_datetime(selected.date).dt.to_period("M")):
                    per_month.append(float(1 - part.y_slot.mean()))
                lower = slots.wilson_lower(report["successful_days"], report["active_days"], settings.confidence)
                admissible = bool(report["slots"] and report["cancellation_rate"] <= settings.max_cancellation)
                if conservative:
                    admissible = bool(admissible and report["active_days"] >= settings.min_support_days
                                      and len(per_month) >= settings.min_active_months
                                      and max(per_month) <= settings.max_cancellation
                                      and lower >= 1 - settings.max_cancellation)
                report |= {"predictor": predictor, "max_length": max_length, "tau": tau,
                           "active_months": len(per_month), "worst_month_cancellation": max(per_month) if per_month else None,
                           "day_hit_lower_bound": lower, "accepted": admissible,
                           "conservative": conservative}
                reports.append(report)
                if admissible:
                    accepted.append(report)
    best = (max(accepted, key=lambda row: (row["announced_hours"], row["day_hit_lower_bound"],
                                          -row["max_length"], row["tau"])) if accepted else None)
    policy = None if best is None else {key: best[key] for key in ("predictor", "max_length", "tau")}
    return policy, pd.DataFrame(reports)


def apply_policy(candidates: pd.DataFrame, policy: dict | None) -> list[int]:
    if policy is None:
        return []
    allowed = candidates[candidates.length <= policy["max_length"]]
    return slots.plan_slots(allowed, allowed[policy["predictor"]], policy["tau"])


def summary_report(policy: pd.DataFrame) -> pd.DataFrame:
    result = []
    for arm, group in policy.groupby("arm"):
        count = int(group.slots.sum())
        successes = float((group.slots * group.slot_hit_rate.fillna(0)).sum())
        cancelled = round(count - successes)
        days = int(group.active_days.sum())
        good_days = int(group.successful_days.sum())
        lower = slots.wilson_lower(good_days, days, Settings().confidence)
        opportunity = int(group.opportunity_days.sum())
        result.append({"arm": arm, "slots": count, "failed_slots": cancelled,
                       "cancellation_rate": cancelled / count if count else None,
                       "point_target_met": bool(count and cancelled / count <= slots.MAX_CANCELLATION),
                       "day_hit_lower_bound": lower, "active_days": days,
                       "mean_hours_per_month": float(group.announced_hours.mean()),
                       "abstaining_months": int(group.abstained.sum()),
                       "zero_offer_months": int(group.slots.eq(0).sum()),
                       "months_with_offers": int(group.slots.gt(0).sum()),
                       "months_above_target": int((group.cancellation_rate > slots.MAX_CANCELLATION).sum()),
                       "opportunity_day_capture": float(group.captured_opportunity_days.sum() / opportunity)
                       if opportunity else None,
                       "deployment_approved": False})
    return pd.DataFrame(result)


def prepare(queue: Path, output: Path, candidate: str | None = None) -> None:
    if output.exists():
        raise ValueError("Choose a new isolated run directory")
    original = json.loads((queue / "plan.json").read_text())
    verify_plan(queue, original)
    # Keep the previous experiment's fixed reference unless explicitly requested.
    reference = slots.choose_reference(queue, original, candidate or "weather_extra__chain_730_90")
    settings = Settings()
    months = default_score_months()
    history_start = pd.Period(months[0], freq="M") - settings.selection_months
    prediction_months = [str(month) for month in pd.period_range(history_start, months[-1], freq="M")]
    output.mkdir(parents=True)
    atomic_json(output / "plan.json", {"queue_dir": str(queue.resolve()), "reference": reference,
        "queue_plan_sha256": digest(queue / "plan.json"), "settings": asdict(settings),
        "implementation_sha256": {name: digest(Path(__file__).parent / name)
                                  for name in ("day_ahead_validation.py", "slot_validation.py")},
        "score_months": months, "prediction_months": prediction_months,
        "test_evaluated": False, "prepared_at_utc": pd.Timestamp.now(tz="UTC").isoformat()})
    print(f"Prepared D+1-only comparison: {prediction_months}; reference={reference['id']}", flush=True)


def verify(output: Path) -> tuple[dict, dict]:
    plan = json.loads((output / "plan.json").read_text())
    for name, checksum in plan["implementation_sha256"].items():
        if digest(Path(__file__).parent / name) != checksum:
            raise ValueError("Experiment code changed; prepare a new run")
    queue = Path(plan["queue_dir"])
    if digest(queue / "plan.json") != plan["queue_plan_sha256"]:
        raise ValueError("Original queue plan changed")
    original = json.loads((queue / "plan.json").read_text())
    verify_plan(queue, original)
    reference = plan["reference"]
    if digest(queue / "jobs" / reference["id"] / "classify.csv") != reference["reference_report_sha256"]:
        raise ValueError("Reference reports changed")
    return plan, original


def execute(output: Path, smoke: bool = False) -> None:
    plan, _ = verify(output)
    with (output / "run.lock").open("a") as lock:
        fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        try:
            _execute(output, plan, smoke)
        except Exception as error:
            atomic_json(output / "status.json", {"state": "failed", "smoke": smoke,
                "error": str(error), "test_evaluated": False})
            raise


def _execute(output: Path, plan: dict, smoke: bool) -> None:
    mode = "smoke" if smoke else "full"
    destination = output / mode
    if destination.exists():
        raise ValueError("Never overwrite partial or completed D+1 runs")
    if not smoke:
        marker_path = output / "smoke" / "completed.json"
        if not marker_path.exists():
            raise ValueError("Run the real-data smoke first")
        marker = json.loads(marker_path.read_text())
        if not marker["smoke_only"] or marker["test_evaluated"]:
            raise ValueError("Invalid smoke marker")
        for name, checksum in marker["report_sha256"].items():
            if digest(output / "smoke" / name) != checksum:
                raise ValueError("Smoke report checksum mismatch")
    destination.mkdir()
    source = Path(plan["queue_dir"]) / "inputs" / f"{plan['reference']['variant']}.parquet"
    table = pd.read_parquet(source)
    validate_table(table)
    settings = Settings(**(plan["settings"] | {"thresholds": tuple(plan["settings"]["thresholds"]),
                                               "max_lengths": tuple(plan["settings"]["max_lengths"])}))
    months = plan["prediction_months"][:settings.selection_months + 1] if smoke else plan["prediction_months"]
    predictions, metrics, metadata = {}, [], []
    for month in months:
        atomic_json(output / "status.json", {"state": "running", "prediction_month": month,
                                              "smoke": smoke, "test_evaluated": False})
        print(f"[D+1] forward prediction month={month}; smoke={smoke}", flush=True)
        frame, report, info = predict_month(table, month, plan["reference"]["profile"], settings, smoke)
        predictions[month] = frame
        metrics.append(report.assign(prediction_month=month))
        metadata.append(info)
        verify(output)
    score_months = plan["score_months"][:1] if smoke else plan["score_months"]
    policies, searches, decisions = [], [], []
    for month in score_months:
        history = history_before(predictions, month, settings)
        later = predictions[month]
        for conservative in (False, True):
            arm = "d1_conservative" if conservative else "d1_empirical_control"
            policy, report = choose_policy(history, settings, conservative)
            searches.append(report.assign(score_month=month, arm=arm))
            chosen = apply_policy(later, policy)
            result = slots.outcomes(later, chosen)
            policies.append(result | {"arm": arm, "score_month": month, "abstained": policy is None,
                "selected_predictor": None if policy is None else policy["predictor"],
                "tau": None if policy is None else policy["tau"],
                "max_length": None if policy is None else policy["max_length"],
                "history_start": str(history.date.min()), "history_end": str(history.date.max())})
            columns = slots.SLOT_KEY + ["date", "slot_end_utc", "y_slot", "quality_known"]
            decisions.append(later.loc[chosen, columns].assign(arm=arm, score_month=month))
        # Fixed, nonselected strict reference baseline: calibrated minimum hourly
        # probability >= .80, 2h slots. No score labels choose its predictor/threshold.
        baseline = {"predictor": "hourly_pooled", "tau": settings.thresholds[0],
                    "max_length": slots.MIN_SLOT_HOURS}
        chosen = apply_policy(later, baseline)
        policies.append(slots.outcomes(later, chosen) | {"arm": "hourly_pooled_fixed_2h",
            "score_month": month, "abstained": False, "selected_predictor": baseline["predictor"],
            "tau": baseline["tau"], "max_length": baseline["max_length"]})
    reports = {"policy_score": pd.DataFrame(policies), "selection": pd.concat(searches, ignore_index=True),
               "classification": pd.concat(metrics, ignore_index=True),
               "decisions": pd.concat(decisions, ignore_index=True)}
    reports["summary"] = summary_report(reports["policy_score"])
    reports["predictions"] = pd.concat([frame.assign(prediction_month=month)
                                        for month, frame in predictions.items()], ignore_index=True)
    hashes = {}
    for name, frame in reports.items():
        file = destination / f"{name}.csv"
        frame.to_csv(file, index=False)
        hashes[file.name] = digest(file)
    verify(output)
    atomic_json(destination / "completed.json", {"smoke_only": smoke, "test_evaluated": False,
        "production_artifacts_changed": False, "report_sha256": hashes, "prediction_folds": metadata,
        "score_months": score_months, "completed_at_utc": pd.Timestamp.now(tz="UTC").isoformat(),
        "caveats": ["Repeated development/postselected reference, not a fresh holdout.",
                    "Policy predictions are generated by earlier models/calibrators month by month.",
                    "Only D+1 outcomes enter policy selection/scoring; pooled model is a reference arm.",
                    "Month and day dependence invalidate an independent-sample safety interpretation.",
                    "Wilson bound is a selection heuristic, not certified risk control after search.",
                    "Zero announcements do not meet the business target with useful coverage.",
                    "Source publication assumptions are unchanged; final test remains untouched."]})
    atomic_json(output / "status.json", {"state": "smoke_passed" if smoke else "completed",
                                         "test_evaluated": False, "smoke": smoke})
    print(reports["summary"].to_string(index=False), flush=True)
    print(f"D+1 {mode} finished: {destination}", flush=True)


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--queue-dir", type=Path)
    parser.add_argument("--run-dir", type=Path, required=True)
    parser.add_argument("--candidate")
    action = parser.add_mutually_exclusive_group(required=True)
    action.add_argument("--prepare", action="store_true")
    action.add_argument("--smoke", action="store_true")
    action.add_argument("--execute", action="store_true")
    args = parser.parse_args(argv)
    if config.DATA_MODE != "real":
        parser.error("D+1 comparison requires real development data; final test is not supported")
    if args.prepare:
        if args.queue_dir is None:
            parser.error("--queue-dir required")
        prepare(args.queue_dir, args.run_dir, args.candidate)
    else:
        execute(args.run_dir, args.smoke)


if __name__ == "__main__":
    main()