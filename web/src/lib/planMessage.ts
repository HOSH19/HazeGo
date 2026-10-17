import { readFile } from "fs/promises";
import path from "path";
import {
  SUMMARY_COPY,
  type OutlookPayload,
  type Region,
  type RegionOutlook,
} from "@/lib/types";
import { buildWindowsFromHourly } from "@/lib/windows";

const LABELS: Record<Region, string> = {
  north: "North",
  south: "South",
  east: "East",
  west: "West",
  central: "Central",
};

export async function loadOutlook(): Promise<OutlookPayload> {
  const file = path.join(process.cwd(), "public", "data", "outlook.json");
  const raw = await readFile(file, "utf8");
  return JSON.parse(raw) as OutlookPayload;
}

function formatRanges(ranges: [string, string][], empty: string): string {
  if (!ranges.length) return `• <i>${empty}</i>`;
  return ranges.map(([a, b]) => `• <b>${a}</b> – <b>${b}</b>`).join("\n");
}

export function formatPlanHtml(
  region: Region,
  outlook: OutlookPayload,
  base: RegionOutlook,
): string {
  const rebuilt = buildWindowsFromHourly(
    base.hourly.map((h) => ({ time: h.time, pm25: h.pm25 })),
    outlook.threshold,
  );
  const copy = SUMMARY_COPY[rebuilt.summary] ?? SUMMARY_COPY.unknown;
  const label = LABELS[region];
  const parts = [
    `🌫 <b>HazeGoOut — ${label}</b>`,
    "📅 Plan for the rest of today",
    "",
    `${copy.emoji} <b>${copy.title}</b> — ${copy.blurb}`,
    "",
    "✅ <b>Outdoors OK</b>",
    formatRanges(rebuilt.outdoor, "None for the rest of today"),
    "",
    "🏠 <b>Stay indoors</b>",
    formatRanges(rebuilt.indoor, "None for the rest of today"),
  ];
  if (rebuilt.peak) {
    parts.push(
      "",
      `📈 <b>Peak outlook</b>: ~${Math.round(rebuilt.peak.pm25)} µg/m³ around ${rebuilt.peak.time}`,
    );
  }
  if (rebuilt.avg != null) {
    parts.push(
      `📊 <b>Average outlook</b>: ~${Math.round(rebuilt.avg)} µg/m³`,
    );
  }
  parts.push(
    "",
    `<i>Threshold: ≤ ${outlook.threshold} µg/m³ (1-hr PM2.5)</i>`,
    "<i>PM2.5 outlook for outdoor planning — not medical advice.</i>",
  );
  return parts.join("\n");
}

export async function fetchLivePm25(
  region: Region,
): Promise<number | null> {
  const headers: HeadersInit = { Accept: "application/json" };
  if (process.env.DATA_GOV_API_KEY) {
    headers["x-api-key"] = process.env.DATA_GOV_API_KEY;
  }
  const res = await fetch(
    "https://api-open.data.gov.sg/v2/real-time/api/pm25",
    { headers, cache: "no-store" },
  );
  if (!res.ok) return null;
  const payload = await res.json();
  if (payload.code !== 0) return null;
  const readings = payload.data?.items?.[0]?.readings?.pm25_one_hourly || {};
  const v = readings[region];
  return typeof v === "number" ? v : null;
}
