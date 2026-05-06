import type { ActivityEvent, ActivityEventSource } from "@/lib/ham/types";

const LABELS: Record<ActivityEventSource, string> = {
  cursor: "CURSOR",
  cloud_agent: "CLOUD_AGENT",
  factory_ai: "FACTORY_AI",
  droid: "DROID",
  ham: "HAM",
  unknown: "UNKNOWN",
};

const CANON: Record<string, ActivityEventSource> = {
  cursor: "cursor",
  cloud_agent: "cloud_agent",
  "cloud agent": "cloud_agent",
  cloudagent: "cloud_agent",
  factory_ai: "factory_ai",
  "factory ai": "factory_ai",
  factory: "factory_ai",
  droid: "droid",
  droids: "droid",
  ham: "ham",
  unknown: "unknown",
};

function normalizeMetaSource(raw: string): ActivityEventSource | null {
  const k = raw
    .trim()
    .toLowerCase()
    .replace(/[\s-]+/g, "_");
  if (k in CANON) return CANON[k]!;
  if (k in LABELS) return k as ActivityEventSource;
  return null;
}

export function resolvedActivitySource(event: ActivityEvent): ActivityEventSource {
  if (event.source && event.source in LABELS) {
    return event.source;
  }
  const meta = event.metadata?.source;
  if (typeof meta === "string" && meta.trim()) {
    const c = normalizeMetaSource(meta);
    if (c) return c;
  }
  return "unknown";
}

/**
 * Display label for activity rows. Uses `event.source`, then `metadata.source` (string), else `UNKNOWN`.
 */
export function activitySourceLabel(event: ActivityEvent): string {
  return LABELS[resolvedActivitySource(event)];
}

const BADGE: Record<ActivityEventSource, string> = {
  cursor: "border-cyan-500/35 bg-cyan-500/10 text-cyan-400/90",
  cloud_agent: "border-[#00E5FF]/40 bg-[#00E5FF]/5 text-[#00E5FF]/85",
  factory_ai: "border-violet-500/40 bg-violet-500/10 text-violet-300/90",
  droid: "border-amber-500/40 bg-amber-500/10 text-amber-300/85",
  ham: "border-[#FF6B00]/45 bg-[#FF6B00]/10 text-[#FF6B00]/90",
  unknown: "border-white/15 bg-white/5 text-white/40",
};

export function activitySourceBadgeClass(event: ActivityEvent): string {
  return BADGE[resolvedActivitySource(event)] ?? BADGE.unknown;
}
