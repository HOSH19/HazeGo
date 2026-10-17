"""Shared configuration for HazeGo."""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data"
MODELS_DIR = ROOT / "models"
HISTORY_PATH = DATA_DIR / "history.parquet"
METRICS_PATH = DATA_DIR / "retrain_metrics.csv"
MODEL_PATH = MODELS_DIR / "current.joblib"
MODEL_META_PATH = MODELS_DIR / "meta.json"

REGIONS = ("north", "south", "east", "west", "central")
REGION_LABELS = {
    "north": "North",
    "south": "South",
    "east": "East",
    "west": "West",
    "central": "Central",
}

SGT = "Asia/Singapore"
PM25_API = "https://api-open.data.gov.sg/v2/real-time/api/pm25"
WEATHER_APIS = {
    "rainfall": "https://api-open.data.gov.sg/v2/real-time/api/rainfall",
    "temperature": "https://api-open.data.gov.sg/v2/real-time/api/air-temperature",
    "wind_speed": "https://api-open.data.gov.sg/v2/real-time/api/wind-speed",
}

HORIZONS = tuple(range(1, 25))  # 1h .. 24h ahead
LAGS = (1, 2, 3, 6, 12, 24)
ROLLING_WINDOWS = (3, 6, 12, 24)

OUTDOOR_PM25_MAX = float(os.getenv("OUTDOOR_PM25_MAX", "55"))
MORNING_HOUR = int(os.getenv("MORNING_HOUR", "6"))
MORNING_MINUTE = int(os.getenv("MORNING_MINUTE", "30"))
GIT_PULL_BEFORE_MORNING = os.getenv("GIT_PULL_BEFORE_MORNING", "true").lower() in {
    "1",
    "true",
    "yes",
}
DATABASE_PATH = Path(os.getenv("DATABASE_PATH", str(DATA_DIR / "bot.db")))
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
DATA_GOV_API_KEY = os.getenv("DATA_GOV_API_KEY", "")
RETRAIN_MAX_MAE_REGRESSION = float(os.getenv("RETRAIN_MAX_MAE_REGRESSION", "0.15"))

# Seed / backfill defaults
DEFAULT_BACKFILL_DAYS = 90
DISCLAIMER = "PM2.5 outlook for outdoor planning — not medical advice."


def api_headers() -> dict[str, str]:
    headers = {"Accept": "application/json"}
    if DATA_GOV_API_KEY:
        headers["x-api-key"] = DATA_GOV_API_KEY
    return headers
