"use client";

import { SUMMARY_COPY, type Region, type SummaryKey } from "@/lib/types";

type Plan = {
  region: Region;
  outdoor: [string, string][];
  indoor: [string, string][];
  summary: SummaryKey;
  peak: { pm25: number; time: string } | null;
  avg: number | null;
  threshold: number;
  generated_at: string;
  live?: number | null;
};

const LABELS: Record<Region, string> = {
  north: "North",
  south: "South",
  east: "East",
  west: "West",
  central: "Central",
};

function WindowList({
  title,
  emoji,
  ranges,
  tone,
}: {
  title: string;
  emoji: string;
  ranges: [string, string][];
  tone: "ok" | "bad";
}) {
  const border =
    tone === "ok" ? "border-[var(--ok)]/40" : "border-[var(--bad)]/40";
  return (
    <section
      className={`rounded-2xl border ${border} bg-white/[0.04] px-4 py-4 backdrop-blur-sm`}
    >
      <h3 className="mb-3 text-sm font-semibold tracking-wide text-[var(--foam)]">
        {emoji} {title}
      </h3>
      {ranges.length === 0 ? (
        <p className="text-sm text-[var(--mist)]">None for the rest of today</p>
      ) : (
        <ul className="space-y-2">
          {ranges.map(([start, end]) => (
            <li
              key={`${start}-${end}`}
              className="flex items-center justify-between rounded-xl bg-black/20 px-3 py-2 text-base"
            >
              <span className="font-semibold tabular-nums">
                {start} – {end}
              </span>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}

export function PlanCard({ plan }: { plan: Plan }) {
  const copy = SUMMARY_COPY[plan.summary] ?? SUMMARY_COPY.unknown;
  const label = LABELS[plan.region];
  const liveOk =
    plan.live != null ? plan.live <= plan.threshold : null;

  return (
    <article className="space-y-5 rounded-3xl border border-white/10 bg-white/[0.06] p-5 shadow-[0_20px_60px_rgba(0,0,0,0.35)] backdrop-blur-md sm:p-7">
      <header className="space-y-1">
        <p className="text-xs uppercase tracking-[0.2em] text-[var(--sand)]">
          Today&apos;s plan
        </p>
        <h2 className="font-[family-name:var(--font-display)] text-3xl font-semibold tracking-tight sm:text-4xl">
          {label}
        </h2>
      </header>

      <div className="rounded-2xl bg-black/25 px-4 py-3">
        <p className="text-lg font-medium">
          {copy.emoji} {copy.title}
        </p>
        <p className="mt-1 text-sm text-[var(--mist)]">{copy.blurb}</p>
      </div>

      {plan.live != null && (
        <div className="flex flex-wrap items-end gap-3 rounded-2xl border border-white/10 px-4 py-3">
          <div>
            <p className="text-xs uppercase tracking-wider text-[var(--mist)]">
              Live now
            </p>
            <p className="text-3xl font-semibold tabular-nums">
              {plan.live}
              <span className="ml-1 text-sm font-normal text-[var(--mist)]">
                µg/m³
              </span>
            </p>
          </div>
          <p className="pb-1 text-sm">
            {liveOk ? "✅ Outdoors OK" : "🏠 Stay indoors"}
          </p>
        </div>
      )}

      <div className="grid gap-3 sm:grid-cols-2">
        <WindowList
          title="Outdoors OK"
          emoji="✅"
          ranges={plan.outdoor}
          tone="ok"
        />
        <WindowList
          title="Stay indoors"
          emoji="🏠"
          ranges={plan.indoor}
          tone="bad"
        />
      </div>

      <dl className="grid grid-cols-2 gap-3 text-sm text-[var(--mist)]">
        {plan.peak && (
          <div className="rounded-xl bg-black/20 px-3 py-2">
            <dt>📈 Peak outlook</dt>
            <dd className="mt-1 font-medium text-[var(--foam)]">
              ~{Math.round(plan.peak.pm25)} µg/m³ around {plan.peak.time}
            </dd>
          </div>
        )}
        {plan.avg != null && (
          <div className="rounded-xl bg-black/20 px-3 py-2">
            <dt>📊 Average outlook</dt>
            <dd className="mt-1 font-medium text-[var(--foam)]">
              ~{Math.round(plan.avg)} µg/m³
            </dd>
          </div>
        )}
      </dl>

      <p className="text-xs leading-relaxed text-[var(--mist)]/80">
        Threshold ≤ {plan.threshold} µg/m³ (1-hr PM2.5). ML outlook generated{" "}
        {new Date(plan.generated_at).toLocaleString("en-SG", {
          timeZone: "Asia/Singapore",
        })}{" "}
        · not medical advice.
      </p>
    </article>
  );
}
