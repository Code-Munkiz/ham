import * as React from "react";

export type CapabilityBadgeTone = "neutral" | "amber" | "ok";

export function WorkspaceSettingsCapabilityBadge({
  children,
  tone = "neutral",
}: {
  children: React.ReactNode;
  tone?: CapabilityBadgeTone;
}) {
  const cls =
    tone === "amber"
      ? "border-amber-500/25 bg-amber-500/10 text-amber-200/90"
      : tone === "ok"
        ? "border-emerald-500/20 bg-emerald-500/10 text-emerald-200/85"
        : "border-white/[0.12] bg-white/[0.04] text-white/55";
  return (
    <span
      className={`inline-flex items-center rounded-md border px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide ${cls}`}
    >
      {children}
    </span>
  );
}

export function WorkspaceSettingsSectionHeader({
  title,
  subtitle,
  badge,
}: {
  title: string;
  subtitle: string;
  badge?: React.ReactNode;
}) {
  return (
    <div className="space-y-2">
      <div className="flex flex-wrap items-center gap-2">
        <h2 className="text-base font-semibold text-[#e8eef8]">{title}</h2>
        {badge}
      </div>
      <p className="text-[13px] leading-relaxed text-white/45">{subtitle}</p>
    </div>
  );
}

export function WorkspaceSettingsFieldRow({
  label,
  value,
  hint,
}: {
  label: string;
  value: React.ReactNode;
  hint?: string;
}) {
  return (
    <div className="flex flex-col gap-1 border-b border-white/[0.06] py-3 last:border-b-0">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <span className="text-[13px] text-white/65">{label}</span>
        <span className="max-w-[min(100%,28rem)] text-right font-mono text-[12px] text-white/80">
          {value}
        </span>
      </div>
      {hint ? <p className="text-[11px] leading-snug text-white/35">{hint}</p> : null}
    </div>
  );
}

export function WorkspaceSettingsReadOnlyCard({
  children,
  className = "",
}: {
  children: React.ReactNode;
  className?: string;
}) {
  return (
    <div
      className={`hww-set-card rounded-2xl border border-white/[0.08] bg-white/[0.02] p-5 shadow-none md:p-6 ${className}`}
    >
      {children}
    </div>
  );
}

export function WorkspaceSettingsUnavailableNote({ children }: { children: React.ReactNode }) {
  return (
    <div className="mt-4 rounded-xl border border-amber-500/20 bg-amber-500/[0.06] px-3 py-2.5 text-[12px] leading-relaxed text-amber-100/80">
      {children}
    </div>
  );
}
