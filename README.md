# HazeGoOut

Outdoor air-quality planner for Singapore — **Telegram bot** + **Vercel web app**.

Pick where you’ll spend most of the day; get **outdoors OK** vs **stay indoors** time windows.

| Piece | Where it runs |
|--------|----------------|
| Website | **Vercel** (`web/`) — free Hobby plan |
| Telegram bot | **Vercel webhook** (`/api/telegram`) — same free host, no laptop |
| Nightly model retrain | **GitHub Actions** (commits updated `models/` + web outlook) |

GitHub stores code + runs the nightly train. The bot does **not** need an always-on VPS: Telegram pushes updates to Vercel when someone messages the bot.

## How it works

1. **Web:** open the site → tap a region → see today’s plan (+ live PM2.5)
2. **Telegram:** [@HazeGoOutBot](https://t.me/HazeGoOutBot) → `/plan` or `/now` → pick a region
3. **~23:30 SGT:** Actions ingests NEA data, retrains, quality-gates, exports web outlook JSON
4. Railway auto-redeploys on push so the bot picks up new model weights

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

### 3. Telegram bot on Vercel (free, recommended)

The production bot is a **webhook** at `https://hazegoout.vercel.app/api/telegram` — no always-on server, works while your laptop sleeps.

1. In Vercel project **hazegoout** → Settings → Environment Variables, add:
   - `TELEGRAM_BOT_TOKEN`
   - optional `DATA_GOV_API_KEY`, `OUTDOOR_PM25_MAX`
2. Redeploy the site
3. Point Telegram at the webhook (once):

```bash
curl "https://api.telegram.org/bot<TELEGRAM_BOT_TOKEN>/setWebhook?url=https://hazegoout.vercel.app/api/telegram"
```

4. **Stop any local** `python -m src.bot.app` (polling conflicts with the webhook)
5. Message [@HazeGoOutBot](https://t.me/HazeGoOutBot) → `/start`

Local Python bot (`python -m src.bot.app`) is only for offline debugging. Dockerfile/Railway files remain as an optional paid always-on alternative.

### 4. Web app (local)

```bash
# refresh outlook JSON from the trained model
python -m src.predict.export_outlook

cd web
npm install
npm run dev
```

Open [http://localhost:3000](http://localhost:3000).

### 5. Deploy to Vercel

1. Import the GitHub repo in [Vercel](https://vercel.com/new)
2. Set **Root Directory** to `web`
3. Framework: Next.js (auto)
4. Optional env: `DATA_GOV_API_KEY` (higher rate limits for `/api/pm25`)
5. Deploy

The site reads `public/data/outlook.json` (updated by nightly Actions) and live NEA readings via `/api/pm25`.

### Triggers & commands

| Message | Action |
|---------|--------|
| `/plan`, `plan`, `haze` | Ask which area you’re in → day plan |
| `/start` | Welcome + commands |
| `/now` | Live 1-hr PM2.5 for today’s region |
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
- `web/public/data/outlook.json` — web app day outlook

Optional on the bot host: `GIT_PULL_ON_PLAN=true` to pull latest committed weights before each plan.

## Project layout

```
src/                 # Python: ingest, train, Telegram bot
web/                 # Next.js app (deploy Root Directory = web)
  public/data/outlook.json
  src/app/api/plan   # region day plan
  src/app/api/pm25   # live NEA proxy
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
