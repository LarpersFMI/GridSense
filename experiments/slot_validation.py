"""Whole-slot prediction versus the strongest completed hourly development candidate.

Run with ``uv run python -m experiments.slot_validation``. This intentionally lives
outside src/gridsense: adding it does not invalidate an executing overnight queue.
It reads verified development snapshots only and never saves production models.
"""

import argparse
import json
import warnings
from dataclasses import asdict, dataclass
from pathlib import Path
from statistics import NormalDist

import lightgbm as lgb
import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression

from gridsense import config
from gridsense.models.base import feature_columns, recency_weights
from gridsense.models.chronological import (
    MAX_CANCELLATION,
    PROFILES,
    TAUS,
    digest,
    month_fold,
)
from gridsense.models.classify import DEFAULT_PARAMS, NEAR_ZERO, LowPriceClassifier
from gridsense.models.error_analysis import (
    MAX_SLOT_HOURS,
    MAX_SLOTS_PER_DAY,
    MIN_SLOT_HOURS,
    MONTHLY_BUDGET_HOURS,
    SLOT_HOURS,
)
from gridsense.models.metrics import classification_report
from gridsense.models.overnight import atomic_json, valid_completion, verify_plan
from gridsense.splits import assign_split

SLOT_KEY = ["issue_ts", "target_ts_utc", "horizon_days", "length"]
ARMS = ("hourly_empirical", "hourly_conservative", "slot_empirical", "slot_conservative")


@dataclass(frozen=True)
class PolicySettings:
    """Experiment knobs; business threshold, slot hours and budgets remain canonical."""

    max_cancellation: float = MAX_CANCELLATION
    confidence: float = 0.90
    min_support_days: int = 15
    min_probability: float = 0.80


