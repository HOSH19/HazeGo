const API = "https://api.telegram.org";

export type TgUpdate = {
  update_id: number;
  message?: {
    message_id: number;
    chat: { id: number };
    text?: string;
    from?: { username?: string };
  };
  callback_query?: {
    id: string;
    data?: string;
    message?: { message_id: number; chat: { id: number } };
  };
};

function token(): string {
  const t = process.env.TELEGRAM_BOT_TOKEN;
  if (!t) throw new Error("TELEGRAM_BOT_TOKEN is not set");
  return t;
}

async function tg(method: string, body: Record<string, unknown>) {
  const res = await fetch(`${API}/bot${token()}/${method}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  const json = (await res.json()) as { ok: boolean; description?: string };
  if (!json.ok) {
    console.error("Telegram API error", method, json);
  }
  return json;
}

export async function sendMessage(
  chatId: number,
  text: string,
  extra: Record<string, unknown> = {},
) {
  return tg("sendMessage", {
    chat_id: chatId,
    text,
    parse_mode: "HTML",
    ...extra,
  });
}

export async function editMessageText(
  chatId: number,
  messageId: number,
  text: string,
) {
  return tg("editMessageText", {
    chat_id: chatId,
    message_id: messageId,
    text,
    parse_mode: "HTML",
  });
}

export async function answerCallbackQuery(id: string) {
  return tg("answerCallbackQuery", { callback_query_id: id });
}

export function regionKeyboard(intent: "plan" | "now") {
  const regions = [
    ["North", "north"],
    ["South", "south"],
    ["East", "east"],
    ["West", "west"],
    ["Central", "central"],
  ] as const;
  return {
    inline_keyboard: regions.map(([label, id]) => [
      { text: label, callback_data: `${intent}:${id}` },
    ]),
  };
}

export const COMMANDS_HTML =
  "📍 /plan — today’s outdoor / indoor windows\n" +
  "⏱ /now — live PM2.5 (pick a region)\n" +
  "❓ /help — command list";
