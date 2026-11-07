import numpy as np
import pandas as pd
from sklearn.metrics import average_precision_score, brier_score_loss, mean_pinball_loss

from gridsense import config


def classification_report(y_true: np.ndarray, p: np.ndarray, k: int) -> dict[str, float]:
    """PR-AUC, precision@k, Brier."""
    y = np.asarray(y_true, dtype=int)
    p = np.asarray(p, dtype=float)
    top_k = np.argsort(-p)[:k]
    return {
        "positives": int(y.sum()),
        "pr_auc": float(average_precision_score(y, p)) if y.any() else float("nan"),
        "precision_at_k": float(y[top_k].mean()) if k > 0 else float("nan"),
        "brier": float(brier_score_loss(y, p)),
    }


def quantile_report(y_true: np.ndarray, quantiles: dict[float, np.ndarray]) -> dict[str, float]:
    """Pinball loss per quantile and coverage of the outer interval."""
    y = np.asarray(y_true, dtype=float)
    out = {
        f"pinball_p{round(q * 100)}": float(mean_pinball_loss(y, pred, alpha=q))
        for q, pred in quantiles.items()
    }
    lo, hi = min(quantiles), max(quantiles)
    out["coverage"] = float(np.mean((y >= quantiles[lo]) & (y <= quantiles[hi])))
    out["nominal_coverage"] = hi - lo
    return out


def price_report(y_true: pd.Series, pred: pd.DataFrame) -> dict[str, float]:
    """Point, quantile and interval metrics for price forecasts (columns price_p10/p50/p90)."""
    y = np.asarray(y_true, dtype=float)
    quantiles = {q: pred[f"price_p{round(q * 100)}"].to_numpy() for q in config.QUANTILES}
    out = quantile_report(y, quantiles)
    err = y - pred["price_p50"].to_numpy()
    low = y <= config.NEAR_ZERO_THRESHOLD_EUR
    out |= {
        "n": len(y),
        "mae": float(np.mean(np.abs(err))),
        "rmse": float(np.sqrt(np.mean(err**2))),
        "mean_pinball": float(np.mean([v for k, v in out.items() if k.startswith("pinball_")])),
        "width": float(np.mean(quantiles[max(quantiles)] - quantiles[min(quantiles)])),
        "mae_low_price": float(np.mean(np.abs(err[low]))) if low.any() else float("nan"),
    }
    return out


# --- Slot metrics (ML-C): what PPC experiences, whole announced slots rather than single hours. ---

SLOT_COLUMNS = ["issue_ts", "horizon_days", "slot_start", "slot_end", "hours", "p_mean"]


def block_slots(
    predictions: pd.DataFrame,
    p_col: str,
    tau: float,
    min_hours: int = 2,
    max_hours: int = 6,
    window: tuple[int, int] = (9, 18),
) -> pd.DataFrame:
    """Simple slot builder: runs of consecutive hours with p >= tau, local time inside `window`.

    Stand-in for agent.planner.candidate_slots (same 2-6 h, 09:00-18:00 contract) so slot metrics
    can be computed before the agent exists. Runs longer than max_hours are cut into max_hours
    pieces; pieces shorter than min_hours are dropped. slot_end is exclusive, both in UTC.
    """
    hour = predictions["target_ts_utc"].dt.tz_convert(config.LOCAL_TZ).dt.hour
    keep = (hour >= window[0]) & (hour < window[1]) & (predictions[p_col] >= tau)
    rows = predictions[keep].sort_values(["issue_ts", "horizon_days", "target_ts_utc"])
    if rows.empty:
        return pd.DataFrame(columns=SLOT_COLUMNS)

    same_forecast = rows["issue_ts"].eq(rows["issue_ts"].shift()) & rows["horizon_days"].eq(
        rows["horizon_days"].shift()
    )
    next_hour = rows["target_ts_utc"].diff().eq(pd.Timedelta(hours=1)) & same_forecast
    run = (~next_hour).cumsum()
    piece = rows.groupby(run).cumcount() // max_hours
    slots = rows.groupby([run, piece]).agg(
        issue_ts=("issue_ts", "first"),
        horizon_days=("horizon_days", "first"),
        slot_start=("target_ts_utc", "min"),
        last_hour=("target_ts_utc", "max"),
        hours=("target_ts_utc", "size"),
        p_mean=(p_col, "mean"),
    )
    slots["slot_end"] = slots.pop("last_hour") + pd.Timedelta(hours=1)
    return slots.loc[slots["hours"] >= min_hours, SLOT_COLUMNS].reset_index(drop=True)


def slot_outcomes(slots: pd.DataFrame, prices: pd.DataFrame, threshold: float) -> pd.DataFrame:
    """Per slot: hours, cheap_hours (cleared <= threshold) and hit (1.0 if every hour did).

    prices has the prices_hourly columns ts_utc and price_mean. hit is NaN when a price is missing.
    """
    if slots.empty:
        return pd.DataFrame(columns=["hours", "cheap_hours", "hit"], dtype=float)
    n = ((slots["slot_end"] - slots["slot_start"]) // pd.Timedelta(hours=1)).astype(int)
    starts = slots["slot_start"].repeat(n)  # one row per slot hour, indexed by slot
    offsets = starts.groupby(level=0).cumcount().to_numpy()
    hours = starts + pd.to_timedelta(offsets, unit="h")
    price = hours.map(prices.set_index("ts_utc")["price_mean"])

    out = pd.DataFrame(
        {
            "hours": n,
            "cheap_hours": (price <= threshold).groupby(level=0).sum(),
            "known": price.notna().groupby(level=0).all(),
        }
    )
    out["hit"] = (out["cheap_hours"] == out["hours"]).astype(float).where(out.pop("known"))
    return out


def slot_hit_rate(
    announced_slots: pd.DataFrame,
    prices: pd.DataFrame,
    threshold: float = config.CHEAP_THRESHOLD_EUR,
) -> float:
    """Share of announced slots in which every hour cleared at or below the threshold.

    1 - hit rate is the miss rate: for slots announced before the D+1 auction, those are the
    slots the agent would have to cancel.
    """
    hit = slot_outcomes(announced_slots, prices, threshold)["hit"]
    return float(hit.mean()) if hit.notna().any() else float("nan")


def by_horizon(table: pd.DataFrame, metric_fn) -> pd.DataFrame:
    """metric_fn(sub_table) -> dict, for all rows and for each horizon_days."""
    rows = {"all": metric_fn(table)}
    rows |= {int(h): metric_fn(group) for h, group in table.groupby("horizon_days")}
    return pd.DataFrame.from_dict(rows, orient="index").rename_axis("horizon")