def slot_table(rows: pd.DataFrame, hourly_probability: pd.Series | None = None) -> pd.DataFrame:
    """Aggregate issue-known f_* inputs; labels are isolated from model features.

    Missing hours invalidate a window. Missing feature values remain NaN; no weather
    observations or price labels are used to fill them. No fitted hourly predictions
    enter slot-model fitting, so no stacking/in-sample prediction leakage is possible.
    """
    if rows.empty or not assign_split(rows.target_ts_utc).isin(["train", "val"]).all():
        raise ValueError("Slots require nonempty development rows only")
    if not rows.index.is_unique:
        raise ValueError("Hourly row indices must be unique")
    if rows.y_price.isna().any() or not np.isfinite(rows.y_price).all():
        raise ValueError("Slot labels must be finite")
    local = rows.target_ts_utc.dt.tz_convert(config.LOCAL_TZ)
    issue = rows.issue_ts.dt.tz_convert(config.LOCAL_TZ)
    lead = (local.dt.tz_localize(None).dt.normalize()
            - issue.dt.tz_localize(None).dt.normalize()).dt.days
    if (not lead.eq(rows.horizon_days).all()
            or not rows.horizon_days.isin(config.HORIZONS_DAYS).all()
            or not issue.dt.hour.eq(config.ISSUE_HOUR).all()
            or not issue.dt.minute.eq(0).all() or not issue.dt.second.eq(0).all()
            or not local.dt.minute.eq(0).all() or not local.dt.second.eq(0).all()):
        raise ValueError("Invalid forecast issue/horizon/hour key")
    if rows.duplicated(["issue_ts", "target_ts_utc", "horizon_days"]).any():
        raise ValueError("Duplicate forecast keys")
    if rows.groupby("target_ts_utc").y_price.nunique().gt(1).any():
        raise ValueError("Conflicting repeated target prices")
    features = feature_columns(rows)
    frame = rows.assign(date=local.dt.date, hour=local.dt.hour)
    frame = frame[frame.hour.isin(SLOT_HOURS)].copy()
    if frame.empty:
        raise ValueError("No delivery hours in the configured slot window")
    keys = pd.MultiIndex.from_frame(frame[["issue_ts", "horizon_days", "date"]])
    groups, unique = pd.factorize(keys, sort=True)
    unique = unique.set_names(["issue_ts", "horizon_days", "date"])
    hour_index = frame.hour.to_numpy() - SLOT_HOURS[0]
    shape = (len(unique), len(SLOT_HOURS))
    present = np.zeros(shape, dtype=bool)
    present[groups, hour_index] = True
    values = np.full((*shape, len(features)), np.nan)
    numeric = frame[features].to_numpy(dtype=float)
    if np.isinf(numeric).any():
        raise ValueError("Infinite feature values")
    values[groups, hour_index] = numeric
    prices = np.full(shape, np.nan)
    prices[groups, hour_index] = frame.y_price.to_numpy()
    quality = np.zeros(shape, dtype=bool)
    known = (frame.data_quality.eq("ok").to_numpy() if "data_quality" in frame
             else np.zeros(len(frame), dtype=bool))
    quality[groups, hour_index] = known & np.isfinite(numeric).all(axis=1)
    timestamps = np.empty(shape, dtype=object)
    timestamps[:] = None
    timestamps[groups, hour_index] = frame.target_ts_utc.to_numpy()
    probabilities = np.full(shape, np.nan)
    if hourly_probability is not None:
        if not hourly_probability.index.equals(rows.index):
            raise ValueError("Hourly predictions must align exactly with input rows")
        if not hourly_probability.between(0, 1).all():
            raise ValueError("Hourly predictions must be finite probabilities")
        probabilities[groups, hour_index] = hourly_probability.loc[frame.index].to_numpy()
    base = unique.to_frame(index=False)
    aggregate_names = [f"f_slot_{name[2:]}_{stat}" for stat in ("mean", "min", "max")
                       for name in features]
    parts = []
    for start in range(len(SLOT_HOURS)):
        for length in range(MIN_SLOT_HOURS, MAX_SLOT_HOURS + 1):
            end = start + length
            if end > len(SLOT_HOURS):
                continue
            valid = present[:, start:end].all(axis=1)
            if not valid.any():
                continue
            block = values[valid, start:end]
            with warnings.catch_warnings():
                warnings.simplefilter("ignore", RuntimeWarning)
                aggregated = np.concatenate([function(block, axis=1) for function in
                                             (np.nanmean, np.nanmin, np.nanmax)], axis=1)
            part = pd.DataFrame(aggregated, columns=aggregate_names)
            metadata = base.loc[valid].reset_index(drop=True)
            for name in metadata:
                part[name] = metadata[name]
            part["target_ts_utc"] = pd.DatetimeIndex(timestamps[valid, start])
            part["slot_end_utc"] = part.target_ts_utc + pd.Timedelta(hours=length)
            part["start_hour"] = SLOT_HOURS[start]
            part["length"] = length
            part["f_slot_length"] = length
            part["f_slot_start_hour"] = SLOT_HOURS[start]
            actual = prices[valid, start:end]
            near = actual <= config.NEAR_ZERO_THRESHOLD_EUR
            part["y_slot"] = near.all(axis=1)
            part["near_zero_hours"] = near.sum(axis=1)
            part["excess_sum"] = np.maximum(actual - config.NEAR_ZERO_THRESHOLD_EUR, 0).sum(axis=1)
            part["quality_known"] = quality[valid, start:end].all(axis=1)
            if hourly_probability is not None:
                part["hourly_min"] = probabilities[valid, start:end].min(axis=1)
            parts.append(part)
    if not parts:
        raise ValueError("No complete candidate slots")
    result = pd.concat(parts, ignore_index=True).sort_values(SLOT_KEY).reset_index(drop=True)
    if result.duplicated(SLOT_KEY).any():
        raise ValueError("Duplicate slot keys")
    return result


def date_weights(slots: pd.DataFrame) -> np.ndarray:
    """Give each delivery date equal total weight, despite overlapping/repeated slots."""
    counts = slots.groupby("date").date.transform("size").to_numpy(dtype=float)
    weights = 1 / counts
    return weights / weights.mean()


def fit_mapping(probability: np.ndarray, slots: pd.DataFrame) -> LogisticRegression:
    eligible = slots.quality_known.to_numpy(dtype=bool)
    selected = slots.loc[eligible]
    if selected.y_slot.nunique() != 2:
        raise ValueError("Eligible earlier calibration slots must have both classes")
    p = np.clip(np.asarray(probability)[eligible], 1e-7, 1 - 1e-7)
    return LogisticRegression(C=1.0, random_state=config.RANDOM_SEED).fit(
        np.log(p / (1 - p))[:, None], selected.y_slot.astype(int),
        sample_weight=date_weights(selected))


