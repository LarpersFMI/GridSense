import json

import matplotlib.pyplot as plt
import pandas as pd
import seaborn as sns
from lightgbm import LGBMRegressor
from sklearn.inspection import permutation_importance

from gridsense.features.feature_augmentation import build_working_dataset
from src.gridsense.config import REPORTS_DIR


def run_feature_importance():
    print("1. Loading augmented datasets...")
    train_df, val_df, _test_df, _working_df = build_working_dataset()

    target_col = "price_mean" if "price_mean" in train_df.columns else "price"
    if target_col not in train_df.columns:
        raise KeyError(
            f"Target column '{target_col}' not found. Check prices DataFrame."
        )

    # Filter strictly numeric/boolean feature columns
    numeric_types = ["int16", "int32", "int64", "float32", "float64", "bool"]
    candidate_cols = train_df.select_dtypes(include=numeric_types).columns.tolist()

    ignore_targets = [
        target_col,
        "price_min",
        "price_max",
        "price",
        "latitude",
        "longitude",
    ]
    feature_cols = [c for c in candidate_cols if c not in ignore_targets]

    print(
        f"2. Preparing matrices ({len(feature_cols)} numeric features, target = '{target_col}')..."
    )

    train_clean = train_df.dropna(subset=feature_cols + [target_col]).reset_index(
        drop=True
    )
    val_clean = val_df.dropna(subset=feature_cols + [target_col]).reset_index(
        drop=True
    )

    X_train, y_train = train_clean[feature_cols], train_clean[target_col]
    X_val, y_val = val_clean[feature_cols], val_clean[target_col]

    print("3. Training baseline LightGBM model...")
    model = LGBMRegressor(
        n_estimators=150,
        learning_rate=0.05,
        num_leaves=31,
        random_state=42,
        n_jobs=-1,
        verbose=-1,
    )
    model.fit(X_train, y_train)

    val_r2 = model.score(X_val, y_val)
    print(f"   Validation R^2 score: {val_r2:.4f}")

    print("4. Computing Permutation Importance on validation set (5 repeats)...")
    result = permutation_importance(
        model,
        X_val,
        y_val,
        scoring="neg_root_mean_squared_error",
        n_repeats=5,
        random_state=42,
        n_jobs=-1,
    )

    importance_df = (
        pd.DataFrame(
            {
                "feature": feature_cols,
                "importance_mean": result.importances_mean,
                "importance_std": result.importances_std,
            }
        )
        .sort_values(by="importance_mean", ascending=False)
        .reset_index(drop=True)
    )

    # Save ordered feature list to disk
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    ranking_path = REPORTS_DIR / "feature_importance.json"

    ranked_features = importance_df["feature"].tolist()
    with open(ranking_path, "w", encoding="utf-8") as f:
        json.dump(ranked_features, f, indent=4)

    print(f"\nFeature ranking saved to: {ranking_path}")
    return importance_df, model, X_val, y_val


def plot_feature_importance(importance_df: pd.DataFrame, top_n: int = 25):
    top_df = importance_df.head(top_n).copy()

    plt.figure(figsize=(12, 8))
    sns.set_theme(style="whitegrid")

    bars = sns.barplot(
        data=top_df,
        x="importance_mean",
        y="feature",
        palette="crest_r",
        edgecolor="black",
        linewidth=0.5,
    )

    plt.title(
        f"Top {top_n} Feature Permutation Importance (Validation RMSE Increase)",
        fontsize=14,
        pad=15,
        weight="bold",
    )
    plt.xlabel(
        "Mean Drop in Model Performance (RMSE Increase when Shuffled)",
        fontsize=12,
    )
    plt.ylabel("Feature Name", fontsize=12)

    for i, row in top_df.iterrows():
        bars.text(
            row["importance_mean"] + (top_df["importance_mean"].max() * 0.01),
            i,
            f"{row['importance_mean']:.3f} ± {row['importance_std']:.3f}",
            va="center",
            fontsize=9,
            color="#333333",
        )

    plt.tight_layout()
    output_fig = REPORTS_DIR / "feature_importance_ranking.png"
    plt.savefig(output_fig, dpi=300)
    print(f"Visualization saved to: {output_fig}")
    plt.show()


if __name__ == "__main__":
    importance_df, model, X_val, y_val = run_feature_importance()
    plot_feature_importance(importance_df, top_n=25)