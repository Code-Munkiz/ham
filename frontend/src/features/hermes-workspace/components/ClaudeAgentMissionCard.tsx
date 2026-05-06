import * as React from "react";
import { Bot, CheckCircle2, XCircle, Loader2, ChevronDown, ChevronUp, Shield } from "lucide-react";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import { postClaudeAgentMission } from "@/lib/ham/api";

export interface ClaudeAgentMissionResult {
  ok: boolean;
  mission_ok: boolean;
  worker: string;
  mission_type: string;
  result_text: string;
  parsed_result: {
    mission_status?: string;
    worker?: string;
    job_type?: string;
    summary?: string;
    acceptance_criteria?: string[];
  } | null;
  duration_ms: number;
  safety_mode: string;
  blocker: string | null;
}

type MissionState =
  | { phase: "idle" }
  | { phase: "loading" }
  | { phase: "success"; result: ClaudeAgentMissionResult; completedAt: string }
  | { phase: "error"; message: string; errorCode?: string; resultTextPresent?: boolean };

function blockerToUserMessage(blocker: string | null, errorCode?: string): string {
  if (errorCode === "CONNECT_CLAUDE_AGENT_REQUIRED")
    return "Connect Claude Agent first in Settings → Connected Tools.";
  if (
    errorCode === "CLERK_SESSION_REQUIRED" ||
    errorCode === "CLERK_AUTH_NOT_CONFIGURED_FOR_MISSION"
  )
    return "Sign in to run Claude Agent missions.";
  if (!blocker) return "Claude Agent mission failed.";
  if (blocker.toLowerCase().includes("credential") || blocker.toLowerCase().includes("api key"))
    return "Credential invalid or missing. Reconnect Claude Agent.";
  if (blocker.toLowerCase().includes("parser") || blocker.toLowerCase().includes("json"))
    return "Parser rejected output — model did not return valid mission JSON.";
  if (blocker.toLowerCase().includes("timeout")) return "Claude runtime timed out.";
  return "Claude runtime failed. Check Connected Tools status.";
}

