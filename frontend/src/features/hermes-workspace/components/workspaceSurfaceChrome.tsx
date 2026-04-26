import * as React from "react";
import { cn } from "@/lib/utils";

export function WorkspaceSurfaceHeader({
  eyebrow,
  title,
  subtitle,
  actions,
  className,
  variant = "default",
}: {
  eyebrow?: string;
  title: string;
  subtitle?: string;
  actions?: React.ReactNode;
  className?: string;
  /** `dark` — light text on dark panel (Jobs/Tasks style). */
  variant?: "default" | "dark";
}) {
  const v =
    variant === "dark"
      ? "border-white/10 bg-black/25 shadow-[0_12px_40px_rgba(0,0,0,0.35)] [&_h1]:text-white/95 [&_p]:text-white/55"
      : "border-[var(--theme-border)] bg-[var(--theme-card)] shadow-[0_16px_48px_var(--theme-shadow)] [&_h1]:text-[var(--theme-text)] [&_p]:text-[var(--theme-muted)]";
  return (
    <header
      className={cn(
        "flex flex-col gap-3 rounded-2xl border px-4 py-4 sm:flex-row sm:items-start sm:justify-between",
        v,
        className,
      )}
    >
      <div className="min-w-0">
        {eyebrow ? (
          <p className={cn("text-[10px] font-semibold uppercase tracking-[0.2em]", variant === "dark" ? "text-white/45" : "")}>
            {eyebrow}
          </p>
        ) : null}
        <h1 className="text-lg font-semibold tracking-tight">{title}</h1>
        {subtitle ? <p className="mt-1 max-w-2xl text-sm leading-relaxed">{subtitle}</p> : null}
      </div>
      {actions ? <div className="flex shrink-0 flex-wrap items-center gap-2">{actions}</div> : null}
    </header>
  );
}

export function WorkspaceSurfaceStateCard({
  title,
  description,
  tone = "neutral",
  technicalDetail,
  primaryAction,
  secondaryAction,
  className,
}: {
  title: string;
  description?: string;
  tone?: "neutral" | "amber" | "danger";
  technicalDetail?: string;
  primaryAction?: React.ReactNode;
  secondaryAction?: React.ReactNode;
  className?: string;
}) {
  const toneClass =
    tone === "danger"
      ? "border-red-500/35 bg-red-950/20 text-red-100"
      : tone === "amber"
        ? "border-amber-500/35 bg-amber-500/10 text-amber-100/90"
        : "border-[var(--theme-border)] bg-[var(--theme-bg)] text-[var(--theme-text)]";

  return (
    <section
      className={cn(
        "rounded-2xl border px-4 py-5 text-sm shadow-[0_12px_40px_var(--theme-shadow)]",
        toneClass,
        className,
      )}
    >
      <h2 className="text-base font-semibold leading-snug">{title}</h2>
      {description ? <p className="mt-2 max-w-prose leading-relaxed opacity-95">{description}</p> : null}
      {technicalDetail ? (
        <pre className="mt-3 max-h-40 overflow-auto whitespace-pre-wrap break-words rounded-lg border border-white/10 bg-black/20 p-3 text-[11px] leading-relaxed opacity-90">
          {technicalDetail}
        </pre>
      ) : null}
      {(primaryAction || secondaryAction) && (
        <div className="mt-4 flex flex-wrap items-center gap-2">
          {primaryAction}
          {secondaryAction}
        </div>
      )}
    </section>
  );
}
