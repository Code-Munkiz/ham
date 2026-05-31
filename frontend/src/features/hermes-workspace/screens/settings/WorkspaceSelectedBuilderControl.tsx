/**
 * Selected builder control (workspace Settings → Builders).
 *
 * Lets the user choose which builder HAM uses for normal builds. Persists via
 * the existing coding-agent access settings (GET/PATCH). This is a preference
 * surface only — it never launches a build, never opens an approval panel, and
 * never exposes provider ids, env vars, registry/recipe/workflow internals, or
 * secrets. Product law: HAM uses the builder selected by the user; the internal
 * scaffold is Quick Preview only.
 */
import * as React from "react";

import {
  fetchCodingAgentAccessSettings,
  fetchCodingReadinessSnapshot,
  normalizeSelectedBuilder,
  patchCodingAgentAccessSettings,
  SELECTABLE_BUILDERS,
  type CodingAgentReadiness,
  type SelectedBuilder,
} from "../../adapters/codingAgentsAdapter";
import { cn } from "@/lib/utils";

const HEADING = "Builder";
const SUBTITLE = "Choose which builder HAM uses for normal builds.";
const NO_SELECTION_HELP =
  "No builder is selected yet — HAM will ask you to choose when you start a build.";
const SAVE_ERROR = "Couldn't save your builder choice. Try again.";
const READY_LABEL = "Ready";
const NEEDS_SETUP_LABEL = "Needs setup";

const BUILDER_LABEL: Record<SelectedBuilder, string> = {
  opencode: "OpenCode",
  factory_droid: "Factory Droid",
  cursor: "Cursor",
  claude: "Claude",
  hermes_agent: "Hermes Agent",
};

const BUILDER_HELP: Record<SelectedBuilder, string> = {
  opencode: "OpenCode opens a managed build you review and approve in the workbench.",
  factory_droid: "Factory Droid opens a managed build you review and approve in the workbench.",
  cursor: "Cursor runs through its own build flow for now.",
  claude: "Claude runs through its own build flow for now.",
  hermes_agent: "Hermes Agent new-build support is coming soon.",
};

type ReadinessState = Partial<Record<SelectedBuilder, CodingAgentReadiness>>;

export function WorkspaceSelectedBuilderControl({ workspaceId }: { workspaceId: string }) {
  const [selected, setSelected] = React.useState<SelectedBuilder | null>(null);
  const [loading, setLoading] = React.useState(true);
  const [saving, setSaving] = React.useState<SelectedBuilder | null>(null);
  const [error, setError] = React.useState<string | null>(null);
  const [readiness, setReadiness] = React.useState<ReadinessState>({});

  React.useEffect(() => {
    let active = true;
    void (async () => {
      setLoading(true);
      const [settingsRes, snap] = await Promise.all([
        fetchCodingAgentAccessSettings(workspaceId),
        fetchCodingReadinessSnapshot(),
      ]);
      if (!active) return;
      if (settingsRes.ok) {
        setSelected(normalizeSelectedBuilder(settingsRes.settings.selected_builder));
      }
      // Only the signals we already have cleanly; others show no badge.
      setReadiness({ opencode: snap.opencode, claude: snap.claudeAgent });
      setLoading(false);
    })();
    return () => {
      active = false;
    };
  }, [workspaceId]);

  const onSelect = React.useCallback(
    async (builder: SelectedBuilder) => {
      if (builder === selected || saving) return;
      const previous = selected;
      setError(null);
      setSaving(builder);
      setSelected(builder);
      const res = await patchCodingAgentAccessSettings(workspaceId, { selected_builder: builder });
      if (res.ok) {
        setSelected(normalizeSelectedBuilder(res.settings.selected_builder));
      } else {
        setSelected(previous);
        setError(SAVE_ERROR);
      }
      setSaving(null);
    },
    [selected, saving, workspaceId],
  );

  const helper = selected ? BUILDER_HELP[selected] : NO_SELECTION_HELP;

  return (
    <section
      data-testid="hww-selected-builder-control"
      className="space-y-3 rounded-2xl border border-[var(--theme-border)] bg-[var(--theme-card)]/90 p-4 shadow-[0_12px_40px_var(--theme-shadow)]"
    >
      <div>
        <h2 className="text-sm font-semibold text-[var(--theme-text)]">{HEADING}</h2>
        <p className="mt-0.5 text-[11px] leading-relaxed text-[var(--theme-muted)]">{SUBTITLE}</p>
      </div>

      <div role="radiogroup" aria-label={HEADING} className="space-y-2">
        {SELECTABLE_BUILDERS.map((builder) => {
          const isSelected = selected === builder;
          const ready = readiness[builder];
          return (
            <button
              key={builder}
              type="button"
              role="radio"
              aria-checked={isSelected}
              aria-label={BUILDER_LABEL[builder]}
              disabled={loading || saving !== null}
              onClick={() => void onSelect(builder)}
              className={cn(
                "flex w-full items-center justify-between gap-3 rounded-xl border px-3 py-2.5 text-left transition-colors",
                "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--theme-accent)]",
                isSelected
                  ? "border-[var(--theme-accent)] bg-[var(--theme-accent)]/10"
                  : "border-[var(--theme-border)] bg-[var(--theme-card)] hover:border-white/20",
                (loading || saving !== null) && "opacity-70",
              )}
            >
              <span className="flex items-center gap-2 text-sm font-medium text-[var(--theme-text)]">
                <span
                  aria-hidden
                  className={cn(
                    "inline-block h-3.5 w-3.5 shrink-0 rounded-full border",
                    isSelected
                      ? "border-[var(--theme-accent)] bg-[var(--theme-accent)]"
                      : "border-white/30",
                  )}
                />
                {BUILDER_LABEL[builder]}
              </span>
              {ready ? (
                <span
                  className={cn(
                    "inline-flex w-fit items-center rounded-full border px-2 py-0.5 text-[10px] font-semibold leading-snug",
                    ready === "ready"
                      ? "border-emerald-500/30 bg-emerald-500/10 text-emerald-200"
                      : "border-amber-500/30 bg-amber-500/10 text-amber-200",
                  )}
                >
                  {ready === "ready" ? READY_LABEL : NEEDS_SETUP_LABEL}
                </span>
              ) : null}
            </button>
          );
        })}
      </div>

      <p
        data-testid="hww-selected-builder-helper"
        className="text-[11px] leading-relaxed text-[var(--theme-muted)]"
        aria-live="polite"
      >
        {helper}
      </p>

      {error ? (
        <p role="alert" className="text-[11px] font-medium text-amber-300">
          {error}
        </p>
      ) : null}
    </section>
  );
}

export default WorkspaceSelectedBuilderControl;
