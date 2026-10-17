# HazeGo

Telegram bot for outdoor-active people in Singapore. Each morning it asks **where you’ll spend most of the day**, then returns ML-based **outdoors OK** vs **stay indoors** time windows for that NEA region.

Nightly, **GitHub Actions** retrains a LightGBM multi-horizon PM2.5 model and **commits updated weights** into `models/current.joblib` (same pattern as checking model artifacts into git).

## How it works

1. **~6:30 SGT** — bot asks: “Where are you going to spend most of your day?”
2. You tap **North / South / East / West / Central** (NEA regions)
3. Bot forecasts hourly 1-hr PM2.5 for the rest of today and merges hours into outdoor / indoor windows
4. **~23:30 SGT** — Actions refreshes `data/history.parquet`, retrains, quality-gates MAE, and commits `models/` if accepted
5. Before the next morning ask, the bot **`git pull`s** so it loads the new weights

## Quick start

### 1. Python env

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
pip install -e .
```

### 2. Seed history + model (once)

```bash
# ~60 days of NEA PM2.5 (skip weather to avoid rate limits)
python -m src.ingest.history --days 60 --skip-weather

# Train and write models/current.joblib
python -m src.train.retrain_daily --no-refresh
```

Optional: include weather features on a smaller refresh when you have a [data.gov.sg API key](https://guide.data.gov.sg/developer-guide/api-overview/api-rate-limits):

```bash
export DATA_GOV_API_KEY=...
python -m src.ingest.history --days 14   # with weather
python -m src.train.retrain_daily --no-refresh
```

### 3. Telegram bot

1. Talk to [@BotFather](https://t.me/BotFather) → `/newbot` → copy the token
2. Configure env:

```bash
cp .env.example .env
# set TELEGRAM_BOT_TOKEN=...
```

3. Run:

```bash
python -m src.bot.app
```

4. Open your bot in Telegram → `/start` → pick a region

### Commands

| Command | Action |
|---------|--------|
| `/start` | Subscribe + region check-in |
| `/plan` | Ask region again / refresh plan |
| `/now` | Live 1-hr PM2.5 for today’s region |
| `/reload` | `git pull` + reload `models/current.joblib` |
| `/stop` | Unsubscribe from morning asks |

## GitHub Actions nightly retrain

Workflow: [`.github/workflows/nightly-retrain.yml`](.github/workflows/nightly-retrain.yml)

- **Schedule:** `30 15 * * *` UTC (= 23:30 SGT)
- **Manual:** Actions → “Nightly model retrain” → Run workflow (optional `backfill_days`)
- **Permissions:** `contents: write` (default `GITHUB_TOKEN`) to commit artifacts
- **Optional secret:** `DATA_GOV_API_KEY` for higher data.gov.sg rate limits
- **Quality gate:** new holdout MAE must not be worse than the previous model by more than `RETRAIN_MAX_MAE_REGRESSION` (default 15%)
- **Loop avoidance:** commit message includes `[skip ci]`

Committed on success:

- `models/current.joblib` — LightGBM bundle
- `models/meta.json` — train metadata
- `data/history.parquet` — training history
- `data/retrain_metrics.csv` — append-only MAE log

The bot host should be a git checkout of this repo with network access so morning `git pull` works (`GIT_PULL_BEFORE_MORNING=true`).

## Project layout

```
src/
  ingest/     # NEA PM2.5 + weather → history.parquet
  features/   # lags / rolling / calendar features
  train/      # retrain_daily (used by Actions)
  predict/    # load model → hourly outlook
  advice/     # outdoor / indoor windows
  bot/        # Telegram + morning scheduler
  db/         # SQLite user prefs / check-ins
  jobs/       # git pull helper
.github/workflows/nightly-retrain.yml
models/current.joblib
data/history.parquet
```

## Model

- **Algorithm:** LightGBM regressors, one per horizon (1–24h)
- **Target:** regional 1-hr PM2.5 (µg/m³)
- **Features:** PM2.5 lags & rolling stats, hour/dow/month, region, optional weather lags
- **Advice rule:** hour is “outdoors OK” if predicted PM2.5 ≤ `OUTDOOR_PM25_MAX` (default 55); otherwise “stay indoors”

This is an air-quality planning aid, **not medical advice**.

## Config (`.env`)

See [`.env.example`](.env.example) for `TELEGRAM_BOT_TOKEN`, `MORNING_HOUR` / `MORNING_MINUTE`, `OUTDOOR_PM25_MAX`, `DATA_GOV_API_KEY`, and retrain gate settings.
