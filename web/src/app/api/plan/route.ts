import { readFile } from "fs/promises";
import path from "path";
import { NextRequest, NextResponse } from "next/server";
import type { OutlookPayload, Region } from "@/lib/types";
import { buildWindowsFromHourly } from "@/lib/windows";

const REGIONS = new Set<Region>([
  "north",
  "south",
  "east",
  "west",
  "central",
]);

async function loadOutlook(): Promise<OutlookPayload> {
  const file = path.join(process.cwd(), "public", "data", "outlook.json");
  const raw = await readFile(file, "utf8");
  return JSON.parse(raw) as OutlookPayload;
}

export async function GET(req: NextRequest) {
  const region = (req.nextUrl.searchParams.get("region") || "").toLowerCase();
  if (!REGIONS.has(region as Region)) {
    return NextResponse.json(
      { error: "region must be north|south|east|west|central" },
      { status: 400 },
    );
  }

  try {
    const outlook = await loadOutlook();
    const base = outlook.regions[region as Region];
    if (!base) {
      return NextResponse.json({ error: "no outlook for region" }, { status: 404 });
    }

    // Rebuild windows from hourly so threshold env can override later
    const rebuilt = buildWindowsFromHourly(
      base.hourly.map((h) => ({ time: h.time, pm25: h.pm25 })),
      outlook.threshold,
    );

    return NextResponse.json({
      region,
      threshold: outlook.threshold,
      generated_at: outlook.generated_at,
      ...base,
      ...rebuilt,
      hourly: base.hourly,
    });
  } catch (err) {
    return NextResponse.json(
      { error: err instanceof Error ? err.message : "plan failed" },
      { status: 500 },
    );
  }
}
