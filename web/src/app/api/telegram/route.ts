import { NextRequest, NextResponse } from "next/server";
import {
  COMMANDS_HTML,
  answerCallbackQuery,
  editMessageText,
  regionKeyboard,
  sendMessage,
  type TgUpdate,
} from "@/lib/telegram";
import {
  fetchLivePm25,
  formatPlanHtml,
  loadOutlook,
} from "@/lib/planMessage";
import type { Region } from "@/lib/types";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";
export const maxDuration = 30;

const REGIONS = new Set<Region>([
  "north",
  "south",
  "east",
  "west",
  "central",
]);

const TRIGGER =
  /^\s*(plan|haze|go\s*out|outdoors?|check|today)\s*$/i;

async function askRegion(chatId: number, intent: "plan" | "now") {
  const prompt =
    intent === "plan"
      ? "📍 <b>Where will you spend most of today?</b>"
      : "📍 <b>Where are you right now?</b>";
  await sendMessage(chatId, prompt, {
    reply_markup: regionKeyboard(intent),
  });
}

async function handleMessage(update: TgUpdate) {
  const msg = update.message;
  if (!msg?.text) return;
  const chatId = msg.chat.id;
  const text = msg.text.trim();
  const cmd = text.split(/\s+/)[0].split("@")[0].toLowerCase();

  if (cmd === "/start") {
    await sendMessage(
      chatId,
      "🌫 <b>Welcome to HazeGoOut!</b>\n" +
        "SG outdoor air quality planner [beta].\n\n" +
        `${COMMANDS_HTML}\n\n` +
        "👉 Send /plan to get today’s windows.",
    );
    return;
  }
  if (cmd === "/help") {
    await sendMessage(chatId, `📋 <b>Commands</b>\n${COMMANDS_HTML}`);
    return;
  }
  if (cmd === "/plan") {
    await askRegion(chatId, "plan");
    return;
  }
  if (cmd === "/now") {
    await askRegion(chatId, "now");
    return;
  }
  if (TRIGGER.test(text)) {
    await askRegion(chatId, "plan");
  }
}

async function handleCallback(update: TgUpdate) {
  const cb = update.callback_query;
  if (!cb?.data || !cb.message) return;
  await answerCallbackQuery(cb.id);

  let [intent, region] = cb.data.split(":") as [string, Region];
  if (intent === "region") intent = "plan";
  if ((intent !== "plan" && intent !== "now") || !REGIONS.has(region)) {
    await editMessageText(
      cb.message.chat.id,
      cb.message.message_id,
      "⚠️ Unknown region.",
    );
    return;
  }

  const chatId = cb.message.chat.id;
  const label =
    region.charAt(0).toUpperCase() + region.slice(1);

  if (intent === "now") {
    await editMessageText(
      chatId,
      cb.message.message_id,
      `⏱ Checking <b>${label}</b>…`,
    );
    const value = await fetchLivePm25(region);
    if (value == null) {
      await sendMessage(chatId, "⚠️ Can’t fetch live PM2.5 right now.");
      return;
    }
    const threshold = Number(process.env.OUTDOOR_PM25_MAX || 55);
    const band =
      value <= threshold ? "✅ Outdoors OK" : "🏠 Stay indoors";
    await sendMessage(
      chatId,
      `⏱ <b>${label} now</b>\n🌫 <b>${value.toFixed(0)}</b> µg/m³\n${band}`,
    );
    return;
  }

  await editMessageText(
    chatId,
    cb.message.message_id,
    `👍 Planning for <b>${label}</b>…`,
  );
  try {
    const outlook = await loadOutlook();
    const base = outlook.regions[region];
    if (!base) {
      await sendMessage(chatId, "⚠️ No outlook for that region yet.");
      return;
    }
    await sendMessage(chatId, formatPlanHtml(region, outlook, base));
  } catch (err) {
    console.error(err);
    await sendMessage(
      chatId,
      `⚠️ Couldn’t build today’s plan: ${err instanceof Error ? err.message : "error"}`,
    );
  }
}

export async function POST(req: NextRequest) {
  try {
    if (!process.env.TELEGRAM_BOT_TOKEN) {
      return NextResponse.json(
        { error: "TELEGRAM_BOT_TOKEN missing" },
        { status: 500 },
      );
    }
    const secret = process.env.TELEGRAM_WEBHOOK_SECRET;
    if (secret) {
      const header = req.headers.get("x-telegram-bot-api-secret-token");
      if (header !== secret) {
        return NextResponse.json({ error: "unauthorized" }, { status: 401 });
      }
    }

    const update = (await req.json()) as TgUpdate;
    if (update.callback_query) {
      await handleCallback(update);
    } else if (update.message) {
      await handleMessage(update);
    }
    return NextResponse.json({ ok: true });
  } catch (err) {
    console.error("telegram webhook failed", err);
    // Still 200 so Telegram doesn't retry forever on our bugs
    return NextResponse.json({ ok: true });
  }
}

/** Health / webhook setup check */
export async function GET() {
  return NextResponse.json({
    ok: true,
    service: "HazeGoOut Telegram webhook",
    hint: "POST Telegram updates here. Set webhook to this URL.",
  });
}
