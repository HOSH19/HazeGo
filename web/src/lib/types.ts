export type Region = "north" | "south" | "east" | "west" | "central";

export type SummaryKey = "tough" | "clear" | "mixed" | "hazy" | "unknown";

export type RegionOutlook = {
  outdoor: [string, string][];
  indoor: [string, string][];
  hourly: { time: string; iso: string; pm25: number }[];
  summary: SummaryKey;
  peak: { pm25: number; time: string } | null;
  avg: number | null;
};

export type OutlookPayload = {
  generated_at: string;
  threshold: number;
  regions: Record<Region, RegionOutlook>;
};

export const REGIONS: { id: Region; label: string }[] = [
  { id: "north", label: "North" },
  { id: "south", label: "South" },
  { id: "east", label: "East" },
  { id: "west", label: "West" },
  { id: "central", label: "Central" },
];

export const SUMMARY_COPY: Record<
  SummaryKey,
  { emoji: string; title: string; blurb: string }
> = {
  tough: {
    emoji: "🔴",
    title: "Tough air day",
    blurb: "Better to keep outdoor plans indoors.",
  },
  clear: {
    emoji: "🟢",
    title: "Clear enough",
    blurb: "Outdoor windows look good.",
  },
  mixed: {
    emoji: "🟡",
    title: "Mixed day",
    blurb: "Go out in the clearer windows below.",
  },
  hazy: {
    emoji: "🟠",
    title: "Hazy stretch ahead",
    blurb: "Pick outdoor slots carefully.",
  },
  unknown: {
    emoji: "⚠️",
    title: "Limited data",
    blurb: "Not enough forecast data right now.",
  },
};
