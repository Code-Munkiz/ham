/**
 * Inline detail panel for a fixed builder connection lane (Claude, Cursor, Factory Droid, OpenCode).
 * Not for API key entry — navigation only to existing settings routes.
 */
import * as React from "react";
import { Link } from "react-router-dom";
import type { LucideIcon } from "lucide-react";
import { X } from "lucide-react";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import { CODING_AGENT_LABELS } from "../coding-agents/codingAgentLabels";

export type BuilderConnectionLane = "claude" | "cursor" | "factory" | "opencode";

export type BuilderConnectionStatusTone = "ready" | "attention" | "blocked" | "neutral";

type ConnectionStatusBadgeProps = { label: string; tone: BuilderConnectionStatusTone };

function ConnectionStatusBadge({ label, tone }: ConnectionStatusBadgeProps) {
  return (
    <span
      className={cn(
        "inline-flex w-fit items-center rounded-full border px-2.5 py-0.5 text-[11px] font-semibold leading-snug",
        tone === "ready" && "border-emerald-500/30 bg-emerald-500/10 text-emerald-200",
        tone === "attention" && "border-amber-500/30 bg-amber-500/10 text-amber-200",
        tone === "blocked" && "border-slate-500/35 bg-slate-500/10 text-slate-200",
        tone === "neutral" && "border-white/15 bg-white/[0.04] text-white/55",
      )}
    >
      {label}
    </span>
  );
}

export type BuilderConnectionPanelModel = {
  lane: BuilderConnectionLane;
  icon: LucideIcon;
  title: string;
  description: string;
  goodForItems: string[];
  requires: string;
  statusLabel: string;
  statusTone: BuilderConnectionStatusTone;
  primary: { label: string; to: string };
  secondaries: Array<{ label: string; to: string }>;
};

export function BuilderConnectionDetailPanel({
  model,
  onClose,
}: {
  model: BuilderConnectionPanelModel;
  onClose: () => void;
}) {
  const panelRef = React.useRef<HTMLDivElement | null>(null);
  const titleId = React.useId();

  React.useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [onClose]);

  React.useEffect(() => {
    panelRef.current?.focus();
  }, []);

  const Icon = model.icon;

  return (
    <div
      className="fixed inset-0 z-50 flex items-end justify-center bg-black/70 p-4 sm:items-center"
      role="presentation"
      onMouseDown={(e) => {
        if (e.target === e.currentTarget) onClose();
      }}
    >
      <div
        ref={panelRef}
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        tabIndex={-1}
        className="flex max-h-[min(90vh,720px)] w-full max-w-lg flex-col overflow-hidden rounded-2xl border border-white/12 bg-zinc-950 shadow-2xl outline-none"
      >
        <div className="flex items-start justify-between gap-3 border-b border-white/10 px-5 py-4">
          <div className="flex min-w-0 gap-3">
            <Icon className="mt-0.5 h-5 w-5 shrink-0 text-[var(--theme-accent)]" aria-hidden />
            <div className="min-w-0">
              <h2 id={titleId} className="text-base font-semibold text-white">
                {model.title}
              </h2>
              <p className="mt-1 text-sm leading-relaxed text-white/70">{model.description}</p>
            </div>
          </div>
          <Button
            type="button"
            size="sm"
            variant="ghost"
            className="h-9 shrink-0 text-white hover:bg-white/10 hover:text-white"
            onClick={onClose}
            aria-label={CODING_AGENT_LABELS.builderPanelCloseAria}
          >
            <X className="h-4 w-4" aria-hidden />
          </Button>
        </div>

        <div className="min-h-0 flex-1 space-y-4 overflow-y-auto px-5 py-4 text-sm text-white/85">
          <div>
            <h3 className="text-xs font-semibold uppercase tracking-wide text-white/50">
              {CODING_AGENT_LABELS.builderPanelGoodForHeading}
            </h3>
            <ul className="mt-2 list-disc space-y-1 pl-5 text-white/80">
              {model.goodForItems.map((item) => (
                <li key={item}>{item}</li>
              ))}
            </ul>
          </div>

          <div>
            <h3 className="text-xs font-semibold uppercase tracking-wide text-white/50">
              {CODING_AGENT_LABELS.builderPanelRequiresHeading}
            </h3>
            <p className="mt-2 leading-relaxed text-white/75">{model.requires}</p>
          </div>

          <div>
            <h3 className="text-xs font-semibold uppercase tracking-wide text-white/50">
              {CODING_AGENT_LABELS.builderPanelStatusHeading}
            </h3>
            <div className="mt-2">
              <ConnectionStatusBadge label={model.statusLabel} tone={model.statusTone} />
            </div>
          </div>

          <div>
            <h3 className="text-xs font-semibold uppercase tracking-wide text-white/50">
              {CODING_AGENT_LABELS.builderPanelNextStepHeading}
            </h3>
            <p className="mt-2 leading-relaxed text-white/70">
              {CODING_AGENT_LABELS.builderPanelNextStepCaption}
            </p>
            <div className="mt-3 flex flex-col gap-2">
              <Button asChild className="w-full sm:w-auto">
                <Link to={model.primary.to} onClick={onClose}>
                  {model.primary.label}
                </Link>
              </Button>
              {model.secondaries.map((sec) => (
                <Button
                  key={sec.label}
                  asChild
                  variant="outline"
                  className="w-full border-white/20 bg-transparent text-white hover:bg-white/10 hover:text-white sm:w-auto"
                >
                  <Link to={sec.to} onClick={onClose}>
                    {sec.label}
                  </Link>
                </Button>
              ))}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
