import * as React from "react";
import { MODEL_SOURCE_LABELS, type ModelSource } from "./builderStudioLabels";

const MODEL_SOURCES: ModelSource[] = ["ham_default", "connected_tools_byok", "workspace_default"];

const HELPER_COPY: Record<ModelSource, string> = {
  ham_default: "Uses HAM's recommended default for this kind of work.",
  connected_tools_byok: "Use a key you've already connected. We never see the value.",
  workspace_default: "Uses your workspace's default model.",
};

export function ModelSourceSelector({
  value,
  modelRef,
  onChange,
  onModelRefChange,
}: {
  value: ModelSource;
  modelRef: string | null;
  onChange: (next: ModelSource) => void;
  onModelRefChange: (next: string | null) => void;
}) {
  return (
    <fieldset className="space-y-2">
      <legend className="text-xs font-medium text-white/75">Model source</legend>
      <div className="grid gap-2">
        {MODEL_SOURCES.map((source) => {
          const selected = value === source;
          return (
            <label
              key={source}
              className={
                "flex cursor-pointer flex-col gap-1 rounded-xl border px-3 py-2 " +
                (selected
                  ? "border-emerald-300/40 bg-emerald-950/35"
                  : "border-white/15 bg-[#141c26] hover:border-white/25")
              }
            >
              <div className="flex items-center gap-2">
                <input
                  type="radio"
                  name="model_source"
                  value={source}
                  checked={selected}
                  onChange={() => {
                    onChange(source);
                    if (source !== "connected_tools_byok") {
                      onModelRefChange(null);
                    }
                  }}
                  className="h-3.5 w-3.5 accent-[var(--theme-accent)]"
                />
                <span className="text-sm font-medium text-white/95">
                  {MODEL_SOURCE_LABELS[source]}
                </span>
              </div>
              <span className="text-[11px] leading-snug text-white/65">{HELPER_COPY[source]}</span>
            </label>
          );
        })}
      </div>

      {value === "connected_tools_byok" ? (
        <label className="mt-2 block text-xs font-medium text-white/80">
          Connected key reference
          <input
            type="text"
            value={modelRef ?? ""}
            onChange={(e) => onModelRefChange(e.target.value)}
            placeholder="byok:your-record-id"
            spellCheck={false}
            autoComplete="off"
            className="mt-1 w-full rounded-md border border-white/15 bg-[#111920] px-3 py-2 text-sm text-white placeholder:text-white/35 shadow-inner shadow-black/30"
          />
          <span className="mt-1 block text-[10px] text-white/55">
            Paste the record id only. Never paste a raw key here.
          </span>
        </label>
      ) : null}
    </fieldset>
  );
}
