"""Train / retrain multi-horizon LightGBM models and apply quality gate."""

from __future__ import annotations

import json
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import joblib
import lightgbm as lgb
import numpy as np
import pandas as pd

from src.config import (
    HORIZONS,
    METRICS_PATH,
    MODEL_META_PATH,
    MODEL_PATH,
    MODELS_DIR,
    RETRAIN_MAX_MAE_REGRESSION,
)
from src.features.build import FEATURE_COLUMNS, build_training_frame, feature_matrix
from src.ingest.history import load_history, update_history


def _lgbm_params() -> dict[str, Any]:
    return {
        "objective": "regression",
        "metric": "mae",
        "learning_rate": 0.05,
        "num_leaves": 31,
        "feature_fraction": 0.9,
        "bagging_fraction": 0.8,
        "bagging_freq": 1,
        "min_child_samples": 20,
        "verbosity": -1,
        "n_estimators": 200,
    }


def train_models(
    train_df: pd.DataFrame, horizons: tuple[int, ...] = HORIZONS
) -> dict[int, lgb.LGBMRegressor]:
    models: dict[int, lgb.LGBMRegressor] = {}
    X = feature_matrix(train_df)
    for h in horizons:
        target = f"y_h{h}"
        mask = train_df[target].notna()
        if mask.sum() < 200:
            continue
        y = train_df.loc[mask, target].astype(float)
        model = lgb.LGBMRegressor(**_lgbm_params())
        model.fit(X.loc[mask], y)
        models[h] = model
    if not models:
        raise RuntimeError("No horizons had enough training rows")
    return models


def persistence_mae(df: pd.DataFrame, horizons: tuple[int, ...] = HORIZONS) -> float:
    errors: list[float] = []
    for h in horizons:
        target = f"y_h{h}"
        mask = df[target].notna() & df["pm25"].notna()
        if not mask.any():
            continue
        err = (df.loc[mask, target] - df.loc[mask, "pm25"]).abs()
        errors.extend(err.tolist())
    return float(np.mean(errors)) if errors else float("inf")


def model_mae(
    models: dict[int, lgb.LGBMRegressor], df: pd.DataFrame
) -> float:
    X = feature_matrix(df)
    errors: list[float] = []
    for h, model in models.items():
        target = f"y_h{h}"
        mask = df[target].notna()
        if not mask.any():
            continue
        pred = model.predict(X.loc[mask])
        err = np.abs(pred - df.loc[mask, target].to_numpy(dtype=float))
        errors.extend(err.tolist())
    return float(np.mean(errors)) if errors else float("inf")


def time_split(frame: pd.DataFrame, holdout_frac: float = 0.15) -> tuple[pd.DataFrame, pd.DataFrame]:
    frame = frame.sort_values("timestamp")
    cut = int(len(frame) * (1 - holdout_frac))
    cut = max(cut, 1)
    if cut >= len(frame):
        return frame, frame.iloc[0:0]
    return frame.iloc[:cut].copy(), frame.iloc[cut:].copy()


def load_bundle(path: Path | None = None) -> dict[str, Any] | None:
    path = path or MODEL_PATH
    if not path.exists():
        return None
    return joblib.load(path)


def save_bundle(
    models: dict[int, lgb.LGBMRegressor],
    meta: dict[str, Any],
    path: Path | None = None,
    write_meta_json: bool | None = None,
) -> None:
    path = path or MODEL_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp.joblib")
    bundle = {"models": models, "feature_columns": list(FEATURE_COLUMNS), "meta": meta}
    joblib.dump(bundle, tmp)
    tmp.replace(path)
    if write_meta_json is None:
        write_meta_json = path.resolve() == MODEL_PATH.resolve()
    if write_meta_json:
        MODEL_META_PATH.write_text(json.dumps(meta, indent=2) + "\n")


def append_metrics(row: dict[str, Any]) -> None:
    METRICS_PATH.parent.mkdir(parents=True, exist_ok=True)
    df = pd.DataFrame([row])
    if METRICS_PATH.exists():
        df.to_csv(METRICS_PATH, mode="a", header=False, index=False)
    else:
        df.to_csv(METRICS_PATH, index=False)


