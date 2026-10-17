# HazeGoOut

Outdoor air-quality planner for Singapore — **Telegram bot** + **Vercel web app**.

Pick where you’ll spend most of the day; get **outdoors OK** vs **stay indoors** time windows.

| Piece | Where it runs |
|--------|----------------|
| Website | **Vercel** (`web/`) |
| Telegram bot | **Railway** (always-on Docker worker — not your laptop) |
| Nightly model retrain | **GitHub Actions** (commits updated `models/` + web outlook) |

GitHub stores the code and runs the nightly train job. It does **not** host a 24/7 bot process — that’s what Railway is for.

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

### 3. Telegram bot (local, optional)

Only for debugging. Production should run on Railway (below).

```bash
cp .env.example .env   # set TELEGRAM_BOT_TOKEN (+ optional DATA_GOV_API_KEY)
python -m src.bot.app
```

**Important:** only one process may poll Telegram at a time. Stop the local bot before Railway runs, or you’ll get conflicts.

### 3b. Host the bot on Railway (always-on)

So the bot works when your laptop is asleep:

1. Push this repo to GitHub (already done)
2. Go to [railway.app](https://railway.app) → **New Project** → **Deploy from GitHub repo** → select this repo
3. Railway should detect [`Dockerfile`](Dockerfile) / [`railway.toml`](railway.toml)
4. Add variables (Variables tab):
   - `TELEGRAM_BOT_TOKEN` = from BotFather
   - `DATA_GOV_API_KEY` = optional
   - `DATABASE_PATH` = `/data/bot.db`
   - `GIT_PULL_ON_PLAN` = `false`
5. (Recommended) Add a **Volume** mounted at `/data` so user prefs survive redeploys
6. Deploy → open [@HazeGoOutBot](https://t.me/HazeGoOutBot) → `/start`

Enable **auto-deploy on push** so nightly Actions model commits wake a fresh bot build.

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
