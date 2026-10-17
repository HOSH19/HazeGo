import { NextResponse } from "next/server";

const PM25_URL = "https://api-open.data.gov.sg/v2/real-time/api/pm25";

export const revalidate = 300;

export async function GET() {
  try {
    const headers: HeadersInit = { Accept: "application/json" };
    if (process.env.DATA_GOV_API_KEY) {
      headers["x-api-key"] = process.env.DATA_GOV_API_KEY;
    }
    const res = await fetch(PM25_URL, {
      headers,
      next: { revalidate: 300 },
    });
    if (!res.ok) {
      return NextResponse.json(
        { error: `NEA API ${res.status}` },
        { status: 502 },
      );
    }
    const payload = await res.json();
    if (payload.code !== 0) {
      return NextResponse.json(
        { error: payload.errorMsg || "NEA API error" },
        { status: 502 },
      );
    }
    const item = payload.data?.items?.[0];
    const readings = item?.readings?.pm25_one_hourly || {};
    return NextResponse.json({
      timestamp: item?.timestamp ?? null,
      readings: {
        north: readings.north ?? null,
        south: readings.south ?? null,
        east: readings.east ?? null,
        west: readings.west ?? null,
        central: readings.central ?? null,
      },
    });
  } catch (err) {
    return NextResponse.json(
      { error: err instanceof Error ? err.message : "fetch failed" },
      { status: 500 },
    );
  }
}
