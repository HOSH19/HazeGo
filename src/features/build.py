"""Feature engineering for multi-horizon PM2.5 forecasting."""

from __future__ import annotations

import pandas as pd

from src.config import HORIZONS, LAGS, REGIONS, ROLLING_WINDOWS

REGION_TO_ID = {r: i for i, r in enumerate(REGIONS)}


def _prepare_base(history: pd.DataFrame) -> pd.DataFrame:
    df = history.copy()
    df["timestamp"] = pd.to_datetime(df["timestamp"])
    df = df.sort_values(["region", "timestamp"])
    for col in ("rainfall", "temperature", "wind_speed"):
        if col not in df.columns:
            df[col] = pd.NA
    df["hour"] = df["timestamp"].dt.hour
    df["dow"] = df["timestamp"].dt.dayofweek
    df["month"] = df["timestamp"].dt.month
    df["region_id"] = df["region"].map(REGION_TO_ID).astype("int64")
    return df


def add_lag_features(df: pd.DataFrame) -> pd.DataFrame:
    parts: list[pd.DataFrame] = []
    for region, g in df.groupby("region", sort=False):
        g = g.sort_values("timestamp").copy()
        for lag in LAGS:
            g[f"pm25_lag_{lag}"] = g["pm25"].shift(lag)
        for window in ROLLING_WINDOWS:
            g[f"pm25_roll_mean_{window}"] = (
                g["pm25"].shift(1).rolling(window, min_periods=1).mean()
            )
            g[f"pm25_roll_std_{window}"] = (
                g["pm25"].shift(1).rolling(window, min_periods=2).std()
            )
        for col in ("rainfall", "temperature", "wind_speed"):
            g[f"{col}_lag_1"] = g[col].shift(1)
        parts.append(g)
    return pd.concat(parts, ignore_index=True)


FEATURE_COLUMNS = (
    ["region_id", "hour", "dow", "month"]
    + [f"pm25_lag_{lag}" for lag in LAGS]
    + [f"pm25_roll_mean_{w}" for w in ROLLING_WINDOWS]
    + [f"pm25_roll_std_{w}" for w in ROLLING_WINDOWS]
    + ["rainfall_lag_1", "temperature_lag_1", "wind_speed_lag_1"]
)


def build_training_frame(
    history: pd.DataFrame, horizons: tuple[int, ...] = HORIZONS
) -> pd.DataFrame:
    """One row per (timestamp, region) with targets y_h{h} for each horizon."""
    base = add_lag_features(_prepare_base(history))
    parts: list[pd.DataFrame] = []
    for region, g in base.groupby("region", sort=False):
        g = g.sort_values("timestamp").copy()
        for h in horizons:
            g[f"y_h{h}"] = g["pm25"].shift(-h)
        parts.append(g)
    out = pd.concat(parts, ignore_index=True)
    # Require lag_24 so early rows drop
    out = out.dropna(subset=["pm25_lag_24"])
    return out


def feature_matrix(df: pd.DataFrame) -> pd.DataFrame:
    X = df[list(FEATURE_COLUMNS)].copy()
    for col in X.columns:
        X[col] = pd.to_numeric(X[col], errors="coerce")
    return X.fillna(-1.0)


def latest_feature_rows(history: pd.DataFrame) -> pd.DataFrame:
    """Latest complete feature row per region (for inference)."""
    base = add_lag_features(_prepare_base(history))
    base = base.dropna(subset=["pm25_lag_24"])
    if base.empty:
        return base
    idx = base.groupby("region")["timestamp"].idxmax()
    return base.loc[idx].reset_index(drop=True)
