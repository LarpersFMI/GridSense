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

# weather_fc.parquet: archived forecasts, one row per (issue, target, location).
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

# weather_hourly.parquet: OBSERVED/reanalysis weather, never target-hour forecast features.
# Older exports contain fabricated issue_date/lead_days extras; they are not vintage evidence.
# Keep the upstream field names but a separate contract, so io.read("weather_fc") rejects them.
WEATHER_HOURLY = {
    "target_ts_utc": "datetime64[ns, UTC]",
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

# Compatibility name used by the upstream File Library/weather integration checks.
WEATHER_ARCHIVED_FC = WEATHER_FC

# calendar.parquet: one row per local hour. Defines the target hours of the training table, so it
# must extend 7 days past the latest price date for the newest issue date to get all horizons.
CALENDAR = {
    "ts_utc": "datetime64[ns, UTC]",
    "is_holiday": "bool",
    "is_bridge_day": "bool",
    "is_dst": "bool",
    "day_hours": "int64",
}

# Country calendar exports enrich, rather than replace, the continuous Romanian ML calendar.
# Their split metadata is informational; training must still call splits.assign_split.
COUNTRY_CALENDAR = {
    **CALENDAR,
    "country": "string",
    "is_working_holiday": "bool",
    "split": "string",
}

# load_fc_week_ahead.parquet: ENTSO-E week-ahead load forecast (TR 6.1.C), one row per local day.
# Only the latest vintage exists; features must apply the publication rule (Thursday before the week).
LOAD_FC_WEEK_AHEAD = {
    "target_date": "datetime64[ns]",
    "load_fc_min_mw": "float64",
    "load_fc_max_mw": "float64",
    "updated_at_utc": "datetime64[ns, UTC]",
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
    "weather_fc": WEATHER_ARCHIVED_FC,
    "weather_hourly": WEATHER_HOURLY,
    "calendar": CALENDAR,
    "calendar_hungary": COUNTRY_CALENDAR,
    "calendar_bulgaria": COUNTRY_CALENDAR,
    "load_fc_week_ahead": LOAD_FC_WEEK_AHEAD,
    "training_table": TRAINING_TABLE,
    "predictions": PREDICTIONS,
}
