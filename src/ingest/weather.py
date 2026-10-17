"""Fetch national-average weather features from data.gov.sg station APIs."""

from __future__ import annotations

import time
from datetime import date, datetime, timedelta
from typing import Any

import httpx
import pandas as pd

from src.config import WEATHER_APIS, api_headers


def _station_mean(reading: dict[str, Any]) -> float | None:
    points = reading.get("data") or []
    values = [float(p["value"]) for p in points if p.get("value") is not None]
    if not values:
        return None
    return sum(values) / len(values)


def fetch_weather_day(day: date, client: httpx.Client | None = None) -> pd.DataFrame:
    """
    Return hourly national means: timestamp, rainfall, temperature, wind_speed.
    Missing series are left as NaN — training tolerates that.
    """
    own_client = client is None
    client = client or httpx.Client(timeout=30.0, headers=api_headers())
    try:
        series: dict[str, dict[pd.Timestamp, float]] = {
            "rainfall": {},
            "temperature": {},
            "wind_speed": {},
        }
        for name, url in WEATHER_APIS.items():
            params: dict[str, str] = {"date": day.isoformat()}
            try:
                while True:
                    resp = client.get(url, params=params)
                    if resp.status_code == 429:
                        time.sleep(12)
                        resp = client.get(url, params=params)
                    if resp.status_code >= 400:
                        break
                    payload = resp.json()
                    if payload.get("code") != 0:
                        break
                    data = payload.get("data") or {}
                    for reading in data.get("readings") or []:
                        mean = _station_mean(reading)
                        if mean is None:
                            continue
                        ts = pd.to_datetime(reading["timestamp"])
                        # floor to hour for join with PM2.5
                        hour = ts.floor("h")
                        series[name][hour] = mean
                    token = data.get("paginationToken")
                    if not token:
                        break
                    params = {"date": day.isoformat(), "paginationToken": token}
                    time.sleep(0.35)
            except Exception as exc:  # noqa: BLE001
                print(f"warn: weather {name} failed for {day}: {exc}")
            time.sleep(0.35)

        hours = sorted(
            set().union(*[set(v.keys()) for v in series.values()])  # type: ignore[arg-type]
        )
        if not hours:
            return pd.DataFrame(
                columns=["timestamp", "rainfall", "temperature", "wind_speed"]
            )
        rows = []
        for hour in hours:
            rows.append(
                {
                    "timestamp": hour,
                    "rainfall": series["rainfall"].get(hour),
                    "temperature": series["temperature"].get(hour),
                    "wind_speed": series["wind_speed"].get(hour),
                }
            )
        return pd.DataFrame(rows)
    finally:
        if own_client:
            client.close()


def fetch_weather_range(start: date, end: date) -> pd.DataFrame:
    frames: list[pd.DataFrame] = []
    with httpx.Client(timeout=30.0, headers=api_headers()) as client:
        day = start
        while day <= end:
            df = fetch_weather_day(day, client=client)
            if not df.empty:
                frames.append(df)
            day += timedelta(days=1)
            time.sleep(0.4)
    if not frames:
        return pd.DataFrame(
            columns=["timestamp", "rainfall", "temperature", "wind_speed"]
        )
    out = pd.concat(frames, ignore_index=True)
    return out.drop_duplicates(subset=["timestamp"]).sort_values("timestamp")