def mapped_probability(mapping: LogisticRegression, probability: np.ndarray) -> np.ndarray:
    p = np.clip(np.asarray(probability), 1e-7, 1 - 1e-7)
    return mapping.predict_proba(np.log(p / (1 - p))[:, None])[:, 1]


def plan_slots(slots: pd.DataFrame, probability: pd.Series, tau: float) -> list[int]:
    """Causal per-horizon replay: rank only slots available at the current daily issue.

    The monthly cap resets by target month. Labels/outcomes are not read here.
    Both predictors and both policies use identical strict data-quality eligibility.
    """
    if slots.horizon_days.nunique() != 1:
        raise ValueError("Replay each horizon separately; horizons are alternative outlooks")
    if not probability.index.equals(slots.index) or not probability.between(0, 1).all():
        raise ValueError("Slot probabilities must align and be finite")
    if slots.duplicated(SLOT_KEY).any():
        raise ValueError("Duplicate slot keys")
    allowed = slots.quality_known & probability.ge(tau)
    # Deliberately exclude truth columns from planning.
    ranked = slots.loc[allowed, ["issue_ts", "date", "start_hour", "length"]].copy()
    ranked["probability"] = probability.loc[ranked.index]
    ranked = ranked.sort_values(["issue_ts", "probability", "length", "start_hour"],
                                ascending=[True, False, False, True])
    chosen, budgets, occupied = [], {}, {}
    for index, row in ranked.iterrows():
        month = (row.date.year, row.date.month)
        blocks = occupied.setdefault(row.date, [])
        start, end = int(row.start_hour), int(row.start_hour + row.length)
        if (budgets.get(month, 0) + row.length > MONTHLY_BUDGET_HOURS
                or len(blocks) >= MAX_SLOTS_PER_DAY
                or any(start < previous_end and previous_start < end
                       for previous_start, previous_end in blocks)):
            continue
        chosen.append(index)
        blocks.append((start, end))
        budgets[month] = budgets.get(month, 0) + int(row.length)
    return chosen


def wilson_lower(successes: int, total: int, confidence: float) -> float:
    """One-sided, day-cluster Wilson heuristic; not a post-selection safety guarantee."""
    if not 0 < confidence < 1 or not 0 <= successes <= total:
        raise ValueError("Invalid confidence/counts")
    if not total:
        return 0.0
    z = NormalDist().inv_cdf(confidence)
    rate = successes / total
    return float((rate + z * z / (2 * total)
                  - z * np.sqrt(rate * (1 - rate) / total + z * z / (4 * total * total)))
                 / (1 + z * z / total))


def outcomes(slots: pd.DataFrame, chosen: list[int]) -> dict:
    selected = slots.loc[chosen]
    days = selected.groupby("date").y_slot.all()
    return {"slots": len(selected), "announced_hours": int(selected.length.sum()),
            "slot_hit_rate": float(selected.y_slot.mean()) if len(selected) else None,
            "cancellation_rate": float(1 - selected.y_slot.mean()) if len(selected) else None,
            "slot_hour_precision": (float(selected.near_zero_hours.sum() / selected.length.sum())
                                    if len(selected) else None),
            "excess_eur_per_mwh": (float(selected.excess_sum.sum() / selected.length.sum())
                                   if len(selected) else None),
            "active_days": len(days), "successful_days": int(days.sum()),
            "eligible_candidate_slots": int(slots.quality_known.sum()),
            "candidate_slots": len(slots),
            "opportunity_days": int(slots[slots.quality_known & slots.y_slot].date.nunique()),
            "captured_opportunity_days": int(selected[selected.y_slot].date.nunique())}


