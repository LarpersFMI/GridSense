"""Data contract between the data, ML and agent workstreams. Tables live in config.PROCESSED_DIR."""

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
    "country": "string",
    "latitude": "float64",
    "longitude": "float64",
    "temp_c": "float64",
    "relative_humidity_pct": "float64",
    "precip_mm": "float64",
    "rain_mm": "float64",
    "snowfall_cm": "float64",
    "pressure_hpa": "float64",
    "cloud_cover_pct": "float64",
    "wind10_ms": "float64",
    "wind_dir_deg": "float64",
    "split": "string",
}

# calendar.parquet: one row per local hour. Defines the target hours of the training table, so it
# must extend 7 days past the latest price date for the newest issue date to get all horizons.
CALENDAR = {
    "ts_utc": "datetime64[ns, UTC]",
    "country": "string",
    "is_holiday": "bool",
    "is_working_holiday": "bool",
    "is_bridge_day": "bool",
    "is_dst": "bool",
    "day_hours": "int64",
    "split": "string",
}

# training_table.parquet: one row per (issue date, target hour, horizon). Owned by ML.
# Feature columns are free-form but must start with FEATURE_PREFIX; models use every such column.
FEATURE_PREFIX = "f_"
TRAINING_TABLE = {
    "issue_ts": "datetime64[ns, UTC]",
    "target_ts_utc": "datetime64[ns, UTC]",
    "horizon_days": "int64",
    "y_price": "float64",
    "y_near_zero": "bool",
    "y_cheap": "bool",
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
    "model_name": "string",
    "model_version": "string",
}

TABLES = {
    "prices_hourly": PRICES_HOURLY,
    "grid_hourly": GRID_HOURLY,
    "weather_fc": WEATHER_FC,
    "calendar": CALENDAR,
    "training_table": TRAINING_TABLE,
    "predictions": PREDICTIONS,
}
