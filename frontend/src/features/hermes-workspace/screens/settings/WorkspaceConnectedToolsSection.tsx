import * as React from "react";

type ToolStatus = "ready" | "needs_sign_in" | "not_found" | "off" | "error" | "unknown";
type ToolSource = "cloud" | "this_computer" | "built_in" | "unknown";

interface ToolEntry {
  id: string;
  label: string;
  category: string;
  status: ToolStatus;
  enabled: boolean;
  source: ToolSource;
  capabilities: string[];
  setup_hint: string | null;
  last_checked_at: string | null;
  safe_actions: string[];
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

function ToolRow({
  tool,
  onToggle,
}: {
  tool: ToolEntry;
  onToggle: (id: string, enabled: boolean) => void;
}) {
  return (
    <div className="flex items-center justify-between rounded-lg border border-white/[0.06] bg-white/[0.02] px-4 py-3">
      <div className="flex items-center gap-3">
        <span className={`h-2 w-2 rounded-full ${statusDotColor(tool.status)}`} />
        <div>
          <p className="text-[13px] font-medium text-white/90">{tool.label}</p>
          <p className="text-[11px] text-white/40">{STATUS_LABELS[tool.status]}</p>
        </div>
      </div>
      <div className="flex items-center gap-3">
        {tool.status === "needs_sign_in" && (
          <span className="rounded-md border border-white/10 bg-white/[0.04] px-2.5 py-1 text-[11px] font-medium text-white/50">
            Connect
          </span>
        )}
        <button
          type="button"
          role="switch"
          aria-checked={tool.enabled}
          aria-label={`Toggle ${tool.label}`}
          onClick={() => onToggle(tool.id, !tool.enabled)}
          className={`relative inline-flex h-5 w-9 shrink-0 cursor-pointer items-center rounded-full border-2 border-transparent transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-emerald-400/50 ${
            tool.enabled ? "bg-emerald-500" : "bg-white/15"
          }`}
        >
          <span
            className={`pointer-events-none block h-3.5 w-3.5 rounded-full bg-white shadow-sm ring-0 transition-transform ${
              tool.enabled ? "translate-x-4" : "translate-x-0.5"
            }`}
          />
        </button>
      </div>
    </div>
  );
}

export function WorkspaceConnectedToolsSection() {
  const [data, setData] = React.useState<ToolDiscoveryResponse | null>(null);
  const [loading, setLoading] = React.useState(true);
  const [error, setError] = React.useState<string | null>(null);
  const [toggleOverrides, setToggleOverrides] = React.useState<Record<string, boolean>>(() => {
    try {
      const saved = localStorage.getItem("ham_tool_toggles");
      return saved ? JSON.parse(saved) : {};
    } catch {
      return {};
    }
  });

  const fetchTools = React.useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const resp = await fetch("/api/workspace/tools");
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

  const handleToggle = React.useCallback((id: string, enabled: boolean) => {
    setToggleOverrides((prev) => {
      const next = { ...prev, [id]: enabled };
      try {
        localStorage.setItem("ham_tool_toggles", JSON.stringify(next));
      } catch {
        // localStorage unavailable — toggle is session-only
      }
      return next;
    });
  }, []);

  const tools: ToolEntry[] = React.useMemo(() => {
    if (!data) return [];
    return data.tools.map((t) => ({
      ...t,
      enabled: toggleOverrides[t.id] ?? t.enabled,
    }));
  }, [data, toggleOverrides]);

  const groupedTools = React.useMemo(() => {
    const groups: Record<string, ToolEntry[]> = {};
    for (const status of STATUS_GROUP_ORDER) {
      const matching = tools.filter((t) => t.status === status);
      if (matching.length > 0) {
        groups[status] = matching;
      }
    }
    return groups;
  }, [tools]);

  if (loading) {
    return (
      <div className="space-y-4">
        <h2 className="text-base font-semibold text-white/90">Connected tools</h2>
        <p className="text-[13px] text-white/40">Loading...</p>
      </div>
    );
  }

  if (error) {
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
          Tools and services HAM can use to help build, test, and automate your projects.
          Toggle each tool on or off to control what HAM can access.
        </p>
      </div>

      {data && !data.scan_available && data.scan_hint && (
        <div className="rounded-lg border border-amber-500/20 bg-amber-500/[0.04] px-4 py-3">
          <p className="text-[12px] text-amber-300/80">{data.scan_hint}</p>
        </div>
      )}

      <div className="flex items-center gap-2">
        <button
          type="button"
          onClick={fetchTools}
          className="rounded-md border border-white/10 bg-white/[0.04] px-3 py-1.5 text-[12px] font-medium text-white/60 hover:bg-white/[0.08]"
        >
          Scan again
        </button>
        <button
          type="button"
          onClick={() => {
            const all: Record<string, boolean> = {};
            tools.forEach((t) => { all[t.id] = true; });
            setToggleOverrides(all);
            try { localStorage.setItem("ham_tool_toggles", JSON.stringify(all)); } catch {}
          }}
          className="rounded-md border border-white/10 bg-white/[0.04] px-3 py-1.5 text-[12px] font-medium text-white/60 hover:bg-white/[0.08]"
        >
          Select all
        </button>
        <button
          type="button"
          onClick={() => {
            const none: Record<string, boolean> = {};
            tools.forEach((t) => { none[t.id] = false; });
            setToggleOverrides(none);
            try { localStorage.setItem("ham_tool_toggles", JSON.stringify(none)); } catch {}
          }}
          className="rounded-md border border-white/10 bg-white/[0.04] px-3 py-1.5 text-[12px] font-medium text-white/60 hover:bg-white/[0.08]"
        >
          Select none
        </button>
      </div>

      {Object.entries(groupedTools).map(([status, groupTools]) => (
        <div key={status} className="space-y-2">
          <h3 className="text-[11px] font-semibold uppercase tracking-wider text-white/35">
            {STATUS_LABELS[status as ToolStatus]}
          </h3>
          <div className="space-y-1.5">
            {groupTools.map((tool) => (
              <ToolRow key={tool.id} tool={tool} onToggle={handleToggle} />
            ))}
          </div>
        </div>
      ))}
    </div>
  );
}
