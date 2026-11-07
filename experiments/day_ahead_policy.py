"""Policy-only D+1 stability comparison on verified saved forward predictions.

No retraining or holdout evaluation. Earlier risk evidence precedes volume in
selection; scoring-month labels never choose thresholds or predictor switches.
"""

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd

from experiments import day_ahead_validation as d1
from gridsense import config
from gridsense.models.chronological import digest
from gridsense.models.overnight import atomic_json
from gridsense.splits import assign_split

ARMS = ("fixed_d1_hourly_risk_first", "switching_d1_risk_first")


def verify_source(source: Path) -> dict:
    plan, _ = d1.verify(source)
    marker = json.loads((source / "full" / "completed.json").read_text())
    if marker["smoke_only"] or marker["test_evaluated"] or marker["production_artifacts_changed"]:
        raise ValueError("Require a full development-only unchanged-model source run")
    if marker["score_months"] != plan["score_months"]:
        raise ValueError("Source completion has different scoring months")
    for name, checksum in marker["report_sha256"].items():
        if digest(source / "full" / name) != checksum:
            raise ValueError("Source report checksum mismatch")
    return plan


def read_predictions(source: Path, source_plan: dict) -> dict[str, pd.DataFrame]:
    columns = d1.slots.SLOT_KEY + ["date", "slot_end_utc", "start_hour", "quality_known", "y_slot",
                                  "near_zero_hours", "excess_sum", "prediction_month", *d1.PREDICTORS]
    table = pd.read_csv(source / "full" / "predictions.csv", usecols=columns)
    for name in ("issue_ts", "target_ts_utc", "slot_end_utc"):
        table[name] = pd.to_datetime(table[name], utc=True)
    table["date"] = pd.to_datetime(table.date).dt.date
    if (table.empty or not table.horizon_days.eq(1).all()
            or not assign_split(table.target_ts_utc).eq("val").all()
            or table.duplicated(d1.slots.SLOT_KEY).any()):
        raise ValueError("Source predictions must contain unique validation-only D+1 slot keys")
    target_local = table.target_ts_utc.dt.tz_convert(config.LOCAL_TZ)
    issue_local = table.issue_ts.dt.tz_convert(config.LOCAL_TZ)
    lead = (target_local.dt.tz_localize(None).dt.normalize()
            - issue_local.dt.tz_localize(None).dt.normalize()).dt.days
    if (not lead.eq(1).all() or not issue_local.dt.hour.eq(config.ISSUE_HOUR).all()
            or not target_local.dt.date.eq(table.date).all()
            or not target_local.dt.strftime("%Y-%m").eq(table.prediction_month).all()
            or not table.slot_end_utc.eq(table.target_ts_utc + pd.to_timedelta(table.length, unit="h")).all()
            or not table.length.between(d1.slots.MIN_SLOT_HOURS, d1.slots.MAX_SLOT_HOURS).all()):
        raise ValueError("Invalid saved slot timing")
    if not table.quality_known.isin([True, False]).all() or not table.y_slot.isin([True, False]).all():
        raise ValueError("Quality and labels must be booleans")
    probabilities = table[list(d1.PREDICTORS)].to_numpy(dtype=float)
    if not np.isfinite(probabilities).all() or not ((probabilities >= 0) & (probabilities <= 1)).all():
        raise ValueError("Invalid saved predictor probabilities")
    result = {str(month): part.reset_index(drop=True) for month, part in table.groupby("prediction_month")}
    if set(result) != set(source_plan["prediction_months"]):
        raise ValueError("Incomplete saved prediction months")
    return result


def risk_first_select(history: pd.DataFrame, settings: d1.Settings, arm: str,
                      min_hours_per_month: float) -> tuple[dict | None, pd.DataFrame]:
    if arm not in ARMS or min_hours_per_month < 0:
        raise ValueError("Invalid policy arm or volume requirement")
    _, evidence = d1.choose_policy(history, settings, conservative=True)
    predictors = ("hourly_d1",) if arm == ARMS[0] else ("hourly_d1", "slot_d1")
    evidence = evidence[(evidence.predictor.isin(predictors))
                        & evidence.max_length.eq(d1.slots.MIN_SLOT_HOURS)].copy()
    evidence["mean_selection_hours_per_month"] = evidence.announced_hours / settings.selection_months
    evidence["volume_supported"] = evidence.mean_selection_hours_per_month >= min_hours_per_month
    evidence["accepted"] &= evidence.volume_supported
    accepted = evidence[evidence.accepted]
    if accepted.empty:
        return None, evidence
    # Rank safety before utility. Prefer the stable hourly model only when all
    # risk/volume criteria tie; selection never inspects the later score month.
    best = min(accepted.to_dict("records"), key=lambda row: (
        row["worst_month_cancellation"], row["cancellation_rate"], -row["day_hit_lower_bound"],
        -row["mean_selection_hours_per_month"], row["predictor"] != "hourly_d1", -row["tau"]))
    return {key: best[key] for key in ("predictor", "max_length", "tau")}, evidence


def add_volume_metrics(report: pd.DataFrame, policy: pd.DataFrame,
                       min_hours_per_month: float) -> pd.DataFrame:
    result = report.copy()
    result["minimum_hours_benchmark"] = min_hours_per_month
    result["mean_volume_benchmark_met"] = result.mean_hours_per_month >= min_hours_per_month
    result["months_below_volume_benchmark"] = result.arm.map(
        policy.groupby("arm").announced_hours.apply(lambda values: int((values < min_hours_per_month).sum())))
    result["every_month_empirical_safety_and_volume"] = (
        result.point_target_met & result.months_above_target.eq(0)
        & result.months_below_volume_benchmark.eq(0))
    return result