export function ClaudeAgentMissionCard() {
  const [state, setState] = React.useState<MissionState>({ phase: "idle" });
  const [expanded, setExpanded] = React.useState(false);

  const runMission = async () => {
    setState({ phase: "loading" });
    try {
      const res = await postClaudeAgentMission();
      if (!res.ok) {
        const body = await res.json().catch(() => null);
        const detail = body?.detail;
        const code = detail?.code || detail?.error?.code;
        const msg = detail?.message || detail?.error?.message || `HTTP ${res.status}`;
        setState({ phase: "error", message: msg, errorCode: code, resultTextPresent: false });
        return;
      }
      const data: ClaudeAgentMissionResult = await res.json();
      if (data.mission_ok) {
        setState({ phase: "success", result: data, completedAt: new Date().toISOString() });
      } else {
        setState({
          phase: "error",
          message: blockerToUserMessage(data.blocker),
          errorCode: undefined,
          resultTextPresent: !!data.result_text,
        });
      }
    } catch (err) {
      setState({
        phase: "error",
        message: "Network error — check your connection.",
        resultTextPresent: false,
      });
    }
  };

  return (
    <section
      className="rounded-2xl border border-[var(--theme-border)] bg-[var(--theme-card)] p-4 shadow-[0_20px_60px_var(--theme-shadow)]"
      data-testid="claude-agent-mission-card"
    >
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <Bot className="h-4 w-4 text-[var(--theme-accent)]" />
          <h3 className="text-sm font-semibold text-[var(--theme-text)]">
            Claude Agent validation mission
          </h3>
        </div>
        <Button
          type="button"
          size="sm"
          variant="secondary"
          className="h-7 gap-1 border border-[var(--theme-border)] bg-[var(--theme-bg)] px-2 text-[11px] text-[var(--theme-text)] hover:bg-[var(--theme-card2)]"
          onClick={() => void runMission()}
          disabled={state.phase === "loading"}
          data-testid="run-claude-mission-btn"
        >
          {state.phase === "loading" ? (
            <Loader2 className="h-3 w-3 animate-spin" />
          ) : (
            <Bot className="h-3 w-3" />
          )}
          {state.phase === "loading" ? "Running…" : "Run Claude Agent mission"}
        </Button>
      </div>

      {state.phase === "loading" && (
        <div
          className="mt-3 flex items-center gap-2 rounded-xl border border-[var(--theme-border)] bg-[var(--theme-bg)] px-3 py-3 text-sm text-[var(--theme-muted)]"
          data-testid="mission-loading"
        >
          <Loader2 className="h-4 w-4 animate-spin text-[var(--theme-accent)]" />
          Running bounded plan-mode mission…
        </div>
      )}

      {state.phase === "error" && (
        <div
          className="mt-3 rounded-xl border border-red-500/30 bg-red-500/5 px-3 py-3"
          data-testid="mission-error"
        >
          <div className="flex items-start gap-2">
            <XCircle className="mt-0.5 h-4 w-4 shrink-0 text-red-400" />
            <div className="min-w-0">
              <p className="text-sm font-medium text-red-300">
                {blockerToUserMessage(state.message, state.errorCode)}
              </p>
              {state.resultTextPresent && (
                <p className="mt-1 text-xs text-[var(--theme-muted)]">
                  Result text was present but did not pass acceptance.
                </p>
              )}
            </div>
          </div>
        </div>
      )}

      {state.phase === "success" && (
        <div className="mt-3 space-y-2" data-testid="mission-success">
          <div className="rounded-xl border border-emerald-500/30 bg-emerald-500/5 px-3 py-3">
            <div className="flex items-start gap-2">
              <CheckCircle2 className="mt-0.5 h-4 w-4 shrink-0 text-emerald-400" />
              <div className="min-w-0 flex-1">
                <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-xs">
                  <span className="font-medium text-emerald-300" data-testid="mission-ok-badge">
                    mission_ok: true
                  </span>
                  <span className="text-[var(--theme-muted)]" data-testid="mission-worker">
                    worker: {state.result.worker}
                  </span>
                  <span className="text-[var(--theme-muted)]">
                    safety_mode: {state.result.safety_mode}
                  </span>
                  <span className="text-[var(--theme-muted)]">{state.result.duration_ms}ms</span>
                </div>

                {state.result.parsed_result && (
                  <div className="mt-2 space-y-1.5">
                    <div className="flex flex-wrap gap-x-3 gap-y-0.5 text-xs text-[var(--theme-muted)]">
                      <span>
                        status:{" "}
                        <span className="text-[var(--theme-text)]">
                          {state.result.parsed_result.mission_status}
                        </span>
                      </span>
                      <span>
                        worker:{" "}
                        <span className="text-[var(--theme-text)]">
                          {state.result.parsed_result.worker}
                        </span>
                      </span>
                    </div>
                    {state.result.parsed_result.acceptance_criteria && (
                      <div data-testid="acceptance-criteria">
                        <p className="text-[10px] font-semibold uppercase tracking-wider text-[var(--theme-muted)]">
                          Acceptance criteria (
                          {state.result.parsed_result.acceptance_criteria.length})
                        </p>
                        <ul className="mt-0.5 space-y-0.5">
                          {state.result.parsed_result.acceptance_criteria.map((c, i) => (
                            <li
                              key={i}
                              className="flex items-start gap-1.5 text-xs text-[var(--theme-text)]"
                            >
                              <CheckCircle2 className="mt-0.5 h-3 w-3 shrink-0 text-emerald-400" />
                              {c}
                            </li>
                          ))}
                        </ul>
                      </div>
                    )}
                  </div>
                )}

                <button
                  type="button"
                  className="mt-2 flex items-center gap-1 text-[10px] text-[var(--theme-muted)] hover:text-[var(--theme-text)]"
                  onClick={() => setExpanded((v) => !v)}
                >
                  {expanded ? (
                    <ChevronUp className="h-3 w-3" />
                  ) : (
                    <ChevronDown className="h-3 w-3" />
                  )}
                  {expanded ? "Hide result text" : "Show result text"}
                </button>
                {expanded && (
                  <pre
                    className="mt-1 max-h-40 overflow-auto whitespace-pre-wrap rounded-lg border border-[var(--theme-border)] bg-[var(--theme-bg)] p-2 text-[10px] text-[var(--theme-text)]"
                    data-testid="mission-result-text"
                  >
                    {state.result.result_text}
                  </pre>
                )}

                <div className="mt-2 flex items-center gap-1.5 text-[10px] text-[var(--theme-muted)]">
                  <Shield className="h-3 w-3" />
                  Returned through HAM API · {new Date(state.completedAt).toLocaleTimeString()}
                </div>
              </div>
            </div>
          </div>
        </div>
      )}
    </section>
  );
}
