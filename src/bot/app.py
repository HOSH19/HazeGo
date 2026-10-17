"""HazeGo Telegram bot — morning region check-in and outdoor/indoor day plan."""

from __future__ import annotations

import logging

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.constants import ParseMode
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
)
from zoneinfo import ZoneInfo

from src.advice.windows import plan_from_forecast
from src.config import (
    DISCLAIMER,
    GIT_PULL_BEFORE_MORNING,
    MORNING_HOUR,
    MORNING_MINUTE,
    OUTDOOR_PM25_MAX,
    REGION_LABELS,
    REGIONS,
    SGT,
    TELEGRAM_BOT_TOKEN,
)
from src.db.schema import init_db
from src.db.users import (
    ensure_user,
    get_daily_region,
    list_subscribed_chat_ids,
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
_scheduler: AsyncIOScheduler | None = None


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


async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    assert update.effective_chat and update.message
    user = update.effective_user
    ensure_user(update.effective_chat.id, user.username if user else None)
    set_subscribed(update.effective_chat.id, True)
    await update.message.reply_text(
        "Welcome to *HazeGo* — daily outdoor air-quality planning for Singapore.\n\n"
        "Each morning I’ll ask where you’ll spend most of the day "
        "(North / South / East / West / Central — NEA regions).\n"
        "You’ll get *outdoors OK* and *stay indoors* time windows from an ML forecast "
        "retrained nightly.\n\n"
        "Commands: /plan /now /stop /help",
        parse_mode=ParseMode.MARKDOWN,
    )
    await update.message.reply_text(
        "Where are you going to spend most of your day?",
        reply_markup=region_keyboard(),
    )


async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    assert update.message
    await update.message.reply_text(
        "/start — subscribe + morning-style check-in\n"
        "/plan — ask region again / refresh today’s plan\n"
        "/now — live PM2.5 for today’s region\n"
        "/stop — unsubscribe from morning asks\n"
        f"_{DISCLAIMER}_",
        parse_mode=ParseMode.MARKDOWN,
    )


async def cmd_stop(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    assert update.effective_chat and update.message
    set_subscribed(update.effective_chat.id, False)
    await update.message.reply_text("Unsubscribed from morning check-ins. /start to return.")


async def cmd_plan(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    assert update.effective_chat and update.message
    ensure_user(update.effective_chat.id)
    set_subscribed(update.effective_chat.id, True)
    await update.message.reply_text(
        "Where are you going to spend most of your day?",
        reply_markup=region_keyboard(),
    )


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


async def morning_checkin(application: Application) -> None:
    logger.info("Running morning check-in job")
    if GIT_PULL_BEFORE_MORNING:
        result = pull_latest()
        logger.info("git pull: %s", result)
        try:
            refresh_model()
        except Exception:  # noqa: BLE001
            logger.exception("model reload after pull failed; keeping previous")

    text = "Good morning! Where are you going to spend most of your day?"
    for chat_id in list_subscribed_chat_ids():
        try:
            await application.bot.send_message(
                chat_id=chat_id,
                text=text,
                reply_markup=region_keyboard(),
            )
        except Exception:  # noqa: BLE001
            logger.exception("failed to message %s", chat_id)


async def post_init(application: Application) -> None:
    global _scheduler
    _scheduler = AsyncIOScheduler(timezone=ZoneInfo(SGT))
    _scheduler.add_job(
        morning_checkin,
        CronTrigger(
            hour=MORNING_HOUR,
            minute=MORNING_MINUTE,
            timezone=ZoneInfo(SGT),
        ),
        kwargs={"application": application},
        id="morning_checkin",
        replace_existing=True,
    )
    _scheduler.start()
    logger.info(
        "Scheduler started; morning ask at %02d:%02d %s",
        MORNING_HOUR,
        MORNING_MINUTE,
        SGT,
    )
    try:
        get_model()
        logger.info("Model loaded")
    except Exception:  # noqa: BLE001
        logger.warning("Model not loaded yet — train before morning ask")


async def post_shutdown(application: Application) -> None:
    global _scheduler
    if _scheduler is not None:
        _scheduler.shutdown(wait=False)
        _scheduler = None


def build_app() -> Application:
    if not TELEGRAM_BOT_TOKEN:
        raise SystemExit("TELEGRAM_BOT_TOKEN is not set. Copy .env.example to .env.")

    init_db()
    application = (
        Application.builder()
        .token(TELEGRAM_BOT_TOKEN)
        .post_init(post_init)
        .post_shutdown(post_shutdown)
        .build()
    )
    application.add_handler(CommandHandler("start", cmd_start))
    application.add_handler(CommandHandler("help", cmd_help))
    application.add_handler(CommandHandler("plan", cmd_plan))
    application.add_handler(CommandHandler("now", cmd_now))
    application.add_handler(CommandHandler("stop", cmd_stop))
    application.add_handler(CommandHandler("reload", cmd_reload))
    application.add_handler(CallbackQueryHandler(on_region, pattern=r"^region:"))
    return application


def main() -> None:
    app = build_app()
    logger.info(
        "HazeGo bot starting (morning %02d:%02d SGT)", MORNING_HOUR, MORNING_MINUTE
    )
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
