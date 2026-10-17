"""Collapse hourly PM2.5 predictions into outdoor / indoor time windows."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Iterable

import pandas as pd

from src.config import DISCLAIMER, OUTDOOR_PM25_MAX, REGION_LABELS


@dataclass
class DayPlan:
    region: str
    outdoor_windows: list[tuple[datetime, datetime]]
    indoor_windows: list[tuple[datetime, datetime]]
    threshold: float
    hourly: pd.DataFrame

    def format_message(self) -> str:
        label = REGION_LABELS.get(self.region, self.region.title())
        outdoor = _format_ranges(self.outdoor_windows) or "none for the rest of today"
        indoor = _format_ranges(self.indoor_windows) or "none for the rest of today"
        peak = ""
        if not self.hourly.empty:
            idx = self.hourly["pm25_pred"].idxmax()
            row = self.hourly.loc[idx]
            peak = (
                f"\nPeak outlook: ~{row['pm25_pred']:.0f} µg/m³ "
                f"around {row['timestamp'].strftime('%H:%M')}"
            )
        return (
            f"**{label} — today’s outdoor plan**\n"
            f"Outdoors OK: {outdoor}\n"
            f"Stay indoors: {indoor}"
            f"{peak}\n"
            f"_(threshold ≤ {self.threshold:.0f} µg/m³ 1-hr PM2.5)_\n"
            f"_{DISCLAIMER}_"
        )


def _fmt_end(end: datetime) -> str:
    if end.hour == 0 and end.minute == 0:
        return "24:00"
    return end.strftime("%H:%M")


def _format_ranges(ranges: Iterable[tuple[datetime, datetime]]) -> str:
    parts: list[str] = []
    for start, end in ranges:
        # end is exclusive hour end → show clock face of range end
        parts.append(f"{start.strftime('%H:%M')}–{_fmt_end(end)}")
    return ", ".join(parts)


def merge_hours(
    hours: list[datetime],
) -> list[tuple[datetime, datetime]]:
    """Merge sorted hour starts into [start, end) ranges where end = last+1h."""
    if not hours:
        return []
    hours = sorted(hours)
    ranges: list[tuple[datetime, datetime]] = []
    start = hours[0]
    prev = hours[0]
    for h in hours[1:]:
        if (h - prev).total_seconds() == 3600:
            prev = h
            continue
        ranges.append((start, prev + pd.Timedelta(hours=1).to_pytimedelta()))
        start = h
        prev = h
    ranges.append((start, prev + pd.Timedelta(hours=1).to_pytimedelta()))
    return ranges


def build_day_plan(
    forecast: pd.DataFrame,
    region: str,
    threshold: float | None = None,
) -> DayPlan:
    threshold = OUTDOOR_PM25_MAX if threshold is None else threshold
    fc = forecast.copy()
    if fc.empty:
        return DayPlan(region, [], [], threshold, fc)

    fc["timestamp"] = pd.to_datetime(fc["timestamp"])
    outdoor_hours = [
        ts.to_pydatetime()
        for ts, val in zip(fc["timestamp"], fc["pm25_pred"], strict=True)
        if float(val) <= threshold
    ]
    indoor_hours = [
        ts.to_pydatetime()
        for ts, val in zip(fc["timestamp"], fc["pm25_pred"], strict=True)
        if float(val) > threshold
    ]
    return DayPlan(
        region=region.lower(),
        outdoor_windows=merge_hours(outdoor_hours),
        indoor_windows=merge_hours(indoor_hours),
        threshold=threshold,
        hourly=fc,
    )


def plan_from_forecast(
    forecast: pd.DataFrame,
    region: str,
    threshold: float | None = None,
) -> str:
    return build_day_plan(forecast, region, threshold).format_message()
