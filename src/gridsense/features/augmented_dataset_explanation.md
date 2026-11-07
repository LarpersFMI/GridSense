# Feature Pipeline & Dataset Usage Guide

This guide explains how to generate, select, and utilize the augmented weather and energy price datasets constructed by the `GridSense` feature engineering pipeline.

---

## 1. Pipeline Architecture

The feature pipeline consists of three sequential modules located in `src/gridsense/features/`:

```
src/gridsense/features/
├── feature_augmentation.py  # Calculates physical, temporal, and spatial features
├── feature_ranking.py       # Computes Permutation Importance via LightGBM
└── feature_selection.py     # Generates final dataset & provides inference transforms
```

### Module Roles

1. **`feature_augmentation.py`**  
   Pivots multi-location hourly weather data into a flat panel, calculates physical proxies (Wind Power Density, Solar Irradiance Proxy, Heating/Cooling Degree Hours, Wind Vectors $U/V$), computes macro regional aggregates (Romania vs. neighboring countries), and generates cyclical temporal features (`hour_sin`, `dayofweek_cos`, etc.) along with price memory lags.

2. **`feature_ranking.py`**  
   Trains a baseline `LGBMRegressor` model on the training split, computes **Permutation Importance** on the validation set, outputs a ranked visualization (`reports/feature_importance_ranking.png`), and saves the ordered feature sequence to `reports/feature_importance.json`.

3. **`feature_selection.py`**  
   Extracts the top $N$ features alongside non-training metadata, writes the final augmented dataset (`weather_hourly_augmented`) via `io.write()`, and exposes `compute_features_for_new_data()` to compute identical feature sets on fresh incoming dataframes.

---

## 2. Data Schema Location

The schema for the processed augmented dataset is registered in **`src/gridsense/schemas.py`** under `WEATHER_HOURLY_AUGMENTED`.

To inspect the list of columns and expected data types in code:

```python
from gridsense.schemas import TABLES, WEATHER_HOURLY_AUGMENTED

# View full type schema dictionary
print(WEATHER_HOURLY_AUGMENTED)

# View expected column names for io validation
print(TABLES["weather_hourly_augmented"])
```

---

## 3. Training a Model on `weather_hourly_augmented`

The generated table contains all necessary metadata (`split`, `target_ts_utc`, `price_mean`) alongside the top $N$ engineered features.

### Step-by-Step Training Code

```python
import pandas as pd
from lightgbm import LGBMRegressor

from gridsense import io
from gridsense.schemas import WEATHER_HOURLY_AUGMENTED

# 1. Load the augmented dataset
df = io.read("weather_hourly_augmented")

# 2. Separate into Train, Validation, and Test splits
train_df = df[df["split"] == "Train"].copy().reset_index(drop=True)
val_df = df[df["split"] == "Validation"].copy().reset_index(drop=True)
test_df = df[df["split"] == "Test"].copy().reset_index(drop=True)

# 3. Define target and feature columns
target_col = "price_mean"
exclude_cols = [
    "ts_utc",
    "target_ts_utc",
    "split",
    "price_mean",
    "price_min",
    "price_max",
]

feature_cols = [c for c in train_df.columns if c not in exclude_cols]

# 4. Prepare feature matrices (drop NaNs introduced by autoregressive price lags)
train_clean = train_df.dropna(subset=feature_cols + [target_col])
val_clean = val_df.dropna(subset=feature_cols + [target_col])

X_train, y_train = train_clean[feature_cols], train_clean[target_col]
X_val, y_val = val_clean[feature_cols], val_clean[target_col]

# 5. Fit your ML model
model = LGBMRegressor(n_estimators=300, learning_rate=0.03, random_state=42)
model.fit(
    X_train,
    y_train,
    eval_set=[(X_val, y_val)],
)

print(f"Validation R² Score: {model.score(X_val, y_val):.4f}")
```

---

## 4. Computing Features for New Data (Inference)

When evaluating new data (e.g., streaming API payloads or fresh evaluation samples), call `compute_features_for_new_data` from `feature_selection.py`. 

This function runs raw weather points through the exact transformation pipeline, pivots them, calculates regional aggregates, and filters the result to match the top $N$ ranked features expected by your trained model.

### Inference Example

```python
import pandas as pd
from src.gridsense.features.feature_selection import (
    compute_features_for_new_data,
)

# Assume df_new_weather contains raw hourly observations for WEATHER_POINTS
# Assume df_new_prices contains recent historical prices needed for lags (optional)

df_inference_features = compute_features_for_new_data(
    df_new_weather=df_new_weather,
    df_new_prices=df_new_prices,  # Optional: Pass if computing price memory lags
    nr_features=30,  # Match the nr_features used during model training
)

# Align columns with trained model features
X_new = df_inference_features[feature_cols]

# Predict
predictions = model.predict(X_new)
```

---

## 5. Execution Workflow Summary

To rebuild feature rankings and update the augmented dataset from scratch, run the scripts in order:

```bash
# 1. Generate full feature panel
python -m src.gridsense.features.feature_augmentation

# 2. Compute importance scores & export ranking artifact (feature_importance.json)
python -m src.gridsense.features.feature_ranking

# 3. Export top-N augmented dataset to parquet (weather_hourly_augmented)
python -m src.gridsense.features.feature_selection
```