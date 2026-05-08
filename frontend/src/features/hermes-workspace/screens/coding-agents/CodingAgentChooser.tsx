import * as React from "react";
import { Bot, ScanLine } from "lucide-react";
import { Button } from "@/components/ui/button";
import { CODING_AGENT_LABELS } from "./codingAgentLabels";

export type CodingAgentLane = "cursor" | "droid";

export function CodingAgentChooser({
  cursorReady,
  droidReady,
  onPick,
  onCancel,
}: {
  cursorReady: boolean;
  droidReady: boolean;
  onPick: (lane: CodingAgentLane) => void;
  onCancel: () => void;
}) {
  return (
    <section className="space-y-3 rounded-2xl border border-[var(--theme-border)] bg-[var(--theme-card)] p-4 shadow-[0_16px_48px_var(--theme-shadow)]">
      <div>
        <h2 className="text-sm font-semibold text-[var(--theme-text)]">
          {CODING_AGENT_LABELS.chooserTitle}
        </h2>
        <p className="mt-1 text-xs text-[var(--theme-muted)]">
          {CODING_AGENT_LABELS.chooserSubtitle}
        </p>
      </div>
      <div className="grid gap-3 sm:grid-cols-2">
        <LaneCard
          icon={<Bot className="h-5 w-5 text-[var(--theme-accent)]" />}
          title={CODING_AGENT_LABELS.chooserCursorTitle}
          body={CODING_AGENT_LABELS.chooserCursorBody}
          ctaLabel={CODING_AGENT_LABELS.newTaskCta}
          disabled={!cursorReady}
          onClick={() => onPick("cursor")}
        />
        <LaneCard
          icon={<ScanLine className="h-5 w-5 text-[var(--theme-accent)]" />}
          title={CODING_AGENT_LABELS.chooserDroidTitle}
          body={CODING_AGENT_LABELS.chooserDroidBody}
          ctaLabel={CODING_AGENT_LABELS.auditCta}
          disabled={!droidReady}
          onClick={() => onPick("droid")}
        />
      </div>
      <div className="flex justify-end">
        <Button type="button" size="sm" variant="ghost" onClick={onCancel}>
          {CODING_AGENT_LABELS.cancelCta}
        </Button>
      </div>
    </section>
  );
}

function LaneCard({
  icon,
  title,
  body,
  ctaLabel,
  disabled,
  onClick,
}: {
  icon: React.ReactNode;
  title: string;
  body: string;
  ctaLabel: string;
  disabled: boolean;
  onClick: () => void;
}) {
  return (
    <div className="flex flex-col gap-2 rounded-xl border border-[var(--theme-border)] bg-[var(--theme-bg)] p-3">
      <div className="flex items-center gap-2">
        {icon}
        <span className="text-sm font-semibold text-[var(--theme-text)]">{title}</span>
      </div>
      <p className="text-xs leading-relaxed text-[var(--theme-muted)]">{body}</p>
      <div className="mt-auto pt-1">
        <Button type="button" size="sm" onClick={onClick} disabled={disabled}>
          {ctaLabel}
        </Button>
      </div>
    </div>
  );
}
