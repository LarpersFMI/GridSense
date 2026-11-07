"""Romanian week-ahead load forecast (TR 6.1.C) from the File Library extracts."""

import pandas as pd

from gridsense import config, io
from gridsense.schemas import LOAD_FC_WEEK_AHEAD

FOLDER = "TotalLoadForecast_6.1.C_D_E_r3"


def parse_week_ahead(raw: pd.DataFrame) -> pd.DataFrame:
    """Daily min/max forecast per local delivery day from the raw tab-separated rows."""
    df = raw[(raw["ContractType"] == "Week-ahead") & (raw["AreaMapCode"] == "RO")]
    if not df["ResolutionCode"].eq("P1D").all():
        raise ValueError("Expected daily (P1D) week-ahead load forecasts")
    start = pd.to_datetime(df["DateTime(UTC)"], utc=True)
    out = pd.DataFrame(
        {
            "target_date": start.dt.tz_convert(config.LOCAL_TZ).dt.tz_localize(None).dt.normalize(),
            "load_fc_min_mw": pd.to_numeric(df["MinimumLoadForecast[MW]"]),
            "load_fc_max_mw": pd.to_numeric(df["MaximumLoadForecast[MW]"]),
            "updated_at_utc": pd.to_datetime(df["UpdateTime(UTC)"], utc=True),
        }
    )
    # Monthly files overlap at their edges; keep the latest update per day.
    out = out.sort_values("updated_at_utc").drop_duplicates("target_date", keep="last")
    return out.sort_values("target_date", ignore_index=True).astype(LOAD_FC_WEEK_AHEAD)


def main() -> None:
    paths = sorted((config.RAW_DIR / "entsoe_file_library" / FOLDER).glob("*.csv"))
    if not paths:
        raise SystemExit(f"No extracts for {FOLDER}; run gridsense.data.entsoe_files first")
    raw = pd.concat([pd.read_csv(p, sep="\t", dtype=str) for p in paths], ignore_index=True)
    table = parse_week_ahead(raw)
    io.write(table, "load_fc_week_ahead")
    days = pd.date_range(table["target_date"].min(), table["target_date"].max())
    print(
        f"[{config.DATA_MODE}] load_fc_week_ahead: {len(table):,} days "
        f"{days[0]:%Y-%m-%d}..{days[-1]:%Y-%m-%d}, {len(days.difference(table['target_date']))} missing"
    )


if __name__ == "__main__":
    main()
