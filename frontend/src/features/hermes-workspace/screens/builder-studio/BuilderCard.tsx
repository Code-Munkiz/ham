import * as React from "react";
import {
  PERMISSION_PRESET_LABELS,
  MODEL_SOURCE_LABELS,
  formatIntentTagsForDisplay,
  type ModelSource,
  type PermissionPreset,
} from "./builderStudioLabels";
import type { BuilderPublic } from "../../adapters/builderStudioAdapter";

export function BuilderCard({
  builder,
  isOperator,
  onOpen,
  onOpenTechnical,
}: {
  builder: BuilderPublic;
  isOperator: boolean;
  onOpen: () => void;
  onOpenTechnical: () => void;
}) {
  const tags = formatIntentTagsForDisplay(builder.intent_tags ?? []);
  const presetLabel =
    PERMISSION_PRESET_LABELS[builder.permission_preset as PermissionPreset] ??
    PERMISSION_PRESET_LABELS.app_build;
  const modelLabel =
    MODEL_SOURCE_LABELS[builder.model_source as ModelSource] ?? MODEL_SOURCE_LABELS.ham_default;
  const statusLabel = builder.enabled ? "Enabled" : "Disabled";

  return (
    <article className="flex min-h-[180px] flex-col rounded-2xl border border-white/10 bg-black/25 p-4 shadow-sm backdrop-blur-sm">
      <div className="mb-2 flex items-start justify-between gap-2">
        <div className="min-w-0 space-y-1">
          <h3 className="truncate text-sm font-semibold text-[var(--theme-text)]">
            {builder.name}
          </h3>
          <p className="line-clamp-2 text-xs text-[var(--theme-muted)]">
            {builder.description || "—"}
          </p>
        </div>
        <span
          className={
            "shrink-0 rounded-full border px-2 py-0.5 text-[10px] font-medium uppercase tracking-wider " +
            (builder.enabled
              ? "border-emerald-500/40 text-emerald-200/80 bg-emerald-500/5"
              : "border-white/15 text-white/45 bg-white/[0.03]")
          }
        >
          {statusLabel}
        </span>
      </div>

      <div className="mt-2 flex flex-wrap gap-1.5">
        {tags.slice(0, 6).map((tag) => (
          <span
            key={tag}
            className="rounded-full border border-white/15 bg-white/[0.04] px-2 py-0.5 text-[10px] text-white/70"
          >
            {tag}
          </span>
        ))}
      </div>

      <div className="mt-3 grid gap-1 text-[11px] text-[var(--theme-muted)]">
        <div>
          Safety: <span className="text-[var(--theme-text)]">{presetLabel}</span>
        </div>
        <div>
          Model: <span className="text-[var(--theme-text)]">{modelLabel}</span>
        </div>
      </div>

      <div className="mt-auto flex items-center justify-between gap-2 border-t border-white/10 pt-3">
        <button
          type="button"
          onClick={onOpen}
          className="text-[11px] font-medium text-emerald-300/90 hover:underline"
        >
          Open details
        </button>
        {isOperator ? (
          <button
            type="button"
            onClick={onOpenTechnical}
            className="text-[10px] text-[var(--theme-muted)] hover:text-[var(--theme-text)]"
          >
            Technical details
          </button>
        ) : null}
      </div>
    </article>
  );
}
