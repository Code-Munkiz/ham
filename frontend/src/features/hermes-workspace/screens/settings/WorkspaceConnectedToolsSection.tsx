import * as React from "react";
import {
  connectWorkspaceTool,
  disconnectWorkspaceTool,
  fetchWorkspaceTools,
  scanWorkspaceTools,
} from "@/lib/ham/api";

type ToolStatus = "ready" | "needs_sign_in" | "not_found" | "off" | "error" | "unknown";
type ToolConnection = "on" | "off" | "error";
type ToolSource = "cloud" | "this_computer" | "built_in" | "unknown";
type ConnectKind = "none" | "api_key" | "access_token" | "local_scan" | "coming_soon";

interface ToolEntry {
  id: string;
  label: string;
  category: string;
  status: ToolStatus;
  connection?: ToolConnection;
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

interface ConnectFailBody {
  ok?: boolean;
  message?: string;
  help?: { label?: string; url?: string } | null;
}

const CONNECTION_LABELS: Record<ToolConnection, string> = {
  on: "On",
  off: "Off",
  error: "Needs attention",
};

const CONNECTION_ORDER: ToolConnection[] = ["on", "off", "error"];

function connectionFromTool(tool: ToolEntry): ToolConnection {
  if (tool.connection) return tool.connection;
  if (tool.status === "error") return "error";
  if (tool.status === "ready") return "on";
  return "off";
}

function statusDotColor(conn: ToolConnection): string {
  switch (conn) {
    case "on":
      return "bg-emerald-400";
    case "error":
      return "bg-red-400";
    default:
      return "bg-white/20";
  }
}

function canShowToggle(tool: ToolEntry): boolean {
  return tool.status === "ready";
}

/** Select-all only affects tools that are connected and ready (never bypasses keys). */
function canSelectAllEnable(tool: ToolEntry): boolean {
  return tool.status === "ready";
}

function wantsApiKeyConnect(tool: ToolEntry): boolean {
  return (
    (tool.connect_kind === "api_key" || tool.connect_kind === "access_token") &&
    tool.safe_actions.includes("connect")
  );
}

function wantsDisconnect(tool: ToolEntry): boolean {
  return tool.safe_actions.includes("disconnect") && tool.status === "ready";
}

const TOOL_KEY_HELP: Record<string, { label: string; url: string }> = {
  openrouter: { label: "Get your OpenRouter API key", url: "https://openrouter.ai/keys" },
  claude_agent_sdk: {
    label: "Get your Anthropic API key",
    url: "https://console.anthropic.com/settings/keys",
  },
  github: {
    label: "Create a GitHub fine-grained token",
    url: "https://docs.github.com/en/authentication/keeping-your-account-and-data-secure/managing-your-personal-access-tokens#creating-a-fine-grained-personal-access-token",
  },
  cursor: { label: "Get your Cursor API key", url: "https://cursor.com/docs/cloud-agent/api" },
  openai_transcription: {
    label: "Create an OpenAI API key",
    url: "https://platform.openai.com/api-keys",
  },
};

const DEFAULT_CONNECTED_TOOLS_HEADING = "Connected tools";
const DEFAULT_CONNECTED_TOOLS_SUBTITLE =
  "Services and tools HAM can use for your projects. Each row shows whether it is connected (On or Off). Turn the switch On only after you connect — pasted keys stay on the server and are not stored in your browser.";

export type WorkspaceConnectedToolsSectionProps = {
  /** When set, only these tool ids are shown after fetch (embedded workbench subsets). */
  visibleToolIds?: readonly string[] | null;
  heading?: string;
  subtitle?: string;
};

export function WorkspaceConnectedToolsSection({
  visibleToolIds = null,
  heading = DEFAULT_CONNECTED_TOOLS_HEADING,
  subtitle = DEFAULT_CONNECTED_TOOLS_SUBTITLE,
}: WorkspaceConnectedToolsSectionProps = {}) {
  const [data, setData] = React.useState<ToolDiscoveryResponse | null>(null);
  const [loading, setLoading] = React.useState(true);
  const [error, setError] = React.useState<string | null>(null);
  const [toggleOverrides, setToggleOverrides] = React.useState<Record<string, boolean | undefined>>(
    {},
  );
  const [expandedId, setExpandedId] = React.useState<string | null>(null);
  const [connectInputs, setConnectInputs] = React.useState<Record<string, string>>({});
  const [connectBusy, setConnectBusy] = React.useState<string | null>(null);
  const [connectRowError, setConnectRowError] = React.useState<Record<string, string>>({});
  const [connectHelp, setConnectHelp] = React.useState<
    Record<string, { label: string; url: string } | undefined>
  >({});

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
    void fetchTools();
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

  const toolsAfterScope = React.useMemo(() => {
    const allow = visibleToolIds && visibleToolIds.length ? new Set(visibleToolIds) : null;
    if (!allow) return toolsWithEffective;
    return toolsWithEffective.filter((t) => allow.has(t.id));
  }, [toolsWithEffective, visibleToolIds]);

  const groupedTools = React.useMemo(() => {
    const groups: Record<ToolConnection, ToolEntry[]> = { on: [], off: [], error: [] };
    for (const t of toolsAfterScope) {
      groups[connectionFromTool(t)].push(t);
    }
    const ordered: Partial<Record<ToolConnection, ToolEntry[]>> = {};
    for (const c of CONNECTION_ORDER) {
      if (groups[c].length > 0) ordered[c] = groups[c];
    }
    return ordered;
  }, [toolsAfterScope]);

  const postConnect = async (toolId: string, body: Record<string, string>) => {
    setConnectBusy(toolId);
    setConnectRowError((prev) => ({ ...prev, [toolId]: "" }));
    setConnectHelp((prev) => ({ ...prev, [toolId]: undefined }));
    try {
      const resp = await connectWorkspaceTool(toolId, body);
      const parsed = (await resp.json().catch(() => null)) as ConnectFailBody | null;
      if (resp.ok && parsed && typeof parsed === "object" && parsed.ok === true) {
        await fetchTools();
        setConnectInputs((prev) => ({ ...prev, [toolId]: "" }));
        setExpandedId(null);
        return;
      }
      const msg =
        (parsed && typeof parsed.message === "string" && parsed.message) ||
        "That key did not work. Check that it is copied correctly and has the required permissions.";
      setConnectRowError((prev) => ({ ...prev, [toolId]: msg }));
      const h = parsed?.help;
      if (h && typeof h.label === "string" && typeof h.url === "string") {
        setConnectHelp((prev) => ({ ...prev, [toolId]: { label: h.label, url: h.url } }));
      }
    } catch {
      setConnectRowError((prev) => ({
        ...prev,
        [toolId]:
          "That key did not work. Check that it is copied correctly and has the required permissions.",
      }));
    } finally {
      setConnectBusy(null);
    }
  };

  const postDisconnect = async (toolId: string) => {
    setConnectBusy(toolId);
    setConnectRowError((prev) => ({ ...prev, [toolId]: "" }));
    setConnectHelp((prev) => ({ ...prev, [toolId]: undefined }));
    try {
      const resp = await disconnectWorkspaceTool(toolId);
      const parsed = (await resp.json().catch(() => null)) as { ok?: boolean } | null;
      if (resp.ok && parsed && parsed.ok === true) {
        await fetchTools();
        return;
      }
      setConnectRowError((prev) => ({
        ...prev,
        [toolId]: "Could not disconnect. Try again.",
      }));
    } catch {
      setConnectRowError((prev) => ({
        ...prev,
        [toolId]: "Could not disconnect. Try again.",
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
        <h2 className="text-base font-semibold text-white/90">{heading}</h2>
        <p className="text-[13px] text-white/40">Loading...</p>
      </div>
    );
  }

  if (error && !data) {
    return (
      <div className="space-y-4">
        <h2 className="text-base font-semibold text-white/90">{heading}</h2>
        <p className="text-[13px] text-red-400">{error}</p>
        <button
          type="button"
          onClick={() => void fetchTools()}
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
        <h2 className="text-base font-semibold text-white/90">{heading}</h2>
        <p className="mt-1 text-[13px] leading-relaxed text-white/45">{subtitle}</p>
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
            toolsAfterScope.forEach((t) => {
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
            toolsAfterScope.forEach((t) => {
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

      {Object.entries(groupedTools).map(([conn, groupTools]) => (
        <div key={conn} className="space-y-2">
          <h3 className="text-[11px] font-semibold uppercase tracking-wider text-white/35">
            {CONNECTION_LABELS[conn as ToolConnection]}
          </h3>
          <div className="space-y-1.5">
            {groupTools.map((tool) => {
              const ee = effectiveEnabled(tool);
              const expanded = expandedId === tool.id;
              const showToggle = canShowToggle(tool);
              const c = connectionFromTool(tool);
              const help = connectHelp[tool.id];

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
                      <span className={`h-2 w-2 shrink-0 rounded-full ${statusDotColor(c)}`} />
                      <div className="min-w-0">
                        <p className="text-[13px] font-medium text-white/90">{tool.label}</p>
                        <p className="text-[11px] text-white/40 truncate">
                          {[
                            showToggle ? (ee ? "In use" : "Not in use") : null,
                            `Status: ${CONNECTION_LABELS[c]}`,
                            tool.credential_preview,
                            tool.version,
                          ]
                            .filter((x): x is string => Boolean(x))
                            .join(" · ")}
                        </p>
                      </div>
                    </button>
                    <div className="flex shrink-0 items-center gap-3">
                      {tool.status === "needs_sign_in" && wantsApiKeyConnect(tool) && (
                        <span className="rounded-md border border-white/10 bg-white/[0.04] px-2.5 py-1 text-[11px] font-medium text-white/70">
                          Set up
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
                      {!showToggle &&
                        (tool.status === "not_found" || tool.status === "unknown") && (
                          <span className="text-[11px] text-white/35">—</span>
                        )}
                    </div>
                  </div>

                  {expanded && (
                    <div className="mt-3 space-y-3 border-t border-white/[0.06] pt-3">
                      {tool.setup_hint && (
                        <p className="text-[12px] text-white/45">{tool.setup_hint}</p>
                      )}

                      {tool.connect_kind === "local_scan" && (
                        <p className="text-[12px] text-white/50">
                          Connect this computer and scan again.
                        </p>
                      )}

                      {tool.connect_kind === "coming_soon" && (
                        <p className="text-[12px] text-white/50">
                          Connect later from settings when available.
                        </p>
                      )}

                      {wantsApiKeyConnect(tool) && (
                        <div className="space-y-2">
                          <label
                            className="block text-[11px] font-medium text-white/50"
                            htmlFor={`key-${tool.id}`}
                          >
                            {tool.connect_kind === "access_token"
                              ? "Paste your access token"
                              : "Paste your API key"}
                          </label>
                          <input
                            id={`key-${tool.id}`}
                            type="password"
                            autoComplete="off"
                            value={connectInputs[tool.id] ?? ""}
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
                                    ? { access_token: connectInputs[tool.id] ?? "" }
                                    : { api_key: connectInputs[tool.id] ?? "" };
                                void postConnect(tool.id, body);
                              }}
                              className="rounded-md bg-emerald-600/80 px-3 py-1.5 text-[12px] font-medium text-white hover:bg-emerald-600 disabled:opacity-50"
                            >
                              Connect
                            </button>
                            {wantsDisconnect(tool) && (
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
                          {(() => {
                            const link = help ?? TOOL_KEY_HELP[tool.id];
                            return link ? (
                              <p className="text-[12px] text-white/50">
                                <span className="text-white/40">Where to find it: </span>
                                <a
                                  href={link.url}
                                  target="_blank"
                                  rel="noreferrer"
                                  className="text-emerald-400/90 underline underline-offset-2 hover:text-emerald-300"
                                >
                                  {link.label}
                                </a>
                              </p>
                            ) : null;
                          })()}
                          {connectRowError[tool.id] && (
                            <p className="text-[12px] text-amber-300/90">
                              {connectRowError[tool.id]}
                            </p>
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
