"""Fetch NEA regional 1-hour PM2.5 readings."""

from __future__ import annotations

import time
from datetime import date, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

import httpx
import pandas as pd

from src.config import PM25_API, REGIONS, SGT, api_headers


def _parse_timestamp(value: str) -> datetime:
    # NEA returns +08:00 timestamps
    return datetime.fromisoformat(value)


def items_to_rows(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for item in items:
        ts = _parse_timestamp(item["timestamp"])
        readings = (item.get("readings") or {}).get("pm25_one_hourly") or {}
        for region in REGIONS:
            if region not in readings:
                continue
            rows.append(
                {
                    "timestamp": ts,
                    "region": region,
                    "pm25": float(readings[region]),
                }
            )
    return rows


def fetch_pm25_day(day: date, client: httpx.Client | None = None) -> pd.DataFrame:
    """Fetch all hourly PM2.5 readings for a SGT calendar day."""
    own_client = client is None
    client = client or httpx.Client(timeout=30.0, headers=api_headers())
    try:
        rows: list[dict[str, Any]] = []
        params: dict[str, str] = {"date": day.isoformat()}
        while True:
            resp = client.get(PM25_API, params=params)
            if resp.status_code == 429:
                time.sleep(12)
                resp = client.get(PM25_API, params=params)
            resp.raise_for_status()
            payload = resp.json()
            if payload.get("code") != 0:
                err = payload.get("errorMsg") or payload
                raise RuntimeError(f"PM2.5 API error for {day}: {err}")
            data = payload.get("data") or {}
            rows.extend(items_to_rows(data.get("items") or []))
            token = data.get("paginationToken")
            if not token:
                break
            params = {"date": day.isoformat(), "paginationToken": token}
            time.sleep(0.35)
        if not rows:
            return pd.DataFrame(columns=["timestamp", "region", "pm25"])
        df = pd.DataFrame(rows)
        df["timestamp"] = pd.to_datetime(df["timestamp"], utc=False)
        return df.drop_duplicates(subset=["timestamp", "region"]).sort_values(
            ["timestamp", "region"]
        )
    finally:
        if own_client:
            client.close()


def fetch_pm25_latest(client: httpx.Client | None = None) -> pd.DataFrame:
    own_client = client is None
    client = client or httpx.Client(timeout=30.0, headers=api_headers())
    try:
        resp = client.get(PM25_API)
        if resp.status_code == 429:
            time.sleep(12)
            resp = client.get(PM25_API)
        resp.raise_for_status()
        payload = resp.json()
        if payload.get("code") != 0:
            raise RuntimeError(payload.get("errorMsg") or payload)
        rows = items_to_rows((payload.get("data") or {}).get("items") or [])
        if not rows:
            return pd.DataFrame(columns=["timestamp", "region", "pm25"])
        df = pd.DataFrame(rows)
        df["timestamp"] = pd.to_datetime(df["timestamp"], utc=False)
        return df
    finally:
        if own_client:
            client.close()


def fetch_pm25_range(start: date, end: date) -> pd.DataFrame:
    """Inclusive date range in SGT calendar days."""
    frames: list[pd.DataFrame] = []
    with httpx.Client(timeout=30.0, headers=api_headers()) as client:
        day = start
        while day <= end:
            try:
                df = fetch_pm25_day(day, client=client)
                if not df.empty:
                    frames.append(df)
            except Exception as exc:  # noqa: BLE001 — keep backfill resilient
                print(f"warn: PM2.5 fetch failed for {day}: {exc}")
            day += timedelta(days=1)
            time.sleep(0.4)
    if not frames:
        return pd.DataFrame(columns=["timestamp", "region", "pm25"])
    out = pd.concat(frames, ignore_index=True)
    return out.drop_duplicates(subset=["timestamp", "region"]).sort_values(
        ["timestamp", "region"]
    )


def today_sgt() -> date:
    return datetime.now(ZoneInfo(SGT)).date()
