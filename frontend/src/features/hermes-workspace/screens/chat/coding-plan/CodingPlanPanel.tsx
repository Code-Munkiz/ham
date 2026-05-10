import * as React from "react";

import { type CodingConductorPreviewPayload, previewCodingConductor } from "@/lib/ham/api";
import { Button } from "@/components/ui/button";

import { CodingPlanCard } from "./CodingPlanCard";

export type CodingPlanPanelProps = {
  /** Optional starting prompt copied from the chat composer. */
  initialPrompt?: string;
  /** Optional active project id for project-aware blockers. */
  projectId?: string | null;
  /** Optional handler for "Send back to composer" — Phase 2B leaves it absent. */
  onClose?: () => void;
};

type AsyncState =
  | { status: "idle" }
  | { status: "loading" }
  | { status: "ready"; payload: CodingConductorPreviewPayload }
  | { status: "error"; message: string };

export function CodingPlanPanel({ initialPrompt = "", projectId, onClose }: CodingPlanPanelProps) {
  const [prompt, setPrompt] = React.useState(initialPrompt);
  const [state, setState] = React.useState<AsyncState>({ status: "idle" });

  const submit = React.useCallback(async () => {
    const trimmed = prompt.trim();
    if (!trimmed) {
      setState({ status: "error", message: "Describe the task to plan." });
      return;
    }
    setState({ status: "loading" });
    try {
      const payload = await previewCodingConductor({
        user_prompt: trimmed,
        project_id: projectId ?? null,
      });
      setState({ status: "ready", payload });
    } catch (err) {
      const message = err instanceof Error ? err.message : "Could not reach HAM.";
      setState({ status: "error", message });
    }
  }, [prompt, projectId]);

  return (
    <section
      className="rounded-lg border border-white/[0.1] bg-[#040608]/85 p-3"
      aria-label="HAM coding plan"
      data-hww-coding-plan-panel
    >
      <header className="flex items-center justify-between gap-2">
        <div>
          <p className="text-[10px] font-medium uppercase tracking-[0.14em] text-white/55">
            Plan with coding agents
          </p>
          <p className="mt-0.5 text-[11px] leading-snug text-white/55">
            HAM picks a provider and explains why. No agent will run from this panel.
          </p>
        </div>
        {onClose ? (
          <Button
            type="button"
            variant="ghost"
            size="sm"
            onClick={onClose}
            className="h-7 text-[11px] text-white/55 hover:bg-white/[0.06]"
          >
            Close
          </Button>
        ) : null}
      </header>

      <label className="mt-3 block">
        <span className="sr-only">Task prompt</span>
        <textarea
          value={prompt}
          onChange={(e) => setPrompt(e.target.value)}
          rows={3}
          className="w-full resize-y rounded-md border border-white/[0.1] bg-[#070b0f] px-2.5 py-2 text-[12px] leading-snug text-white/90 placeholder:text-white/35 focus:border-cyan-300/40 focus:outline-none"
          placeholder="Describe the task — e.g. 'Refactor the chat router for clarity.'"
          data-hww-coding-plan-input
          aria-label="Task prompt"
        />
      </label>
      <div className="mt-2 flex items-center gap-2">
        <Button
          type="button"
          size="sm"
          onClick={() => void submit()}
          disabled={state.status === "loading" || !prompt.trim()}
          data-hww-coding-plan-submit
          className="h-7 text-[11px]"
        >
          {state.status === "loading" ? "Planning…" : "Plan with coding agents"}
        </Button>
        {state.status === "error" ? (
          <span className="text-[11px] text-amber-200/85" role="alert" data-hww-coding-plan-error>
            {state.message}
          </span>
        ) : null}
      </div>

      {state.status === "ready" ? (
        <div className="mt-3">
          <CodingPlanCard payload={state.payload} />
        </div>
      ) : null}
    </section>
  );
}
