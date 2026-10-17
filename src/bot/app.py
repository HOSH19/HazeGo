"""HazeGo Telegram bot — on-demand region check-in and outdoor/indoor day plan."""

from __future__ import annotations

import logging
import re

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.constants import ParseMode
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

from src.advice.windows import plan_from_forecast
from src.config import (
    DISCLAIMER,
    GIT_PULL_ON_PLAN,
    OUTDOOR_PM25_MAX,
    REGION_LABELS,
    REGIONS,
    TELEGRAM_BOT_TOKEN,
)
from src.db.schema import init_db
from src.db.users import (
    ensure_user,
    get_daily_region,
    set_daily_region,
    set_subscribed,
)
from src.ingest.pm25 import fetch_pm25_latest, today_sgt
from src.jobs.git_pull import pull_latest
from src.predict.forecast import forecast_today, reload_model

logging.basicConfig(
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger("hazego")

_MODEL = None

# Plain-text triggers (any of these → ask for region)
_TRIGGER_RE = re.compile(
    r"^\s*(plan|haze|go\s*out|outdoors?|check|today|/plan)\s*$",
    re.IGNORECASE,
)


def region_keyboard() -> InlineKeyboardMarkup:
    buttons = [
        [InlineKeyboardButton(REGION_LABELS[r], callback_data=f"region:{r}")]
        for r in REGIONS
    ]
    return InlineKeyboardMarkup(buttons)


def get_model():
    global _MODEL
    if _MODEL is None:
        _MODEL = reload_model()
    return _MODEL


def refresh_model() -> None:
    global _MODEL
    _MODEL = reload_model()


async def ask_region(update: Update, *, preface: str | None = None) -> None:
    assert update.effective_chat and update.message
    ensure_user(
        update.effective_chat.id,
        update.effective_user.username if update.effective_user else None,
    )
    set_subscribed(update.effective_chat.id, True)

    if GIT_PULL_ON_PLAN:
        result = pull_latest()
        logger.info("git pull on plan: %s", result)
        try:
            refresh_model()
        except Exception:  # noqa: BLE001
            logger.exception("model reload after pull failed; keeping previous")

    if preface:
        await update.message.reply_text(preface, parse_mode=ParseMode.MARKDOWN)
    await update.message.reply_text(
        "Where are you going to spend most of your day?",
        reply_markup=region_keyboard(),
    )


async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await ask_region(
        update,
        preface=(
            "Welcome to *HazeGo* — outdoor air-quality planning for Singapore.\n\n"
            "Send /plan (or message *plan* / *haze*) anytime and I’ll ask which "
            "NEA region you’ll be in, then give *outdoors OK* vs *stay indoors* windows.\n\n"
            "Commands: /plan /now /help"
        ),
    )


async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    assert update.message
    await update.message.reply_text(
        "*Triggers* (ask for your area):\n"
        "/plan — or just type `plan` / `haze`\n\n"
        "*Other*\n"
        "/now — live PM2.5 for today’s region\n"
        "/reload — git pull + reload model\n"
        "/start — welcome + area ask\n"
        f"_{DISCLAIMER}_",
        parse_mode=ParseMode.MARKDOWN,
    )


async def cmd_plan(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await ask_region(update)


async def on_trigger_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Any plain-text trigger message starts the area check-in."""
    assert update.message and update.message.text
    if _TRIGGER_RE.match(update.message.text):
        await ask_region(update)


async def cmd_now(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    assert update.effective_chat and update.message
    chat_id = update.effective_chat.id
    ensure_user(chat_id)
    region = get_daily_region(chat_id, today_sgt().isoformat())
    if not region:
        await update.message.reply_text(
            "Pick a region first:", reply_markup=region_keyboard()
        )
        return
    try:
        live = fetch_pm25_latest()
        row = live[live["region"] == region]
        if row.empty:
            await update.message.reply_text("Could not fetch live PM2.5 right now.")
            return
        value = float(row.iloc[0]["pm25"])
        band = "Outdoors OK" if value <= OUTDOOR_PM25_MAX else "Stay indoors"
        label = REGION_LABELS.get(region, region)
        await update.message.reply_text(
            f"*{label}* now: *{value:.0f}* µg/m³ 1-hr PM2.5 → *{band}*\n_{DISCLAIMER}_",
            parse_mode=ParseMode.MARKDOWN,
        )
    except Exception as exc:  # noqa: BLE001
        logger.exception("/now failed")
        await update.message.reply_text(f"Live fetch failed: {exc}")


async def cmd_reload(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    assert update.message
    msg = pull_latest()
    try:
        refresh_model()
        meta = get_model().get("meta") or {}
        await update.message.reply_text(
            f"Pulled:\n{msg}\n\nModel MAE={meta.get('holdout_mae')} "
            f"trained={meta.get('trained_at_utc')}"
        )
    except Exception as exc:  # noqa: BLE001
        await update.message.reply_text(f"Pull finished, reload failed: {exc}\n{msg}")


async def on_region(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    assert query and query.data and update.effective_chat
    await query.answer()
    if not query.data.startswith("region:"):
        return
    region = query.data.split(":", 1)[1]
    if region not in REGIONS:
        await query.edit_message_text("Unknown region.")
        return

    chat_id = update.effective_chat.id
    ensure_user(chat_id)
    set_daily_region(chat_id, region, today_sgt().isoformat())
    label = REGION_LABELS[region]
    await query.edit_message_text(
        f"Got it — planning for *{label}*…", parse_mode=ParseMode.MARKDOWN
    )

    try:
        bundle = get_model()
        fc = forecast_today(region, bundle=bundle)
        text = plan_from_forecast(fc, region).replace("**", "*")
        await context.bot.send_message(
            chat_id=chat_id,
            text=text,
            parse_mode=ParseMode.MARKDOWN,
        )
    except Exception as exc:  # noqa: BLE001
        logger.exception("forecast failed")
        await context.bot.send_message(
            chat_id=chat_id,
            text=f"Could not build today’s plan: {exc}",
        )


async def post_init(application: Application) -> None:
    try:
        get_model()
        logger.info("Model loaded")
    except Exception:  # noqa: BLE001
        logger.warning("Model not loaded yet — run training before /plan")


def build_app() -> Application:
    if not TELEGRAM_BOT_TOKEN:
        raise SystemExit("TELEGRAM_BOT_TOKEN is not set. Copy .env.example to .env.")

    init_db()
    application = (
        Application.builder()
        .token(TELEGRAM_BOT_TOKEN)
        .post_init(post_init)
        .build()
    )
    application.add_handler(CommandHandler("start", cmd_start))
    application.add_handler(CommandHandler("help", cmd_help))
    application.add_handler(CommandHandler("plan", cmd_plan))
    application.add_handler(CommandHandler("now", cmd_now))
    application.add_handler(CommandHandler("reload", cmd_reload))
    application.add_handler(CallbackQueryHandler(on_region, pattern=r"^region:"))
    application.add_handler(
        MessageHandler(filters.TEXT & ~filters.COMMAND, on_trigger_text)
    )
    return application


def main() -> None:
    app = build_app()
    logger.info("HazeGo bot starting (on-demand /plan trigger; no morning schedule)")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
