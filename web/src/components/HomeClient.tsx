"use client";

import { useState, useTransition } from "react";
import { PlanCard } from "@/components/PlanCard";
import { REGIONS, type Region, type SummaryKey } from "@/lib/types";

type PlanState = {
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

export function HomeClient() {
  const [region, setRegion] = useState<Region | null>(null);
  const [plan, setPlan] = useState<PlanState | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [pending, startTransition] = useTransition();

  function loadPlan(next: Region) {
    setRegion(next);
    setError(null);
    startTransition(async () => {
      try {
        const [planRes, liveRes] = await Promise.all([
          fetch(`/api/plan?region=${next}`),
          fetch("/api/pm25"),
        ]);
        if (!planRes.ok) {
          const body = await planRes.json().catch(() => ({}));
          throw new Error(body.error || "Could not load plan");
        }
        const planJson = await planRes.json();
        let live: number | null = null;
        if (liveRes.ok) {
          const liveJson = await liveRes.json();
          live = liveJson.readings?.[next] ?? null;
        }
        setPlan({ ...planJson, live });
      } catch (err) {
        setPlan(null);
        setError(err instanceof Error ? err.message : "Something went wrong");
      }
    });
  }

  return (
    <div className="mx-auto flex w-full max-w-xl flex-col gap-8 px-4 py-10 sm:py-14">
      <header className="space-y-3 text-center sm:text-left">
        <p className="text-sm tracking-[0.25em] text-[var(--sand)]">HAZEGO</p>
        <h1 className="font-[family-name:var(--font-display)] text-4xl font-semibold leading-tight tracking-tight sm:text-5xl">
          Should you go out today?
        </h1>
        <p className="max-w-md text-[var(--mist)]">
          Pick where you&apos;ll spend most of the day. We&apos;ll show outdoor vs
          indoor windows from an ML PM2.5 outlook for Singapore.
        </p>
      </header>

      <section className="space-y-3">
        <h2 className="text-sm font-medium text-[var(--foam)]">
          📍 Where will you be?
        </h2>
        <div className="grid grid-cols-2 gap-2 sm:grid-cols-3">
          {REGIONS.map((r) => {
            const active = region === r.id;
            return (
              <button
                key={r.id}
                type="button"
                onClick={() => loadPlan(r.id)}
                disabled={pending}
                className={`rounded-2xl border px-3 py-3 text-sm font-semibold transition duration-200 ${
                  active
                    ? "border-[var(--sand)] bg-[var(--sand)]/20 text-[var(--foam)] shadow-[0_0_0_1px_rgba(216,195,165,0.35)]"
                    : "border-white/10 bg-white/[0.04] text-[var(--mist)] hover:border-white/25 hover:bg-white/[0.08] hover:text-[var(--foam)]"
                } disabled:opacity-60`}
              >
                {r.label}
              </button>
            );
          })}
        </div>
      </section>

      {pending && (
        <p className="text-sm text-[var(--mist)] animate-pulse">
          Building today&apos;s plan…
        </p>
      )}
      {error && (
        <p className="rounded-xl border border-[var(--bad)]/40 bg-[var(--bad)]/10 px-4 py-3 text-sm">
          {error}
        </p>
      )}
      {plan && !pending && <PlanCard plan={plan} />}

      <footer className="space-y-1 pt-4 text-center text-xs text-[var(--mist)]/70 sm:text-left">
        <p>Data: NEA via data.gov.sg · Forecast: LightGBM (nightly retrain)</p>
        <p>Also on Telegram — message the bot with /plan</p>
      </footer>
    </div>
  );
}
