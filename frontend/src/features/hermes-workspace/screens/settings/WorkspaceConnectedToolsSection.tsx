import * as React from "react";
import {
  connectWorkspaceTool,
  disconnectWorkspaceTool,
  fetchWorkspaceTools,
  scanWorkspaceTools,
} from "@/lib/ham/api";

type ToolStatus = "ready" | "needs_sign_in" | "not_found" | "off" | "error" | "unknown";
type ToolSource = "cloud" | "this_computer" | "built_in" | "unknown";
type ConnectKind = "none" | "api_key" | "access_token" | "local_scan" | "coming_soon";

interface ToolEntry {
  id: string;
  label: string;
  category: string;
  status: ToolStatus;
  enabled: boolean;
  source: ToolSource;
  capabilities: string[];
  setup_hint: string | null;
  connect_kind: ConnectKind;
  connected_account_label: string | null;
  credential_preview: string | null;
  last_checked_at: string | null;
  safe_actions: string[];
  version: string | null;
}

interface ToolDiscoveryResponse {
  tools: ToolEntry[];
  scan_available: boolean;
  scan_hint: string | null;
}

const STATUS_LABELS: Record<ToolStatus, string> = {
  ready: "Ready",
  needs_sign_in: "Needs sign-in",
  not_found: "Not found",
  off: "Off",
  error: "Error",
  unknown: "Unknown",
};

const STATUS_GROUP_ORDER: ToolStatus[] = ["ready", "needs_sign_in", "not_found", "off", "error", "unknown"];

function statusDotColor(status: ToolStatus): string {
  switch (status) {
    case "ready":
      return "bg-emerald-400";
    case "needs_sign_in":
      return "bg-amber-400";
    case "not_found":
      return "bg-white/20";
    case "off":
      return "bg-white/20";
    case "error":
      return "bg-red-400";
    default:
      return "bg-white/15";
  }
}

/** Group key for display: Ready-but-disabled rows appear under Off. */
function displayGroupStatus(tool: ToolEntry, effectiveEnabled: boolean): ToolStatus {
  if (tool.status === "ready" && !effectiveEnabled) {
    return "off";
  }
  return tool.status;
}

function canShowToggle(tool: ToolEntry): boolean {
  return tool.status === "ready";
}

function canSelectAllEnable(tool: ToolEntry): boolean {
  return tool.status === "ready";
}