def select_threshold(slots: pd.DataFrame, probability: pd.Series, conservative: bool,
                     settings: PolicySettings) -> tuple[float | None, list[dict]]:
    """Use earlier selection labels only; enforce evidence/quality gates or abstain."""
    options, reports = [], []
    midpoint = sorted(slots.date.unique())[len(slots.date.unique()) // 2]
    for tau in TAUS:
        if conservative and tau < settings.min_probability:
            continue
        chosen = plan_slots(slots, probability, tau)
        report = outcomes(slots, chosen) | {"tau": tau}
        lower = wilson_lower(report["successful_days"], report["active_days"], settings.confidence)
        selected = slots.loc[chosen]
        halves = [selected[selected.date < midpoint], selected[selected.date >= midpoint]]
        stable = all(len(half) and 1 - half.y_slot.mean() <= settings.max_cancellation
                     for half in halves)
        acceptable = bool(report["slots"] and report["cancellation_rate"] <= settings.max_cancellation)
        if conservative:
            acceptable = bool(acceptable and stable
                              and report["active_days"] >= settings.min_support_days
                              and lower >= 1 - settings.max_cancellation)
        report |= {"day_hit_lower_bound": lower, "stable_halves": bool(stable),
                   "accepted": acceptable, "conservative": conservative}
        reports.append(report)
        if acceptable:
            options.append(report)
        best = (max(options, key=lambda row: (row["announced_hours"], row["slot_hit_rate"], row["tau"]))
            if options else None)
    return (None if best is None else best["tau"]), reports


def compare_fold(stages: dict, profile: str, settings: PolicySettings,
                 smoke: bool = False) -> tuple[dict[str, pd.DataFrame], dict]:
    options = dict(PROFILES[profile])
    half_life = options.pop("half_life_days")
    step_half_lives = options.pop("step_half_lives")
    options["n_jobs"] = 1
    if smoke:
        options["n_estimators"] = 8
    hourly = LowPriceClassifier(params=DEFAULT_PARAMS | options, half_life_days=half_life,
                                step_half_lives=step_half_lives, calibration=None)
    hourly.fit(stages["fit"], stages["early_stop"])
    slots = {name: slot_table(rows) for name, rows in stages.items()}
    features = [name for name in feature_columns(slots["fit"])
                if slots["fit"][name].notna().any()]
    fit, stop, calib = (slots[name] for name in ("fit", "early_stop", "calibration"))
    if fit.y_slot.nunique() != 2 or stop.y_slot.nunique() != 2:
        raise ValueError("Slot fit/early-stop blocks require both classes")
    model = lgb.LGBMClassifier(**(DEFAULT_PARAMS | options))
    # Near-zero step's effective recency is the matched whole-slot recency control.
    weights = recency_weights(fit, step_half_lives[NEAR_ZERO]) * date_weights(fit)
    model.fit(fit[features], fit.y_slot.astype(int), sample_weight=weights,
              eval_set=[(stop[features], stop.y_slot.astype(int))],
              callbacks=[lgb.early_stopping(100, verbose=False)])
    for name in ("calibration", "selection", "score"):
        raw = hourly.predict(stages[name], apply_calibration=False).p_near_zero
        enriched = slot_table(stages[name], raw)
        pd.testing.assert_frame_equal(enriched.drop(columns="hourly_min"), slots[name])
        slots[name] = enriched
    mappings = {
        "hourly": fit_mapping(slots["calibration"].hourly_min.to_numpy(), calib),
        "slot": fit_mapping(model.predict_proba(calib[features])[:, 1], calib),
    }
    probabilities = {}
    for name in ("selection", "score"):
        rows = slots[name]
        probabilities[name] = {
            "hourly": pd.Series(mapped_probability(mappings["hourly"], rows.hourly_min.to_numpy()),
                                index=rows.index),
            "slot": pd.Series(mapped_probability(mappings["slot"],
                                                  model.predict_proba(rows[features])[:, 1]),
                              index=rows.index),
        }
    metrics, policy_scores, searches, decisions = [], [], [], []
    score = slots["score"]
    for predictor in ("hourly", "slot"):
        for horizon, index in score.groupby("horizon_days").groups.items():
            for scope, keep in (("all", pd.Series(True, index=index)),
                                ("eligible", score.loc[index, "quality_known"])):
                selected_index = keep[keep].index
                if len(selected_index):
                    y = score.loc[selected_index, "y_slot"].astype(int)
                    metrics.append(classification_report(
                        y, probabilities["score"][predictor].loc[selected_index], k=int(y.sum()))
                        | {"predictor": predictor, "horizon": int(horizon), "scope": scope,
                           "candidate_slots": len(y)})
        for conservative in (False, True):
            arm = f"{predictor}_{'conservative' if conservative else 'empirical'}"
            for horizon, selection in slots["selection"].groupby("horizon_days"):
                p = probabilities["selection"][predictor].loc[selection.index]
                tau, candidates = select_threshold(selection, p, conservative, settings)
                searches.extend(row | {"arm": arm, "horizon": int(horizon)} for row in candidates)
                later = score[score.horizon_days == horizon]
                chosen = ([] if tau is None else plan_slots(
                    later, probabilities["score"][predictor].loc[later.index], tau))
                policy_scores.append(outcomes(later, chosen) | {"arm": arm,
                    "horizon": int(horizon), "tau": tau, "abstained": tau is None,
                    "reason": "no earlier policy passed gates" if tau is None else "selected earlier"})
                taken = later.loc[chosen, SLOT_KEY + ["slot_end_utc", "date", "quality_known", "y_slot"]]
                decisions.append(taken.assign(arm=arm, probability=probabilities["score"][predictor].loc[chosen]))
    reports = {"classification": pd.DataFrame(metrics), "policy_score": pd.DataFrame(policy_scores),
               "selection": pd.DataFrame(searches), "decisions": pd.concat(decisions, ignore_index=True)}
    return reports, {"slot_features": features, "slot_best_iteration": model.best_iteration_,
                     "hourly_best_iterations": hourly.best_iterations(),
                     "hourly_params": hourly.params, "slot_params": model.get_params(),
                     "slot_half_life_days": step_half_lives[NEAR_ZERO],
                     "stage_candidate_counts": {name: len(part) for name, part in slots.items()},
                     "calibration": "eligible whole-slot outcomes, date-weighted Platt for both arms"}


def choose_reference(queue: Path, plan: dict, candidate: str | None = None) -> dict:
    """Freeze a provisional completed candidate. This is post-selection development evidence."""
    candidates = []
    for job in plan["jobs"]:
        directory = queue / "jobs" / job["id"]
        if candidate is not None and job["id"] != candidate:
            continue
        if not (directory / "completed.json").is_file():
            continue
        if not valid_completion(directory, plan["snapshot_sha256"][job["variant"]],
                                months=plan["months"], profile=job["profile"], smoke=False):
            continue
        report = pd.read_csv(directory / "classify.csv")
        near = report[(report.horizon == "all") & (report.label == "y_near_zero")
                      & (report.model == "lgbm_platt_forward")]
        if len(near) != len(plan["months"]):
            raise ValueError("Incomplete reference scoring months")
        candidates.append(job | {"mean_monthly_pr_auc": float(near.pr_auc.mean()),
                                 "mean_monthly_brier": float(near.brier.mean()),
                                 "reference_report_sha256": digest(directory / "classify.csv")})
    if not candidates:
        raise ValueError("No verified completed hourly reference is available")
    best = max(candidates, key=lambda row: (row["mean_monthly_pr_auc"], -row["mean_monthly_brier"]))
    return best | {"completed_candidates_considered": len(candidates)}


def prepare(queue: Path, output: Path, settings: PolicySettings, candidate: str | None) -> dict:
    if output.exists() or queue.resolve() == output.resolve():
        raise ValueError("Choose a new isolated run directory")
    source_plan = json.loads((queue / "plan.json").read_text())
    verify_plan(queue, source_plan)
    reference = choose_reference(queue, source_plan, candidate)
    plan = {"queue_dir": str(queue.resolve()), "queue_plan_sha256": digest(queue / "plan.json"),
            "experiment_sha256": digest(Path(__file__)), "reference": reference,
            "policy_settings": asdict(settings), "months": source_plan["months"],
            "prepared_at_utc": pd.Timestamp.now(tz="UTC").isoformat(), "test_evaluated": False}
    output.mkdir(parents=True)
    atomic_json(output / "plan.json", plan)
    print(f"Frozen provisional reference: {reference['id']}; {output}", flush=True)
    return plan


def comparison_summary(classification: pd.DataFrame, policy: pd.DataFrame) -> pd.DataFrame:
    """Show utility alongside safety; zero offers never count as perfect performance."""
    result = []
    for arm, group in policy.groupby("arm"):
        predictor = arm.split("_")[0]
        scores = classification[(classification.predictor == predictor)
                                & (classification.scope == "eligible")]
        count = int(group.slots.sum())
        hits = float((group.slot_hit_rate.fillna(0) * group.slots).sum())
        opportunities = int(group.opportunity_days.sum())
        result.append({
            "arm": arm, "mean_month_horizon_pr_auc": float(scores.pr_auc.mean()),
            "eligible_brier": float(np.average(scores.brier, weights=scores.candidate_slots))
            if len(scores) else None,
            "slots": count, "cancellation_rate": 1 - hits / count if count else None,
            "mean_hours_per_horizon_month": float(group.announced_hours.mean()),
            "abstaining_horizon_months": int(group.abstained.sum()),
            "zero_offer_horizon_months": int(group.slots.eq(0).sum()),
            "opportunity_day_capture": (float(group.captured_opportunity_days.sum() / opportunities)
                                        if opportunities else None),
        })
    return pd.DataFrame(result)


def run(output: Path, smoke: bool = False) -> None:
    plan = json.loads((output / "plan.json").read_text())
    queue = Path(plan["queue_dir"])
    if plan["experiment_sha256"] != digest(Path(__file__)):
        raise ValueError("Experiment implementation changed; prepare a new run")
    if digest(queue / "plan.json") != plan["queue_plan_sha256"]:
        raise ValueError("Original queue plan changed")
    original = json.loads((queue / "plan.json").read_text())
    reference = plan["reference"]
    if digest(queue / "jobs" / reference["id"] / "classify.csv") != reference["reference_report_sha256"]:
        raise ValueError("Reference report changed")
    verify_plan(queue, original)
    mode = "smoke" if smoke else "full"
    destination = output / mode
    if destination.exists():
        raise ValueError("Run output already exists; do not overwrite a completed/partial experiment")
    if not smoke and not (output / "smoke" / "completed.json").is_file():
        raise ValueError("Run the isolated smoke before full execution")
    if not smoke:
        marker = json.loads((output / "smoke" / "completed.json").read_text())
        if not marker["smoke_only"] or marker["test_evaluated"]:
            raise ValueError("Invalid smoke completion")
        for name, checksum in marker["report_sha256"].items():
            if digest(output / "smoke" / name) != checksum:
                raise ValueError("Smoke report checksum mismatch")
    table = pd.read_parquet(queue / "inputs" / f"{reference['variant']}.parquet")
    months = plan["months"][:1] if smoke else plan["months"]
    destination.mkdir()
    reports, metadata = {}, []
    for month in months:
        atomic_json(output / "status.json", {"state": "running", "month": month, "smoke": smoke})
        print(f"[slot-validation] {reference['id']} / {month}; smoke={smoke}", flush=True)
        stages, protocol = month_fold(table, month)
        result, info = compare_fold(stages, reference["profile"],
                                    PolicySettings(**plan["policy_settings"]), smoke)
        metadata.append(protocol | info)
        for name, frame in result.items():
            reports.setdefault(name, []).append(frame.assign(score_month=month))
        verify_plan(queue, original)
    combined = {name: pd.concat(frames, ignore_index=True) for name, frames in reports.items()}
    combined["summary"] = comparison_summary(combined["classification"], combined["policy_score"])
    hashes = {}
    for name, frame in combined.items():
        path = destination / f"{name}.csv"
        frame.to_csv(path, index=False)
        hashes[path.name] = digest(path)
    atomic_json(destination / "completed.json", {
        "test_evaluated": False, "production_artifacts_changed": False, "smoke_only": smoke,
        "completed_at_utc": pd.Timestamp.now(tz="UTC").isoformat(), "folds": metadata,
        "reference": reference, "report_sha256": hashes,
        "caveats": [
            "Reference chosen using already-explored development score months; not fresh holdout evidence.",
            "Best reference is provisional among completed jobs, not necessarily the full queue winner.",
            "Hourly control is minimum hourly probability calibrated to slot outcomes, not original queue policy.",
            "Both arms replay causally within each horizon; budgets across horizons are alternatives, not additive.",
            "All policies exclude missing-quality/nonfinite-feature slots; D+7 normally abstains.",
            "Wilson day-cluster bounds are selection heuristics, not independence/post-selection guarantees.",
            "Overlapping slots, repeated horizons and adjacent delivery days are dependent.",
            "Source-vintage/weather publication assumptions remain unresolved."]})
    atomic_json(output / "status.json", {"state": "smoke_passed" if smoke else "completed",
                                         "smoke": smoke, "test_evaluated": False})
    print(combined["summary"].to_string(index=False), flush=True)
    print(f"{mode} comparison finished: {destination}", flush=True)


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
        parser.error("Use GRIDSENSE_DATA=real; no final-test evaluation is supported")
    if args.prepare:
        if args.queue_dir is None:
            parser.error("--queue-dir is required for preparation")
        prepare(args.queue_dir, args.run_dir, PolicySettings(), args.candidate)
    else:
        run(args.run_dir, args.smoke)


if __name__ == "__main__":
    main()