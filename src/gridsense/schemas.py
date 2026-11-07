"""Data contract between the data, ML and agent workstreams. All parquet files live in data/processed/."""

# prices_hourly.parquet: one row per delivery hour; 15-min MTUs aggregated to hourly.
PRICES_HOURLY = {
    "ts_utc": "datetime64[ns, UTC]",
    "price_mean": "float64",
    "price_min": "float64",
    "price_max": "float64",
}

# grid_hourly.parquet: actuals, only usable as lagged features (known as of issue time).
GRID_HOURLY = {
    "ts_utc": "datetime64[ns, UTC]",
    "load_actual_mw": "float64",
    "solar_actual_mw": "float64",
    "wind_actual_mw": "float64",
}

# weather_fc.parquet: forecasts as they were issued, one row per (issue, target, location).
WEATHER_FC = {
    "issue_date": "datetime64[ns]",
    "target_ts_utc": "datetime64[ns, UTC]",
    "lead_days": "int64",
    "location": "string",
    "ghi_wm2": "float64",
    "cloud_cover_pct": "float64",
    "wind100_ms": "float64",
    "temp_c": "float64",
}

# calendar.parquet: one row per local hour.
CALENDAR = {
    "ts_utc": "datetime64[ns, UTC]",
    "is_holiday": "bool",
    "is_bridge_day": "bool",
    "is_dst": "bool",
    "day_hours": "int64",
}

# predictions.parquet: ML output consumed by the agent.
PREDICTIONS = {
    "issue_ts": "datetime64[ns, UTC]",
    "target_ts_utc": "datetime64[ns, UTC]",
    "horizon_days": "int64",
    "p_cheap": "float64",
    "p_near_zero": "float64",
    "price_p10": "float64",
    "price_p50": "float64",
    "price_p90": "float64",
    "data_quality": "string",
    "top_features": "string",
}
