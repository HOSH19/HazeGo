import type { RegionOutlook, SummaryKey } from "./types";

const DEFAULT_THRESHOLD = 55;

export function buildWindowsFromHourly(
  hourly: { time: string; pm25: number }[],
  threshold = DEFAULT_THRESHOLD,
): Pick<RegionOutlook, "outdoor" | "indoor" | "summary" | "peak" | "avg"> {
  const outdoor: [string, string][] = [];
  const indoor: [string, string][] = [];

  const pushRange = (
    bucket: [string, string][],
    start: string | null,
    end: string | null,
  ) => {
    if (start && end) bucket.push([start, end]);
  };

  let mode: "out" | "in" | null = null;
  let rangeStart: string | null = null;
  let prevEnd: string | null = null;

  const hourEnd = (time: string) => {
    const [h, m] = time.split(":").map(Number);
    const next = (h + 1) % 24;
    if (h === 23) return "24:00";
    return `${String(next).padStart(2, "0")}:${String(m).padStart(2, "0")}`;
  };

  for (const row of hourly) {
    const nextMode: "out" | "in" = row.pm25 <= threshold ? "out" : "in";
    const end = hourEnd(row.time);
    if (mode === null) {
      mode = nextMode;
      rangeStart = row.time;
      prevEnd = end;
      continue;
    }
    if (nextMode === mode) {
      prevEnd = end;
      continue;
    }
    pushRange(mode === "out" ? outdoor : indoor, rangeStart, prevEnd);
    mode = nextMode;
    rangeStart = row.time;
    prevEnd = end;
  }
  if (mode && rangeStart && prevEnd) {
    pushRange(mode === "out" ? outdoor : indoor, rangeStart, prevEnd);
  }

  let peak: RegionOutlook["peak"] = null;
  let avg: number | null = null;
  if (hourly.length) {
    const top = hourly.reduce((a, b) => (a.pm25 >= b.pm25 ? a : b));
    peak = { pm25: top.pm25, time: top.time };
    avg =
      Math.round(
        (hourly.reduce((s, r) => s + r.pm25, 0) / hourly.length) * 10,
      ) / 10;
  }

  const outdoorH = outdoor.length;
  const indoorH = indoor.length;
  let summary: SummaryKey = "unknown";
  if (!hourly.length) summary = "unknown";
  else if (!outdoorH) summary = "tough";
  else if (!indoorH) summary = "clear";
  else if (outdoorH >= indoorH) summary = "mixed";
  else summary = "hazy";

  return { outdoor, indoor, summary, peak, avg };
}
