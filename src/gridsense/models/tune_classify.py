"""Recency half-life sweep for the low-price classifier, on validation only. Owner: ML-C.

    uv run python -m gridsense.models.tune_classify [--half-lives 90 365 none 730/90 ...]

Each training row gets weight 0.5 ** (age_days / half_life), where age is measured back from the
last train hour: a short half-life trusts recent months (more solar), a long one keeps every year.
A candidate is one half-life for both chain steps ("365"), or near-zero step / cheap step
("730/90"); "none" means no recency weighting. Every candidate is trained the normal way (early
stopping on val) and scored on the same val rows, raw and with month-cross-fitted calibration.
Writes reports/<mode>/eval/classify_half_life_val.csv and classify_half_life_by_month_val.csv.
Never touches the test split.
"""

import argparse

import numpy as np
import pandas as pd

from gridsense import config
from gridsense.models import train as train_module
from gridsense.models.base import recency_weights
from gridsense.models.classify import CHEAP_GIVEN_NEAR_ZERO, LABELS, NEAR_ZERO, LowPriceClassifier
from gridsense.models.metrics import classification_report

HalfLife = float | None
Candidate = tuple[HalfLife, HalfLife]  # (near-zero step, cheap-given-near-zero step)

CANDIDATES: tuple[Candidate, ...] = (
    *((h, h) for h in (90.0, 180.0, 365.0, 730.0, None)),
    (730.0, 90.0),
    (None, 90.0),
    (730.0, 180.0),
)


def _name(half_life: HalfLife) -> str:
    return "none" if half_life is None else f"{half_life:g}"


def candidate_name(candidate: Candidate) -> str:
    near_zero, cheap = candidate
    return _name(near_zero) if near_zero == cheap else f"{_name(near_zero)}/{_name(cheap)}"


def parse_candidate(value: str) -> Candidate:
    parts = [None if p.lower() == "none" else float(p) for p in value.split("/")]
    if len(parts) == 1:
        return parts[0], parts[0]
    if len(parts) == 2:
        return parts[0], parts[1]
    raise argparse.ArgumentTypeError(f"expected DAYS or DAYS/DAYS, got {value!r}")


def _weight_last_year(train: pd.DataFrame, half_life: HalfLife) -> float:
    """Share of the total training weight on the last 12 months of train (1/n rows if unweighted)."""
    w = recency_weights(train, half_life)
    w = np.ones(len(train)) if w is None else w
    recent = train["target_ts_utc"] > train["target_ts_utc"].max() - pd.Timedelta(days=365)
    return float(w[recent.to_numpy()].sum() / w.sum())


def sweep(
    train: pd.DataFrame, val: pd.DataFrame, candidates=CANDIDATES
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """(overall, by_month): one row per candidate x raw/calibrated x label (x val month)."""
    month = val["target_ts_utc"].dt.tz_convert(config.LOCAL_TZ).dt.month.to_numpy()
    overall, by_month = [], []
    for candidate in candidates:
        near_zero, cheap = candidate
        clf = LowPriceClassifier(
            half_life_days=near_zero, step_half_lives={CHEAP_GIVEN_NEAR_ZERO: cheap}
        ).fit(train, val)
        trees = clf.best_iterations()
        preds = {"raw": clf.predict(val, apply_calibration=False)}
        if clf.calibrators:
            preds["calibrated"] = clf.predict_cross_fitted(val, month)
        name = candidate_name(candidate)
        info = {
            "half_life_days": name,
            "weight_last_year": _weight_last_year(train, near_zero),
            "trees_near_zero": trees[NEAR_ZERO],
            "trees_cheap_given_near_zero": trees[CHEAP_GIVEN_NEAR_ZERO],
        }
        for kind, pred in preds.items():
            for col, label in LABELS.items():
                y = val[label].astype(int).to_numpy()
                p = pred[col].to_numpy()
                report = classification_report(y, p, k=int(y.sum()))
                overall.append({**info, "kind": kind, "label": col, **report})
                for m in np.unique(month):
                    held = month == m
                    r = classification_report(y[held], p[held], k=int(y[held].sum()))
                    by_month.append(
                        {"half_life_days": name, "kind": kind, "label": col, "month": m}
                        | {k: r[k] for k in ("positives", "pr_auc", "brier")}
                    )
        print(f"[{config.DATA_MODE}] half-life {name}: trees {trees}")
    return pd.DataFrame(overall), pd.DataFrame(by_month)


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument(
        "--half-lives",
        nargs="+",
        type=parse_candidate,
        default=list(CANDIDATES),
        help="DAYS for both steps or NEAR_ZERO/CHEAP (e.g. 730/90); 'none' = no weighting",
    )
    args = parser.parse_args(argv)

    train, val = train_module.load_train_val()
    overall, by_month = sweep(train, val, args.half_lives)
    out_dir = config.REPORTS_DIR / "eval"
    out_dir.mkdir(parents=True, exist_ok=True)
    overall.to_csv(out_dir / "classify_half_life_val.csv", index=False)
    by_month.to_csv(out_dir / "classify_half_life_by_month_val.csv", index=False)

    with pd.option_context("display.width", 160, "display.float_format", "{:.4f}".format):
        cols = ["weight_last_year", "pr_auc", "precision_at_k", "brier"]
        print(overall.set_index(["kind", "label", "half_life_days"])[cols].to_string())


if __name__ == "__main__":
    main()