def run(source: Path, output: Path, min_hours_per_month: float = 20.0) -> None:
    if output.exists() or not np.isfinite(min_hours_per_month) or min_hours_per_month < 0:
        raise ValueError("Choose a new run directory and finite nonnegative volume benchmark")
    source_plan = verify_source(source)
    settings = d1.Settings(**(source_plan["settings"] | {
        "thresholds": tuple(source_plan["settings"]["thresholds"]),
        "max_lengths": tuple(source_plan["settings"]["max_lengths"])}))
    # Freeze before loading/scoring the outcomes; never update prior run plans.
    output.mkdir(parents=True)
    plan = {"source_dir": str(source.resolve()), "source_plan_sha256": digest(source / "plan.json"),
            "source_completion_sha256": digest(source / "full" / "completed.json"),
            "implementation_sha256": digest(Path(__file__)), "arms": ARMS,
            "min_hours_per_month": min_hours_per_month, "settings": source_plan["settings"],
            "score_months": source_plan["score_months"], "test_evaluated": False,
            "prepared_at_utc": pd.Timestamp.now(tz="UTC").isoformat()}
    atomic_json(output / "plan.json", plan)
    atomic_json(output / "status.json", {"state": "running", "test_evaluated": False})
    try:
        predictions = read_predictions(source, source_plan)
        policies, searches, decisions, frontier = [], [], [], []
        for month in source_plan["score_months"]:
            history = d1.history_before(predictions, month, settings)
            later = predictions[month]
            for arm in ARMS:
                policy, evidence = risk_first_select(history, settings, arm, min_hours_per_month)
                searches.append(evidence.assign(arm=arm, score_month=month))
                chosen = d1.apply_policy(later, policy)
                policies.append(d1.slots.outcomes(later, chosen) | {
                    "arm": arm, "score_month": month, "abstained": policy is None,
                    "predictor": None if policy is None else policy["predictor"],
                    "tau": None if policy is None else policy["tau"],
                    "max_length": None if policy is None else policy["max_length"],
                    "history_end": str(history.date.max())})
                taken = later.loc[chosen, d1.slots.SLOT_KEY + ["slot_end_utc", "date", "quality_known", "y_slot"]]
                decisions.append(taken.assign(arm=arm, score_month=month))
            # A bounded descriptive frontier, never used to select or promote a
            # policy. Thresholds are the predeclared source grid, not a new sweep.
            for predictor in ("hourly_d1", "slot_d1"):
                for tau in settings.thresholds:
                    chosen = d1.apply_policy(later, {"predictor": predictor,
                        "tau": tau, "max_length": d1.slots.MIN_SLOT_HOURS})
                    frontier.append(d1.slots.outcomes(later, chosen) | {
                        "arm": f"{predictor}_fixed_tau_{tau}", "score_month": month,
                        "predictor": predictor, "tau": tau, "abstained": False,
                        "descriptive_only": True})
        old = pd.read_csv(source / "full" / "policy_score.csv")
        prior = old[old.arm == "d1_conservative"].copy()
        prior["arm"] = "previous_switching_volume_first"
        score = pd.concat([pd.DataFrame(policies), prior], ignore_index=True)
        frontier = pd.DataFrame(frontier)
        reports = {"policy_score": score, "selection": pd.concat(searches, ignore_index=True),
                   "decisions": pd.concat(decisions, ignore_index=True),
                   "summary": add_volume_metrics(d1.summary_report(score), score, min_hours_per_month),
                   "frontier_by_month": frontier,
                   "frontier_summary": add_volume_metrics(d1.summary_report(frontier), frontier, min_hours_per_month)}
        hashes = {}
        for name, frame in reports.items():
            file = output / f"{name}.csv"
            frame.to_csv(file, index=False)
            hashes[file.name] = digest(file)
        verify_source(source)
        if digest(source / "plan.json") != plan["source_plan_sha256"]:
            raise ValueError("Source plan changed during comparison")
        atomic_json(output / "completed.json", {"test_evaluated": False,
            "production_artifacts_changed": False, "models_retrained": False,
            "report_sha256": hashes, "score_months": source_plan["score_months"],
            "completed_at_utc": pd.Timestamp.now(tz="UTC").isoformat(),
            "caveats": ["Reused explored development predictions, not fresh holdout evidence.",
                        "20 hours/month is a provisional usefulness benchmark, not a proven business requirement.",
                        "Risk bounds are day-cluster heuristics, not certified post-selection guarantees.",
                        "Fixed-threshold frontier is descriptive; do not choose a winner using scored labels.",
                        "Previous policy permits longer slots; compare risk/volume, not architecture causality.",
                        "June cold-start abstention and months without offers count against useful coverage.",
                        "No automatic promotion, model replacement or final-test evaluation."]})
        atomic_json(output / "status.json", {"state": "completed", "test_evaluated": False})
        print(reports["summary"].to_string(index=False))
        print(f"Policy-only comparison complete: {output}; no retraining")
    except Exception as error:
        atomic_json(output / "status.json", {"state": "failed", "error": str(error), "test_evaluated": False})
        raise


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-dir", type=Path, required=True)
    parser.add_argument("--run-dir", type=Path, required=True)
    parser.add_argument("--min-hours-per-month", type=float, default=20.0)
    args = parser.parse_args(argv)
    if config.DATA_MODE != "real":
        parser.error("Only real development predictions; final-test mode does not exist")
    run(args.source_dir, args.run_dir, args.min_hours_per_month)


if __name__ == "__main__":
    main()