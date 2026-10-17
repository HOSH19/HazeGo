"""Collapse hourly PM2.5 predictions into outdoor / indoor time windows."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from html import escape
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
        outdoor_block = _format_range_block(
            self.outdoor_windows, empty="None for the rest of today"
        )
        indoor_block = _format_range_block(
            self.indoor_windows, empty="None for the rest of today"
        )

        peak_line = ""
        avg_line = ""
        if not self.hourly.empty:
            idx = self.hourly["pm25_pred"].idxmax()
            row = self.hourly.loc[idx]
            peak_line = (
                f"📈 <b>Peak outlook</b>: ~{row['pm25_pred']:.0f} µg/m³ "
                f"around {row['timestamp'].strftime('%H:%M')}"
            )
            avg = float(self.hourly["pm25_pred"].mean())
            avg_line = f"📊 <b>Average outlook</b>: ~{avg:.0f} µg/m³"

        summary = _summary_line(self)

        parts = [
            f"🌫 <b>HazeGoOut — {escape(label)}</b>",
            "📅 Plan for the rest of today",
            "",
            summary,
            "",
            "✅ <b>Outdoors OK</b>",
            outdoor_block,
            "",
            "🏠 <b>Stay indoors</b>",
            indoor_block,
        ]
        if peak_line or avg_line:
            parts.append("")
            if peak_line:
                parts.append(peak_line)
            if avg_line:
                parts.append(avg_line)
        parts.extend(
            [
                "",
                f"<i>Threshold: ≤ {self.threshold:.0f} µg/m³ (1-hr PM2.5)</i>",
                f"<i>{escape(DISCLAIMER)}</i>",
            ]
        )
        return "\n".join(parts)


def _summary_line(plan: DayPlan) -> str:
    if plan.hourly.empty:
        return "⚠️ Not enough forecast data right now."
    outdoor_h = sum(
        (end - start).total_seconds() / 3600
        for start, end in plan.outdoor_windows
    )
    indoor_h = sum(
        (end - start).total_seconds() / 3600
        for start, end in plan.indoor_windows
    )
    if outdoor_h <= 0:
        return "🔴 <b>Tough air day</b> — better to keep outdoor plans indoors."
    if indoor_h <= 0:
        return "🟢 <b>Clear enough</b> — outdoor windows look good."
    if outdoor_h >= indoor_h:
        return "🟡 <b>Mixed day</b> — go out in the clearer windows below."
    return "🟠 <b>Hazy stretch ahead</b> — pick outdoor slots carefully."


def _fmt_end(end: datetime) -> str:
    if end.hour == 0 and end.minute == 0:
        return "24:00"
    return end.strftime("%H:%M")


def _format_range_block(
    ranges: Iterable[tuple[datetime, datetime]], *, empty: str
) -> str:
    ranges = list(ranges)
    if not ranges:
        return f"• <i>{escape(empty)}</i>"
    lines = [
        f"• <b>{start.strftime('%H:%M')}</b> – <b>{_fmt_end(end)}</b>"
        for start, end in ranges
    ]
    return "\n".join(lines)


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
