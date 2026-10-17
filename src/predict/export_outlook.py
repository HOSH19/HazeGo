"""Export per-region day outlook JSON for the Vercel web app."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from src.advice.windows import build_day_plan
from src.config import OUTDOOR_PM25_MAX, REGIONS, ROOT
from src.predict.forecast import forecast_today, reload_model

DEFAULT_OUT = ROOT / "web" / "public" / "data" / "outlook.json"


def _window_pairs(windows: list) -> list[list[str]]:
    pairs: list[list[str]] = []
    for start, end in windows:
        end_s = "24:00" if end.hour == 0 and end.minute == 0 else end.strftime("%H:%M")
        pairs.append([start.strftime("%H:%M"), end_s])
    return pairs


def _summary_key(plan) -> str:
    if plan.hourly.empty:
        return "unknown"
    outdoor_h = sum((e - s).total_seconds() / 3600 for s, e in plan.outdoor_windows)
    indoor_h = sum((e - s).total_seconds() / 3600 for s, e in plan.indoor_windows)
    if outdoor_h <= 0:
        return "tough"
    if indoor_h <= 0:
        return "clear"
    if outdoor_h >= indoor_h:
        return "mixed"
    return "hazy"


def export_outlook(path: Path | None = None) -> Path:
    path = path or DEFAULT_OUT
    path.parent.mkdir(parents=True, exist_ok=True)
    bundle = reload_model()
    regions: dict = {}
    for region in REGIONS:
        fc = forecast_today(region, bundle=bundle)
        plan = build_day_plan(fc, region)
        hourly = []
        if not plan.hourly.empty:
            for _, row in plan.hourly.iterrows():
                ts = row["timestamp"]
                hourly.append(
                    {
                        "time": ts.strftime("%H:%M"),
                        "iso": ts.isoformat(),
                        "pm25": round(float(row["pm25_pred"]), 1),
                    }
                )
        peak = None
        avg = None
        if not plan.hourly.empty:
            idx = plan.hourly["pm25_pred"].idxmax()
            prow = plan.hourly.loc[idx]
            peak = {
                "pm25": round(float(prow["pm25_pred"]), 1),
                "time": prow["timestamp"].strftime("%H:%M"),
            }
            avg = round(float(plan.hourly["pm25_pred"].mean()), 1)

        regions[region] = {
            "outdoor": _window_pairs(plan.outdoor_windows),
            "indoor": _window_pairs(plan.indoor_windows),
            "hourly": hourly,
            "summary": _summary_key(plan),
            "peak": peak,
            "avg": avg,
        }

    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "threshold": OUTDOOR_PM25_MAX,
        "regions": regions,
    }
    path.write_text(json.dumps(payload, indent=2) + "\n")
    print(f"wrote {path}")
    return path


def main() -> None:
    export_outlook()


if __name__ == "__main__":
    main()