def quality_gate(new_mae: float, previous_mae: float | None) -> bool:
    if previous_mae is None or not np.isfinite(previous_mae):
        return True
    if not np.isfinite(new_mae):
        return False
    # Allow small regression
    limit = previous_mae * (1.0 + RETRAIN_MAX_MAE_REGRESSION)
    return new_mae <= limit


def retrain(
    refresh_history: bool = True,
    backfill_days: int | None = None,
    skip_weather: bool = False,
) -> dict[str, Any]:
    if refresh_history:
        update_history(days=backfill_days, skip_weather=skip_weather)

    history = load_history()
    if history.empty or len(history) < 500:
        raise RuntimeError(
            f"Not enough history rows ({len(history)}). Run ingest backfill first."
        )

    frame = build_training_frame(history)
    train_df, holdout = time_split(frame)
    if holdout.empty:
        holdout = train_df.tail(min(500, len(train_df)))

    models = train_models(train_df)
    new_mae = model_mae(models, holdout)
    base_mae = persistence_mae(holdout)

    previous = load_bundle()
    previous_mae = None
    if previous and previous.get("meta"):
        previous_mae = previous["meta"].get("holdout_mae")

    # Also score previous models on same holdout if present
    prev_holdout_mae = None
    if previous and previous.get("models"):
        try:
            prev_holdout_mae = model_mae(previous["models"], holdout)
        except Exception:  # noqa: BLE001
            prev_holdout_mae = previous_mae

    gate_ref = prev_holdout_mae if prev_holdout_mae is not None else previous_mae
    accept = quality_gate(new_mae, gate_ref)

    meta = {
        "trained_at_utc": datetime.now(timezone.utc).isoformat(),
        "n_train_rows": int(len(train_df)),
        "n_holdout_rows": int(len(holdout)),
        "n_history_rows": int(len(history)),
        "horizons": sorted(models.keys()),
        "holdout_mae": new_mae,
        "persistence_mae": base_mae,
        "previous_holdout_mae": gate_ref,
        "accepted": accept,
        "beats_persistence": bool(new_mae < base_mae),
    }

    metrics_row = {
        "date": datetime.now(timezone.utc).date().isoformat(),
        "holdout_mae": new_mae,
        "persistence_mae": base_mae,
        "previous_mae": gate_ref if gate_ref is not None else "",
        "accepted": accept,
        "n_train_rows": len(train_df),
        "n_history_rows": len(history),
    }
    append_metrics(metrics_row)

    result = {"meta": meta, "accepted": accept, "model_path": str(MODEL_PATH)}

    if accept:
        # Keep backup of previous artifact
        if MODEL_PATH.exists():
            shutil.copy2(MODEL_PATH, MODELS_DIR / "previous.joblib")
        save_bundle(models, meta)
        print(
            f"accepted model MAE={new_mae:.3f} (persistence={base_mae:.3f}) -> {MODEL_PATH}"
        )
    else:
        # Write candidate for inspection but do not replace current
        candidate = MODELS_DIR / "candidate.joblib"
        save_bundle(models, meta, path=candidate, write_meta_json=False)
        print(
            f"rejected model MAE={new_mae:.3f} vs previous={gate_ref}; kept {MODEL_PATH}"
        )

    # Exit code helper for Actions: write status file
    status_path = MODELS_DIR / "retrain_status.json"
    status_path.write_text(
        json.dumps({"accepted": accept, "meta": meta}, indent=2) + "\n"
    )
    return result


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="Retrain HazeGoOut LightGBM models")
    parser.add_argument(
        "--no-refresh",
        action="store_true",
        help="Skip history refresh (use existing parquet only)",
    )
    parser.add_argument(
        "--backfill-days",
        type=int,
        default=None,
        help="If refreshing empty/short history, fetch this many days",
    )
    parser.add_argument(
        "--seed-backfill",
        type=int,
        default=None,
        help="Force refresh of N days before training (for first seed)",
    )
    parser.add_argument(
        "--skip-weather",
        action="store_true",
        help="Skip weather APIs during history refresh",
    )
    args = parser.parse_args()
    days = args.seed_backfill or args.backfill_days
    retrain(
        refresh_history=not args.no_refresh,
        backfill_days=days,
        skip_weather=args.skip_weather,
    )


if __name__ == "__main__":
    main()