export function WorkspaceConnectedToolsSection() {
  const [data, setData] = React.useState<ToolDiscoveryResponse | null>(null);
  const [loading, setLoading] = React.useState(true);
  const [error, setError] = React.useState<string | null>(null);
  /** Session-only preference overrides (never persisted in the browser). */
  const [toggleOverrides, setToggleOverrides] = React.useState<Record<string, boolean | undefined>>({});
  const [expandedId, setExpandedId] = React.useState<string | null>(null);
  const [connectInputs, setConnectInputs] = React.useState<Record<string, string>>({});
  const [connectBusy, setConnectBusy] = React.useState<string | null>(null);
  const [connectRowError, setConnectRowError] = React.useState<Record<string, string>>({});

  const fetchTools = React.useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const resp = await fetchWorkspaceTools();
      if (!resp.ok) throw new Error(`Failed to load tools (${resp.status})`);
      const json: ToolDiscoveryResponse = await resp.json();
      setData(json);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load tools");
    } finally {
      setLoading(false);
    }
  }, []);

  React.useEffect(() => {
    fetchTools();
  }, [fetchTools]);

  const effectiveEnabled = React.useCallback(
    (t: ToolEntry) => {
      if (Object.prototype.hasOwnProperty.call(toggleOverrides, t.id)) {
        return Boolean(toggleOverrides[t.id]);
      }
      return t.enabled;
    },
    [toggleOverrides],
  );

  const handleToggle = React.useCallback((id: string, enabled: boolean, tool: ToolEntry) => {
    if (!canShowToggle(tool)) return;
    setToggleOverrides((prev) => ({ ...prev, [id]: enabled }));
  }, []);

  const toolsWithEffective: ToolEntry[] = React.useMemo(() => {
    if (!data) return [];
    return data.tools.map((t) => ({
      ...t,
      enabled: effectiveEnabled(t),
    }));
  }, [data, effectiveEnabled]);

  const groupedTools = React.useMemo(() => {
    const groups: Record<string, ToolEntry[]> = {};
    for (const status of STATUS_GROUP_ORDER) {
      const matching = toolsWithEffective.filter(
        (t) => displayGroupStatus(t, effectiveEnabled(t)) === status,
      );
      if (matching.length > 0) {
        groups[status] = matching;
      }
    }
    return groups;
  }, [toolsWithEffective, effectiveEnabled]);

  const postConnect = async (toolId: string, body: Record<string, string>) => {
    setConnectBusy(toolId);
    setConnectRowError((prev) => ({ ...prev, [toolId]: "" }));
    try {
      const resp = await connectWorkspaceTool(toolId, body);
      if (resp.ok) {
        const json: ToolDiscoveryResponse = await resp.json();
        setData(json);
        setConnectInputs((prev) => ({ ...prev, [toolId]: "" }));
        setExpandedId(null);
        return;
      }
      if (resp.status === 501) {
        const detail = await resp.json().catch(() => null);
        const msg =
          detail?.detail?.message ??
          detail?.message ??
          "Secure key storage is coming next.";
        setConnectRowError((prev) => ({ ...prev, [toolId]: String(msg) }));
        return;
      }
      setConnectRowError((prev) => ({
        ...prev,
        [toolId]: "Couldn't connect. Check the key and try again.",
      }));
    } catch {
      setConnectRowError((prev) => ({
        ...prev,
        [toolId]: "Couldn't connect. Check the key and try again.",
      }));
    } finally {
      setConnectBusy(null);
    }
  };

  const postDisconnect = async (toolId: string) => {
    setConnectBusy(toolId);
    setConnectRowError((prev) => ({ ...prev, [toolId]: "" }));
    try {
      const resp = await disconnectWorkspaceTool(toolId);
      if (resp.ok) {
        const json: ToolDiscoveryResponse = await resp.json();
        setData(json);
        return;
      }
      setConnectRowError((prev) => ({
        ...prev,
        [toolId]: "Couldn't disconnect. Try again.",
      }));
    } catch {
      setConnectRowError((prev) => ({
        ...prev,
        [toolId]: "Couldn't disconnect. Try again.",
      }));
    } finally {
      setConnectBusy(null);
    }
  };

  const runScan = async () => {
    setLoading(true);
    setError(null);
    try {
      const resp = await scanWorkspaceTools();
      if (!resp.ok) throw new Error(`Scan failed (${resp.status})`);
      const json: ToolDiscoveryResponse = await resp.json();
      setData(json);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Scan failed");
    } finally {
      setLoading(false);
    }
  };

  if (loading && !data) {
    return (
      <div className="space-y-4">
        <h2 className="text-base font-semibold text-white/90">Connected tools</h2>
        <p className="text-[13px] text-white/40">Loading...</p>
      </div>
    );
  }

  if (error && !data) {
    return (
      <div className="space-y-4">
        <h2 className="text-base font-semibold text-white/90">Connected tools</h2>
        <p className="text-[13px] text-red-400">{error}</p>
        <button
          type="button"
          onClick={fetchTools}
          className="rounded-md border border-white/10 bg-white/[0.04] px-3 py-1.5 text-[12px] font-medium text-white/60 hover:bg-white/[0.08]"
        >
          Try again
        </button>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-base font-semibold text-white/90">Connected tools</h2>
        <p className="mt-1 text-[13px] leading-relaxed text-white/45">
          Tools and services HAM can use to help build, test, and automate your projects. Turn each one On or Off
          to control what HAM will use. Nothing runs automatically from this screen.
        </p>
      </div>

      {data && !data.scan_available && data.scan_hint && (
        <div className="rounded-lg border border-amber-500/20 bg-amber-500/[0.04] px-4 py-3">
          <p className="text-[12px] text-amber-300/80">{data.scan_hint}</p>
        </div>
      )}

      <div className="flex flex-wrap items-center gap-2">
        <button
          type="button"
          onClick={() => {
            void runScan();
          }}
          className="rounded-md border border-white/10 bg-white/[0.04] px-3 py-1.5 text-[12px] font-medium text-white/60 hover:bg-white/[0.08]"
        >
          Scan again
        </button>
        <button
          type="button"
          onClick={() => {
            const next: Record<string, boolean | undefined> = { ...toggleOverrides };
            toolsWithEffective.forEach((t) => {
              if (canSelectAllEnable(t)) {
                next[t.id] = true;
              }
            });
            setToggleOverrides(next);
          }}
          className="rounded-md border border-white/10 bg-white/[0.04] px-3 py-1.5 text-[12px] font-medium text-white/60 hover:bg-white/[0.08]"
        >
          Select all
        </button>
        <button
          type="button"
          onClick={() => {
            const next: Record<string, boolean | undefined> = { ...toggleOverrides };
            toolsWithEffective.forEach((t) => {
              next[t.id] = false;
            });
            setToggleOverrides(next);
          }}
          className="rounded-md border border-white/10 bg-white/[0.04] px-3 py-1.5 text-[12px] font-medium text-white/60 hover:bg-white/[0.08]"
        >
          Select none
        </button>
      </div>

      {error && data && <p className="text-[13px] text-red-400">{error}</p>}

      {Object.entries(groupedTools).map(([status, groupTools]) => (
        <div key={status} className="space-y-2">
          <h3 className="text-[11px] font-semibold uppercase tracking-wider text-white/35">
            {STATUS_LABELS[status as ToolStatus]}
          </h3>
          <div className="space-y-1.5">
            {groupTools.map((tool) => {
              const ee = effectiveEnabled(tool);
              const expanded = expandedId === tool.id;
              const showToggle = canShowToggle(tool);
              const wantsConnect =
                (tool.connect_kind === "api_key" ||
                  tool.connect_kind === "access_token" ||
                  tool.connect_kind === "local_scan" ||
                  tool.connect_kind === "coming_soon") &&
                tool.safe_actions.includes("connect");
              const inputVal = connectInputs[tool.id] ?? "";
              const pasteLabel =
                tool.connect_kind === "access_token" ? "Paste your access token" : "Paste your API key";

              return (
                <div
                  key={tool.id}
                  className="rounded-lg border border-white/[0.06] bg-white/[0.02] px-4 py-3"
                >
                  <div className="flex w-full items-center justify-between gap-3">
                    <button
                      type="button"
                      className="flex min-w-0 flex-1 items-center gap-3 text-left"
                      onClick={() => setExpandedId(expanded ? null : tool.id)}
                    >
                      <span className={`h-2 w-2 shrink-0 rounded-full ${statusDotColor(tool.status)}`} />
                      <div className="min-w-0">
                        <p className="text-[13px] font-medium text-white/90">{tool.label}</p>
                        <p className="text-[11px] text-white/40 truncate">
                          {tool.status === "ready"
                            ? ee
                              ? "Ready · On"
                              : "Ready · Off"
                            : STATUS_LABELS[tool.status]}
                          {tool.credential_preview ? ` · ${tool.credential_preview}` : ""}
                          {tool.version ? ` · ${tool.version}` : ""}
                        </p>
                      </div>
                    </button>
                    <div className="flex shrink-0 items-center gap-3">
                      {tool.status === "needs_sign_in" && wantsConnect && (
                        <span className="rounded-md border border-white/10 bg-white/[0.04] px-2.5 py-1 text-[11px] font-medium text-white/70">
                          Connect
                        </span>
                      )}
                      {showToggle && (
                        <button
                          type="button"
                          role="switch"
                          aria-checked={ee}
                          aria-label={`${ee ? "On" : "Off"} — ${tool.label}`}
                          onClick={(ev) => {
                            ev.stopPropagation();
                            handleToggle(tool.id, !ee, tool);
                          }}
                          className={`relative inline-flex h-5 w-9 shrink-0 cursor-pointer items-center rounded-full border-2 border-transparent transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-emerald-400/50 ${
                            ee ? "bg-emerald-500" : "bg-white/15"
                          }`}
                        >
                          <span
                            className={`pointer-events-none block h-3.5 w-3.5 rounded-full bg-white shadow-sm ring-0 transition-transform ${
                              ee ? "translate-x-4" : "translate-x-0.5"
                            }`}
                          />
                        </button>
                      )}
                      {!showToggle && (tool.status === "not_found" || tool.status === "unknown") && (
                        <span className="text-[11px] text-white/35">—</span>
                      )}
                    </div>
                  </div>

                  {expanded && (
                    <div className="mt-3 space-y-3 border-t border-white/[0.06] pt-3">
                      {tool.setup_hint && <p className="text-[12px] text-white/45">{tool.setup_hint}</p>}

                      {tool.connect_kind === "local_scan" && (
                        <p className="text-[12px] text-white/50">
                          Not found on this computer. Connect this computer and scan again.
                        </p>
                      )}

                      {tool.connect_kind === "coming_soon" && (
                        <p className="text-[12px] text-white/50">Connect coming later.</p>
                      )}

                      {(tool.connect_kind === "api_key" || tool.connect_kind === "access_token") && (
                        <div className="space-y-2">
                          <label className="block text-[11px] font-medium text-white/50" htmlFor={`key-${tool.id}`}>
                            {pasteLabel}
                          </label>
                          <input
                            id={`key-${tool.id}`}
                            type="password"
                            autoComplete="off"
                            value={inputVal}
                            onChange={(e) =>
                              setConnectInputs((prev) => ({ ...prev, [tool.id]: e.target.value }))
                            }
                            className="w-full rounded-md border border-white/10 bg-black/30 px-3 py-2 text-[13px] text-white/90 placeholder:text-white/25"
                            placeholder=""
                          />
                          <div className="flex flex-wrap gap-2">
                            <button
                              type="button"
                              disabled={connectBusy === tool.id}
                              onClick={() => {
                                const body =
                                  tool.connect_kind === "access_token"
                                    ? { access_token: inputVal }
                                    : { api_key: inputVal };
                                void postConnect(tool.id, body);
                              }}
                              className="rounded-md bg-emerald-600/80 px-3 py-1.5 text-[12px] font-medium text-white hover:bg-emerald-600 disabled:opacity-50"
                            >
                              Connect
                            </button>
                            {tool.id === "cursor" && (tool.status === "ready" || tool.credential_preview) && (
                              <button
                                type="button"
                                disabled={connectBusy === tool.id}
                                onClick={() => void postDisconnect(tool.id)}
                                className="rounded-md border border-white/10 bg-white/[0.04] px-3 py-1.5 text-[12px] font-medium text-white/70 hover:bg-white/[0.08] disabled:opacity-50"
                              >
                                Disconnect
                              </button>
                            )}
                          </div>
                          <p className="text-[11px] text-white/35">
                            Your key is saved securely by HAM when Connect is available for this tool.
                          </p>
                          {connectRowError[tool.id] && (
                            <p className="text-[12px] text-amber-300/90">{connectRowError[tool.id]}</p>
                          )}
                        </div>
                      )}
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        </div>
      ))}
    </div>
  );
}
