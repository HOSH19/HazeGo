# HazeGo

Telegram bot for outdoor-active people in Singapore. Send a **trigger** (`/plan` or `plan` / `haze`) and it asks **where you’ll spend most of the day**, then returns ML-based **outdoors OK** vs **stay indoors** time windows for that NEA region.

Nightly, **GitHub Actions** retrains a LightGBM multi-horizon PM2.5 model and **commits updated weights** into `models/current.joblib`.

## How it works

1. You message the bot: `/plan` (or `plan` / `haze`)
2. Bot asks: “Where are you going to spend most of your day?”
3. You tap **North / South / East / West / Central** (NEA regions)
4. Bot forecasts hourly 1-hr PM2.5 for the rest of today → outdoor / indoor windows
5. **~23:30 SGT** — Actions refreshes history, retrains, and commits `models/` if the quality gate passes
6. Optional: set `GIT_PULL_ON_PLAN=true` so each `/plan` pulls latest weights first

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

4. Open your bot in Telegram → send `/plan` (or `plan`) → pick a region

### Triggers & commands

| Message | Action |
|---------|--------|
| `/plan`, `plan`, `haze` | Ask which area you’re in → day plan |
| `/start` | Welcome + area ask |
| `/now` | Live 1-hr PM2.5 for today’s region |
| `/reload` | `git pull` + reload `models/current.joblib` |
| `/help` | Command list |

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

Optional on the bot host: `GIT_PULL_ON_PLAN=true` to pull latest committed weights before each plan.

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
