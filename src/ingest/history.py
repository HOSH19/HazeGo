"""Maintain data/history.parquet used for training and forecasting."""

from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path

import pandas as pd

from src.config import DEFAULT_BACKFILL_DAYS, HISTORY_PATH
from src.ingest.pm25 import fetch_pm25_range, today_sgt
from src.ingest.weather import fetch_weather_range


def load_history(path: Path | None = None) -> pd.DataFrame:
    path = path or HISTORY_PATH
    if not path.exists():
        return pd.DataFrame(
            columns=[
                "timestamp",
                "region",
                "pm25",
                "rainfall",
                "temperature",
                "wind_speed",
            ]
        )
    df = pd.read_parquet(path)
    df["timestamp"] = pd.to_datetime(df["timestamp"])
    return df.sort_values(["timestamp", "region"]).reset_index(drop=True)


def save_history(df: pd.DataFrame, path: Path | None = None) -> Path:
    path = path or HISTORY_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    out = df.copy()
    out["timestamp"] = pd.to_datetime(out["timestamp"])
    out = out.drop_duplicates(subset=["timestamp", "region"]).sort_values(
        ["timestamp", "region"]
    )
    out.to_parquet(path, index=False)
    return path


def merge_history(existing: pd.DataFrame, new: pd.DataFrame) -> pd.DataFrame:
    if existing.empty:
        return new.copy()
    if new.empty:
        return existing.copy()
    cols = ["timestamp", "region", "pm25", "rainfall", "temperature", "wind_speed"]
    for frame in (existing, new):
        for col in cols:
            if col not in frame.columns:
                frame[col] = pd.NA
    combined = pd.concat([existing[cols], new[cols]], ignore_index=True)
    # Prefer newest non-null weather when duplicates collide
    combined = combined.sort_values("timestamp")
    combined = combined.groupby(["timestamp", "region"], as_index=False).agg(
        {
            "pm25": "last",
            "rainfall": "last",
            "temperature": "last",
            "wind_speed": "last",
        }
    )
    return combined.sort_values(["timestamp", "region"]).reset_index(drop=True)


def build_day_frame(day: date, skip_weather: bool = False) -> pd.DataFrame:
    pm = fetch_pm25_range(day, day)
    if pm.empty:
        return pm
    if skip_weather:
        for col in ("rainfall", "temperature", "wind_speed"):
            pm[col] = pd.NA
        return pm
    weather = fetch_weather_range(day, day)
    if weather.empty:
        for col in ("rainfall", "temperature", "wind_speed"):
            pm[col] = pd.NA
        return pm
    weather = weather.copy()
    weather["timestamp"] = pd.to_datetime(weather["timestamp"]).dt.floor("h")
    pm = pm.copy()
    pm["timestamp"] = pd.to_datetime(pm["timestamp"]).dt.floor("h")
    return pm.merge(weather, on="timestamp", how="left")


def update_history(
    days: int | None = None,
    start: date | None = None,
    end: date | None = None,
    path: Path | None = None,
    skip_weather: bool = False,
) -> pd.DataFrame:
    """
    Backfill or refresh history.parquet.

    If history exists and days/start not set, only refresh the last 2 calendar days
    (catch late API updates) plus today.
    """
    path = path or HISTORY_PATH
    existing = load_history(path)
    end = end or today_sgt()

    if start is None:
        if days is not None:
            start = end - timedelta(days=days - 1)
        elif existing.empty:
            start = end - timedelta(days=DEFAULT_BACKFILL_DAYS - 1)
        else:
            start = end - timedelta(days=1)

    frames: list[pd.DataFrame] = []
    day = start
    while day <= end:
        print(f"ingest {day.isoformat()} …")
        frame = build_day_frame(day, skip_weather=skip_weather)
        if not frame.empty:
            frames.append(frame)
        day += timedelta(days=1)

    if not frames:
        print("no new rows fetched")
        return existing

    new = pd.concat(frames, ignore_index=True)
    merged = merge_history(existing, new)
    save_history(merged, path)
    print(f"history rows: {len(merged)} -> {path}")
    return merged


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="Update PM2.5 history parquet")
    parser.add_argument("--days", type=int, default=None, help="Backfill N days ending today")
    parser.add_argument("--start", type=str, default=None, help="YYYY-MM-DD")
    parser.add_argument("--end", type=str, default=None, help="YYYY-MM-DD")
    parser.add_argument(
        "--skip-weather",
        action="store_true",
        help="Only fetch PM2.5 (faster seed / fewer rate limits)",
    )
    args = parser.parse_args()
    start = date.fromisoformat(args.start) if args.start else None
    end = date.fromisoformat(args.end) if args.end else None
    update_history(
        days=args.days, start=start, end=end, skip_weather=args.skip_weather
    )


if __name__ == "__main__":
    main()
