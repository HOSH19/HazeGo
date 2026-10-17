"""Load committed model and produce today's hourly PM2.5 outlook."""

from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

from src.config import HORIZONS, MODEL_PATH, SGT
from src.features.build import latest_feature_rows
from src.ingest.history import load_history
from src.ingest.pm25 import fetch_pm25_latest, today_sgt
from src.train.retrain_daily import load_bundle


def reload_model(path: Path | None = None) -> dict[str, Any]:
    bundle = load_bundle(path or MODEL_PATH)
    if bundle is None:
        raise FileNotFoundError(
            f"No model at {path or MODEL_PATH}. Run training first "
            "(python -m src.train.retrain_daily --seed-backfill 60)."
        )
    return bundle


def forecast_region(
    region: str,
    history: pd.DataFrame | None = None,
    bundle: dict[str, Any] | None = None,
    as_of: datetime | None = None,
) -> pd.DataFrame:
    """
    Return DataFrame with columns: timestamp, region, pm25_pred, horizon_h
    for the next hours covering the rest of the SGT calendar day (up to 24h).
    """
    region = region.lower()
    bundle = bundle or reload_model()
    models: dict[int, Any] = bundle["models"]
    history = load_history() if history is None else history
    if history.empty:
        raise RuntimeError("Empty history — cannot forecast")

    feat_rows = latest_feature_rows(history)
    row = feat_rows[feat_rows["region"] == region]
    if row.empty:
        raise ValueError(f"No feature row for region={region}")

    from src.features.build import feature_matrix

    X = feature_matrix(row)
    as_of = as_of or pd.to_datetime(row.iloc[0]["timestamp"]).to_pydatetime()
    if as_of.tzinfo is None:
        as_of = as_of.replace(tzinfo=ZoneInfo(SGT))
    else:
        as_of = as_of.astimezone(ZoneInfo(SGT))

    end_of_day = datetime(
        as_of.year, as_of.month, as_of.day, 23, 0, tzinfo=ZoneInfo(SGT)
    )
    # Also allow forecasting into tomorrow morning if as_of is late; morning job
    # typically wants full remaining day. Cap at 24h.
    max_h = min(max(models.keys()), 24)
    records: list[dict[str, Any]] = []
    for h in range(1, max_h + 1):
        if h not in models:
            continue
        ts = as_of + timedelta(hours=h)
        if ts > end_of_day + timedelta(hours=0):
            # Still include up to end of day only for "today's plan"
            if ts.date() > as_of.date():
                break
        pred = float(models[h].predict(X)[0])
        pred = float(max(0.0, pred))
        records.append(
            {
                "timestamp": ts,
                "region": region,
                "pm25_pred": pred,
                "horizon_h": h,
            }
        )

    if not records:
        # Fallback: at least produce 24h from available models
        for h in sorted(models.keys()):
            ts = as_of + timedelta(hours=h)
            pred = float(max(0.0, models[h].predict(X)[0]))
            records.append(
                {
                    "timestamp": ts,
                    "region": region,
                    "pm25_pred": pred,
                    "horizon_h": h,
                }
            )

    return pd.DataFrame(records)


def forecast_today(
    region: str,
    bundle: dict[str, Any] | None = None,
) -> pd.DataFrame:
    """Forecast remaining hours of today SGT for a region."""
    # Merge latest live reading into history view for fresher lags when possible
    history = load_history()
    try:
        live = fetch_pm25_latest()
        if not live.empty:
            live = live.copy()
            live["timestamp"] = pd.to_datetime(live["timestamp"]).dt.floor("h")
            for col in ("rainfall", "temperature", "wind_speed"):
                if col not in live.columns:
                    live[col] = np.nan
            history = (
                pd.concat([history, live], ignore_index=True)
                .drop_duplicates(subset=["timestamp", "region"], keep="last")
                .sort_values(["timestamp", "region"])
            )
    except Exception as exc:  # noqa: BLE001
        print(f"warn: live PM2.5 merge failed: {exc}")

    now = datetime.now(ZoneInfo(SGT)).replace(minute=0, second=0, microsecond=0)
    # Use last history timestamp as as_of if it's recent; else now
    feat = latest_feature_rows(history)
    row = feat[feat["region"] == region.lower()]
    if not row.empty:
        as_of = pd.to_datetime(row.iloc[0]["timestamp"]).to_pydatetime()
        if as_of.tzinfo is None:
            as_of = as_of.replace(tzinfo=ZoneInfo(SGT))
    else:
        as_of = now

    fc = forecast_region(region, history=history, bundle=bundle, as_of=as_of)
    today = today_sgt()
    fc = fc[fc["timestamp"].dt.date == today].copy()
    if fc.empty:
        # If history timestamp is already end of day, forecast next 12h anyway
        fc = forecast_region(region, history=history, bundle=bundle, as_of=now)
    return fc.reset_index(drop=True)
