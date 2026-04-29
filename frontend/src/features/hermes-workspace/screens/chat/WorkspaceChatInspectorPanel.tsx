/**
 * Upstream `inspector-panel.tsx` structure: header, tab bar, scroll body — honest empty / unavailable
 * per tab. Activity + Logs are wired from real HAM chat stream / session load events only.
 * Memory + Skills: read-only summaries via HAM workspace adapters (lazy-loaded per tab).
 */
import * as React from "react";
import { Link } from "react-router-dom";
import { X } from "lucide-react";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import type { HermesSkillCatalogEntry, HermesSkillCatalogEntryDetail, HermesSkillsInstalledResponse } from "@/lib/ham/api";
import {
  workspaceMemoryAdapter,
  type WorkspaceMemoryItem,
} from "../../adapters/memoryAdapter";
import { workspaceFileAdapter } from "../../adapters/filesAdapter";
import {
  fetchLocalWorkspaceHealth,
  isLocalRuntimeConfigured,
} from "../../adapters/localRuntime";
import {
  workspaceSkillsAdapter,
  type WorkspaceSkill,
} from "../../adapters/skillsAdapter";
import { primaryHermesCatalogLabel, workspaceFileEntryLabels } from "../../lib/workspaceHumanLabels";
import type { WorkspaceInspectorEvent } from "./workspaceInspectorEvents";
import {
  humanInspectorKindLabel,
  publicMetaSummary,
  statusLabelForUi,
} from "./workspaceInspectorEvents";
import type { WorkspaceComposerAttachment } from "./composerAttachmentHelpers";
import type { HwwMsgRow } from "./WorkspaceChatMessageList";
import {
  composerAttachmentRows,
  extractTranscriptAttachmentRows,
  type ChatInspectorArtifactRow,
  type ChatInspectorFileRow,
} from "./workspaceInspectorChatDerived";
import type { HamChatExecutionMode } from "@/lib/ham/api";

type TabId = "activity" | "artifacts" | "files" | "memory" | "skills" | "logs";

const TABS: Array<{ id: TabId; label: string }> = [
  { id: "activity", label: "Activity" },
  { id: "artifacts", label: "Artifacts" },
  { id: "files", label: "Files" },
  { id: "memory", label: "Memory" },
  { id: "skills", label: "Skills" },
  { id: "logs", label: "Logs" },
];

type WorkspaceChatInspectorPanelProps = {
  onClose: () => void;
  sessionId: string | null;
  events: WorkspaceInspectorEvent[];
  messages: HwwMsgRow[];
  composerAttachments: WorkspaceComposerAttachment[];
  artifactRows: ChatInspectorArtifactRow[];
  executionMode: HamChatExecutionMode | null;
};

const SKILL_BUILTIN = new Set(["ham-local-docs", "ham-local-plan"]);

const CATALOG_PREVIEW_N = 8;

function truncate(s: string, max: number): string {
  const t = s.trim();
  if (t.length <= max) return t;
  return `${t.slice(0, max - 1)}…`;
}

function formatMemoryTime(ts: number): string {
  try {
    return new Date(ts * 1000).toLocaleString(undefined, {
      month: "short",
      day: "numeric",
      hour: "2-digit",
      minute: "2-digit",
    });
  } catch {
    return "";
  }
}

type MemoryInspectorState =
  | { status: "idle" }
  | { status: "loading" }
  | { status: "ready"; items: WorkspaceMemoryItem[] }
  | { status: "error"; message: string };

type SkillsInspectorState =
  | { status: "idle" }
  | { status: "loading" }
  | {
      status: "ready";
      skills: WorkspaceSkill[];
      catalogCount: number | null;
      catalogError?: string;
      catalogSource: string | null;
      catalogPreview: HermesSkillCatalogEntry[];
      live: HermesSkillsInstalledResponse | null;
    }
  | { status: "error"; message: string };

type FilesWorkspaceState =
  | { status: "loading" }
  | { status: "unconfigured" }
  | { status: "error"; message: string }
  | { status: "ready"; rootPath: string; broad: boolean; entries: Array<{ name: string; type: "file" | "folder" }> };

function formatClock(iso: string): string {
  try {
    return new Date(iso).toLocaleTimeString([], {
      hour12: false,
      hour: "2-digit",
      minute: "2-digit",
      second: "2-digit",
    });
  } catch {
    return iso;
  }
}

function statusBadgeClass(status: WorkspaceInspectorEvent["status"]): string {
  switch (status) {
    case "error":
      return "bg-red-500/15 text-red-200/90";
    case "warning":
      return "bg-amber-500/15 text-amber-200/90";
    case "info":
      return "bg-sky-500/10 text-sky-200/85";
    default:
      return "bg-emerald-500/10 text-emerald-200/85";
  }
}

function InspectorEventList({
  events,
  emptyText,
  showKindChip,
}: {
  events: WorkspaceInspectorEvent[];
  emptyText: string;
  showKindChip: boolean;
}) {
  if (events.length === 0) {
    return (
      <div className="p-3">
        <p className="text-[12px] leading-relaxed text-white/60">{emptyText}</p>
      </div>
    );
  }
  return (
    <ul className="divide-y divide-white/[0.06]">
      {events.map((e) => {
        const extra = publicMetaSummary(e.meta);
        return (
          <li key={e.id} className="px-3 py-2.5">
            <div className="flex items-start justify-between gap-2">
              <div className="min-w-0 flex-1">
                {showKindChip ? (
                  <p className="mb-1 text-[10px] font-medium text-[#ffb27a]/85">
                    {humanInspectorKindLabel(e.kind)}
                  </p>
                ) : null}
                <p className="text-[12px] leading-snug text-white/[0.88]">{e.summary}</p>
                <p className="mt-1 text-[10px] leading-relaxed text-white/40">
                  {formatClock(e.atIso)}
                  {extra ? <span className="text-white/35"> · {extra}</span> : null}
                </p>
              </div>
              <span
                className={cn(
                  "shrink-0 rounded px-1.5 py-0.5 text-[9px] font-medium tracking-wide",
                  statusBadgeClass(e.status),
                )}
              >
                {statusLabelForUi(e.status)}
              </span>
            </div>
          </li>
        );
      })}
    </ul>
  );
}

function ActivityBody({ events }: { events: WorkspaceInspectorEvent[] }) {
  return (
    <InspectorEventList
      events={events}
      showKindChip={false}
      emptyText="No activity yet. Start a conversation to populate this timeline."
    />
  );
}

function LogsBody({ events }: { events: WorkspaceInspectorEvent[] }) {
  return (
    <InspectorEventList
      events={events}
      showKindChip
      emptyText="No events yet. They will show here after you send a message or load a session."
    />
  );
}

function InspectorLinkRow({ to, children }: { to: string; children: React.ReactNode }) {
  return (
    <div className="border-t border-white/[0.06] px-3 py-2.5">
      <Link
        to={to}
        className="text-[11px] font-medium text-[#ffb27a]/90 underline-offset-2 hover:underline"
      >
        {children}
      </Link>
    </div>
  );
}

function MemoryTabBody({ state, onRetry }: { state: MemoryInspectorState; onRetry: () => void }) {
  if (state.status === "idle" || state.status === "loading") {
    return (
      <div className="space-y-2 p-3">
        <div className="h-3 w-3/4 animate-pulse rounded bg-white/10" />
        <div className="h-3 w-1/2 animate-pulse rounded bg-white/10" />
        <div className="h-3 w-5/6 animate-pulse rounded bg-white/10" />
      </div>
    );
  }
  if (state.status === "error") {
    return (
      <div className="p-3">
        <p className="text-[12px] font-medium text-white/85">Memory API unavailable.</p>
        <p className="mt-1.5 text-[11px] leading-relaxed text-white/55">
          This tab reads from the HAM Workspace Memory API, not the local Files runtime.
        </p>
        <p className="mt-2 whitespace-pre-wrap break-words text-[10px] leading-relaxed text-amber-200/70">
          {state.message}
        </p>
        <Button
          type="button"
          variant="outline"
          size="sm"
          className="mt-3 h-7 border-white/20 text-[11px] text-white/80"
          onClick={onRetry}
        >
          Retry
        </Button>
        <InspectorLinkRow to="/workspace/memory">Open Memory</InspectorLinkRow>
      </div>
    );
  }
  if (state.items.length === 0) {
    return (
      <div className="p-3">
        <p className="text-[12px] leading-relaxed text-white/70">No memory entries available.</p>
        <p className="mt-1.5 text-[11px] leading-relaxed text-white/50">
          Workspace Memory is connected, but no entries are currently stored.
        </p>
        <InspectorLinkRow to="/workspace/memory">Open Memory</InspectorLinkRow>
      </div>
    );
  }
  const shown = state.items.slice(0, 12);
  return (
    <div>
      <ul className="divide-y divide-white/[0.06]">
        {shown.map((m) => (
          <li key={m.id} className="px-3 py-2">
            <div className="flex flex-wrap items-center gap-1.5">
              <span className="min-w-0 truncate text-[12px] font-medium text-white/[0.88]">
                {truncate(m.title || "(untitled)", 56)}
              </span>
              <span className="shrink-0 rounded bg-white/[0.08] px-1.5 py-0.5 text-[9px] uppercase tracking-wide text-white/55">
                {m.kind}
              </span>
              {m.archived ? (
                <span className="shrink-0 rounded bg-white/[0.06] px-1.5 py-0.5 text-[9px] text-white/45">
                  archived
                </span>
              ) : null}
            </div>
            {m.body ? (
              <p className="mt-1 line-clamp-2 text-[10px] leading-relaxed text-white/45">
                {truncate(m.body.replace(/\s+/g, " "), 120)}
              </p>
            ) : null}
            <p className="mt-1 text-[9px] text-white/35">Updated {formatMemoryTime(m.updatedAt)}</p>
          </li>
        ))}
      </ul>
      {state.items.length > 12 ? (
        <p className="px-3 py-2 text-[10px] text-white/40">+{state.items.length - 12} more in Memory</p>
      ) : null}
      <InspectorLinkRow to="/workspace/memory">Open Memory</InspectorLinkRow>
    </div>
  );
}

function SkillsTabBody({
  state,
  onRetry,
  onReloadAfterAction,
}: {
  state: SkillsInspectorState;
  onRetry: () => void;
  onReloadAfterAction: () => void;
}) {
  const [skillBusy, setSkillBusy] = React.useState<string | null>(null);
  const [skillActionErr, setSkillActionErr] = React.useState<string | null>(null);
  const [catDetail, setCatDetail] = React.useState<{
    catalogId: string;
    loading: boolean;
    entry: HermesSkillCatalogEntryDetail | null;
    error: string | null;
  } | null>(null);

  const openCatalogDetail = async (catalogId: string) => {
    setCatDetail({ catalogId, loading: true, entry: null, error: null });
    const { entry, error, bridge } = await workspaceSkillsAdapter.hermesStaticCatalogEntry(catalogId);
    if (bridge.status === "pending") {
      setCatDetail({ catalogId, loading: false, entry: null, error: bridge.detail });
      return;
    }
    setCatDetail({
      catalogId,
      loading: false,
      entry: entry ?? null,
      error: error ?? (!entry ? "No detail returned" : null),
    });
  };

  const runSkillPatch = async (id: string, body: { enabled?: boolean; installed?: boolean }) => {
    setSkillActionErr(null);
    setSkillBusy(id);
    const { error } = await workspaceSkillsAdapter.patch(id, body);
    setSkillBusy(null);
    if (error) {
      setSkillActionErr(error);
      return;
    }
    onReloadAfterAction();
  };

  const runSkillRemove = async (id: string) => {
    if (SKILL_BUILTIN.has(id)) return;
    if (!window.confirm("Remove this skill from the workspace?")) return;
    setSkillActionErr(null);
    setSkillBusy(id);
    const { error } = await workspaceSkillsAdapter.remove(id);
    setSkillBusy(null);
    if (error) {
      setSkillActionErr(error);
      return;
    }
    onReloadAfterAction();
  };

  if (state.status === "idle" || state.status === "loading") {
    return (
      <div className="space-y-2 p-3">
        <div className="h-3 w-2/3 animate-pulse rounded bg-white/10" />
        <div className="h-3 w-full animate-pulse rounded bg-white/10" />
        <div className="h-3 w-4/5 animate-pulse rounded bg-white/10" />
      </div>
    );
  }
  if (state.status === "error") {
    return (
      <div className="p-3">
        <p className="text-[12px] font-medium text-white/85">Skills API unavailable.</p>
        <p className="mt-1.5 text-[11px] leading-relaxed text-white/55">
          This tab reads from the HAM Workspace Skills API.
        </p>
        <p className="mt-2 whitespace-pre-wrap break-words text-[10px] leading-relaxed text-amber-200/70">
          {state.message}
        </p>
        <Button
          type="button"
          variant="outline"
          size="sm"
          className="mt-3 h-7 border-white/20 text-[11px] text-white/80"
          onClick={onRetry}
        >
          Retry
        </Button>
        <InspectorLinkRow to="/workspace/skills">Open Skills</InspectorLinkRow>
      </div>
    );
  }

  const { skills, catalogCount, catalogError, catalogSource, catalogPreview, live } = state;
  const hasInstalled = skills.some((s) => s.installed);
  const installedList = skills.filter((s) => s.installed);

  return (
    <div>
      {skillActionErr ? (
        <p className="mx-3 mt-2 rounded-lg border border-amber-500/25 bg-amber-500/10 px-2 py-1.5 text-[10px] text-amber-100/90">
          {skillActionErr}
        </p>
      ) : null}
      <div className="border-b border-white/[0.06] px-3 py-2">
        <p className="text-[10px] font-semibold uppercase tracking-wider text-white/45">Installed / workspace</p>
      </div>

      {!hasInstalled ? (
        <div className="p-3">
          <p className="text-[12px] leading-relaxed text-white/70">No skills installed yet.</p>
          <p className="mt-1.5 text-[11px] leading-relaxed text-white/50">
            Enable built-ins or add custom skills on the Skills page. Hermes catalog entries below are read-only until
            linked on the server.
          </p>
        </div>
      ) : (
        <ul className="divide-y divide-white/[0.06]">
          {installedList.slice(0, 16).map((s) => {
            const builtin = SKILL_BUILTIN.has(s.id);
            const busy = skillBusy === s.id;
            return (
              <li key={s.id} className="px-3 py-2">
                <p className="truncate text-[12px] font-medium text-white/[0.88]">{s.name}</p>
                <div className="mt-1 flex flex-wrap items-center gap-1">
                  {builtin ? (
                    <span className="rounded bg-sky-500/15 px-1.5 py-0.5 text-[9px] text-sky-200/85">built-in</span>
                  ) : (
                    <span className="rounded bg-violet-500/15 px-1.5 py-0.5 text-[9px] text-violet-200/85">
                      workspace
                    </span>
                  )}
                  <span className="rounded bg-white/[0.06] px-1.5 py-0.5 text-[9px] text-white/40">
                    {builtin ? "source: catalog" : "source: workspace"}
                  </span>
                  <span
                    className={cn(
                      "rounded px-1.5 py-0.5 text-[9px]",
                      s.enabled ? "bg-emerald-500/15 text-emerald-200/85" : "bg-white/[0.08] text-white/45",
                    )}
                  >
                    {s.enabled ? "enabled" : "disabled"}
                  </span>
                </div>
                {s.description ? (
                  <p className="mt-1 line-clamp-2 text-[10px] text-white/45">{truncate(s.description, 100)}</p>
                ) : null}
                <div className="mt-2 flex flex-wrap gap-1.5">
                  <Button
                    type="button"
                    variant="outline"
                    size="sm"
                    className="h-6 border-white/15 px-2 text-[10px] text-white/80"
                    disabled={busy}
                    onClick={() => void runSkillPatch(s.id, { enabled: !s.enabled })}
                  >
                    {s.enabled ? "Disable" : "Enable"}
                  </Button>
                  <Button
                    type="button"
                    variant="outline"
                    size="sm"
                    className="h-6 border-white/15 px-2 text-[10px] text-white/80"
                    disabled={busy || builtin}
                    title={builtin ? "Built-in entries stay in the catalog" : undefined}
                    onClick={() => void runSkillRemove(s.id)}
                  >
                    Remove
                  </Button>
                </div>
              </li>
            );
          })}
        </ul>
      )}
      {hasInstalled && installedList.length > 16 ? (
        <p className="px-3 py-2 text-[10px] text-white/40">+{installedList.length - 16} more in Skills</p>
      ) : null}

      <div className="border-t border-white/[0.06]">
        <p className="px-3 py-2 text-[10px] font-semibold uppercase tracking-wider text-white/45">Hermes catalog</p>
      </div>

      {catalogCount != null ? (
        <p className="border-b border-white/[0.06] px-3 py-2 text-[10px] text-white/50">
          <span className="font-medium text-white/65">{catalogCount}</span> catalog entries available
          {catalogSource ? (
            <>
              {" "}
              · Source: <span className="font-mono text-white/55">{catalogSource}</span>
            </>
          ) : null}
          <span className="text-white/40"> · Read-only catalog</span>
        </p>
      ) : catalogError ? (
        <p className="border-b border-white/[0.06] px-3 py-2 text-[10px] text-amber-200/70">
          Hermes catalog unavailable.
        </p>
      ) : null}

      {live && live.live_count > 0 ? (
        <p className="border-b border-white/[0.06] px-3 py-1.5 text-[9px] text-white/40">
          Live overlay: {live.live_count} reported · read-only
        </p>
      ) : null}

      {catalogPreview.length > 0 ? (
        <ul className="divide-y divide-white/[0.06]">
          {catalogPreview.map((e) => (
            <li key={e.catalog_id} className="flex items-start justify-between gap-2 px-3 py-2">
              <div className="min-w-0">
                <p
                  className="truncate text-[12px] font-medium text-white/[0.88]"
                  title={`${primaryHermesCatalogLabel(e)} — ${e.catalog_id}`}
                >
                  {primaryHermesCatalogLabel(e)}
                </p>
              </div>
              <Button
                type="button"
                variant="ghost"
                size="sm"
                className="h-6 shrink-0 px-2 text-[10px] text-[#ffb27a]/90"
                onClick={() => void openCatalogDetail(e.catalog_id)}
              >
                View
              </Button>
            </li>
          ))}
        </ul>
      ) : catalogCount != null && !catalogError ? (
        <p className="px-3 py-2 text-[10px] text-white/45">No preview rows (empty catalog payload).</p>
      ) : null}

      <p className="border-t border-white/[0.06] px-3 py-2 text-[10px] leading-relaxed text-white/40">
        Installing catalog-only entries as workspace skills requires the full Skills page and server-backed items (
        <span className="font-mono">/api/workspace/skills</span>). There is no Hermes VM or external hub call from the
        browser here.
      </p>

      <InspectorLinkRow to="/workspace/skills">Open Skills</InspectorLinkRow>

      {catDetail ? (
        <div
          className="fixed inset-0 z-[120] flex items-center justify-center bg-black/60 p-3"
          role="dialog"
          aria-modal="true"
          onClick={(ev) => {
            if (ev.target === ev.currentTarget) setCatDetail(null);
          }}
        >
          <div
            className="max-h-[min(85vh,480px)] w-full max-w-md overflow-y-auto rounded-xl border border-white/10 bg-[#061018] p-4 shadow-xl"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="flex items-start justify-between gap-2">
              <div className="min-w-0">
                <h4 className="text-sm font-semibold text-white/90">
                  Catalog: {primaryHermesCatalogLabel({ catalog_id: catDetail.catalogId })}
                </h4>
                <p className="mt-0.5 truncate font-mono text-[10px] text-white/45">{catDetail.catalogId}</p>
              </div>
              <Button type="button" variant="ghost" size="sm" className="h-7 text-[11px]" onClick={() => setCatDetail(null)}>
                Close
              </Button>
            </div>
            {catDetail.loading ? <p className="mt-3 text-[12px] text-white/50">Loading…</p> : null}
            {catDetail.error ? (
              <p className="mt-3 whitespace-pre-wrap text-[11px] text-amber-200/80">{catDetail.error}</p>
            ) : null}
            {catDetail.entry ? (
              <div className="mt-3 space-y-2 text-[11px] text-white/70">
                <p className="font-medium text-white/85">
                  {primaryHermesCatalogLabel(catDetail.entry)}
                </p>
                {catDetail.entry.summary ? (
                  <p className="leading-relaxed text-white/60">{catDetail.entry.summary}</p>
                ) : null}
                {catDetail.entry.detail?.provenance_note ? (
                  <p className="text-[10px] text-white/45">{catDetail.entry.detail.provenance_note}</p>
                ) : null}
              </div>
            ) : null}
          </div>
        </div>
      ) : null}
    </div>
  );
}

function FilesTabBody({ fileRows }: { fileRows: ChatInspectorFileRow[] }) {
  const hasRows = fileRows.length > 0;
  const [ws, setWs] = React.useState<FilesWorkspaceState>({ status: "loading" });
  const [wsTick, setWsTick] = React.useState(0);

  const loadWorkspaceFiles = React.useCallback(async () => {
    if (!isLocalRuntimeConfigured()) {
      setWs({ status: "unconfigured" });
      return;
    }
    setWs({ status: "loading" });
    const health = await fetchLocalWorkspaceHealth();
    const { entries, bridge } = await workspaceFileAdapter.list();
    if (bridge.status !== "ready") {
      setWs({ status: "error", message: bridge.detail });
      return;
    }
    const rootPath =
      health?.workspaceRootPath?.trim() ||
      (health?.workspaceRootConfigured === true ? "(workspace root configured)" : "—");
    const broad = health?.broadFilesystemAccess === true;
    setWs({
      status: "ready",
      rootPath,
      broad,
      entries: entries.slice(0, 12).map((e) => ({ name: e.name, type: e.type })),
    });
  }, [wsTick]);

  React.useEffect(() => {
    void loadWorkspaceFiles();
  }, [loadWorkspaceFiles]);

  React.useEffect(() => {
    const onRuntime = () => setWsTick((n) => n + 1);
    window.addEventListener("hww-local-runtime-changed", onRuntime);
    return () => window.removeEventListener("hww-local-runtime-changed", onRuntime);
  }, []);

  return (
    <div>
      <div className="border-b border-white/[0.06] px-3 py-2">
        <p className="text-[10px] font-semibold uppercase tracking-wider text-white/45">Session attachments</p>
      </div>
      {hasRows ? (
        <ul className="divide-y divide-white/[0.06]">
          {fileRows.map((r) => (
            <li key={r.id} className="px-3 py-2">
              <p className="truncate text-[12px] font-medium text-white/[0.88]">{r.name}</p>
              <div className="mt-1 flex flex-wrap items-center gap-1.5">
                <span className="rounded bg-white/[0.08] px-1.5 py-0.5 text-[9px] text-white/55">
                  {r.kindLabel}
                </span>
                <span className="text-[10px] text-white/45">{r.sizeLabel}</span>
                <span
                  className={cn(
                    "rounded px-1.5 py-0.5 text-[9px]",
                    r.source === "queued_in_composer"
                      ? "bg-amber-500/15 text-amber-200/80"
                      : "bg-white/[0.06] text-white/40",
                  )}
                >
                  {r.source === "queued_in_composer" ? "in composer" : "in transcript"}
                </span>
              </div>
              {r.atLabel ? (
                <p className="mt-1 text-[9px] text-white/35">Sent {r.atLabel}</p>
              ) : null}
            </li>
          ))}
        </ul>
      ) : (
        <div className="p-3">
          <p className="text-[12px] leading-relaxed text-white/70">No files attached to this session yet.</p>
          <p className="mt-1.5 text-[11px] leading-relaxed text-white/50">
            Queued composer attachments and transcript markers appear here.
          </p>
        </div>
      )}

      <div className="border-t border-white/[0.06]">
        <p className="px-3 py-2 text-[10px] font-semibold uppercase tracking-wider text-white/45">Workspace file browser</p>
      </div>

      {ws.status === "loading" ? (
        <div className="space-y-2 p-3">
          <div className="h-3 w-2/3 animate-pulse rounded bg-white/10" />
          <div className="h-3 w-1/2 animate-pulse rounded bg-white/10" />
        </div>
      ) : null}

      {ws.status === "unconfigured" ? (
        <div className="p-3">
          <p className="text-[12px] leading-relaxed text-white/70">Workspace file browser is not connected.</p>
          <p className="mt-1.5 text-[11px] leading-relaxed text-white/50">
            Connect the local HAM runtime in Settings → Connection to browse files on this machine.
          </p>
          <InspectorLinkRow to="/workspace/settings?section=connection">Open Connection</InspectorLinkRow>
        </div>
      ) : null}

      {ws.status === "error" ? (
        <div className="p-3">
          <p className="text-[12px] font-medium text-white/80">Could not reach local file browser</p>
          <p className="mt-1.5 whitespace-pre-wrap break-words text-[10px] leading-relaxed text-amber-200/75">
            {ws.message}
          </p>
          <Button
            type="button"
            variant="outline"
            size="sm"
            className="mt-2 h-7 border-white/20 text-[11px] text-white/80"
            onClick={() => setWsTick((n) => n + 1)}
          >
            Retry
          </Button>
        </div>
      ) : null}

      {ws.status === "ready" ? (
        <div className="px-3 py-2">
          <p className="text-[11px] font-medium text-emerald-200/85">Workspace file browser connected</p>
          <p className="mt-1 text-[10px] text-white/55">
            Root: <span className="font-mono text-white/70">{ws.rootPath}</span>
          </p>
          <p className="mt-1 text-[10px] text-white/45">
            {ws.broad ? "Broad filesystem access (wide root)" : "Scoped to configured workspace root"}
          </p>
          {ws.entries.length > 0 ? (
            <ul className="mt-2 rounded-lg border border-white/[0.08] bg-white/[0.03]">
              {ws.entries.map((e) => {
                const { label, technical } = workspaceFileEntryLabels(e.name);
                return (
                  <li
                    key={`${e.type}:${e.name}`}
                    className="flex items-center gap-2 border-b border-white/[0.05] px-2 py-1.5 text-[11px] last:border-b-0"
                  >
                    <span className="text-white/35">{e.type === "folder" ? "📁" : "📄"}</span>
                    <span className="flex min-w-0 flex-1 flex-col">
                      <span className="truncate text-white/80">{label}</span>
                      {technical ? (
                        <span className="truncate font-mono text-[9px] text-white/40">{technical}</span>
                      ) : null}
                    </span>
                  </li>
                );
              })}
            </ul>
          ) : (
            <p className="mt-2 text-[10px] text-white/45">Root listing is empty (or not returned).</p>
          )}
        </div>
      ) : null}

      <InspectorLinkRow to="/workspace/files">Open Files</InspectorLinkRow>
    </div>
  );
}

function ArtifactsTabBody({ rows }: { rows: ChatInspectorArtifactRow[] }) {
  if (rows.length === 0) {
    return (
      <div className="p-3">
        <p className="text-[12px] leading-relaxed text-white/70">No artifacts generated yet.</p>
        <p className="mt-1.5 text-[11px] leading-relaxed text-white/50">
          Generated files, UI actions, and mission outputs will appear here when available.
        </p>
      </div>
    );
  }
  const newestFirst = [...rows].slice(-24).reverse();
  return (
    <ul className="divide-y divide-white/[0.06]">
      {newestFirst.map((r) => (
        <li key={r.id} className="px-3 py-2">
          <p className="text-[12px] font-medium leading-snug text-white/[0.88]">{r.title}</p>
          <div className="mt-1 flex flex-wrap gap-1">
            <span className="rounded bg-violet-500/15 px-1.5 py-0.5 text-[9px] text-violet-200/85">
              {r.typeLabel}
            </span>
            <span className="rounded bg-white/[0.08] px-1.5 py-0.5 text-[9px] text-white/50">{r.source}</span>
            <span
              className={cn(
                "rounded px-1.5 py-0.5 text-[9px]",
                r.status === "ok" || r.status === "applied"
                  ? "bg-emerald-500/12 text-emerald-200/85"
                  : r.status === "blocked"
                    ? "bg-red-500/15 text-red-200/85"
                    : "bg-white/[0.08] text-white/45",
              )}
            >
              {r.status}
            </span>
          </div>
          {r.detail ? (
            <p className="mt-1 whitespace-pre-wrap break-words text-[10px] text-amber-200/70">{r.detail}</p>
          ) : null}
          <div className="mt-1.5 flex flex-wrap items-center gap-2">
            <span className="text-[9px] text-white/35">{formatClock(r.atIso)}</span>
            {r.navigateTo ? (
              <Link
                to={r.navigateTo}
                className="text-[10px] font-medium text-[#ffb27a]/90 underline-offset-2 hover:underline"
              >
                Open
              </Link>
            ) : null}
          </div>
        </li>
      ))}
    </ul>
  );
}

export function WorkspaceChatInspectorPanel({
  onClose,
  sessionId,
  events,
  messages,
  composerAttachments,
  artifactRows,
  executionMode,
}: WorkspaceChatInspectorPanelProps) {
  const [activeTab, setActiveTab] = React.useState<TabId>("activity");
  const [memoryState, setMemoryState] = React.useState<MemoryInspectorState>({ status: "idle" });
  const [skillsState, setSkillsState] = React.useState<SkillsInspectorState>({ status: "idle" });

  const fileRows = React.useMemo(() => {
    const queued = composerAttachmentRows(composerAttachments);
    const fromTx = extractTranscriptAttachmentRows(messages);
    return [...queued, ...fromTx];
  }, [composerAttachments, messages]);

  const loadMemory = React.useCallback(() => {
    setMemoryState({ status: "loading" });
    void workspaceMemoryAdapter.list(undefined, false).then(({ items, bridge }) => {
      if (bridge.status === "pending") {
        setMemoryState({ status: "error", message: bridge.detail });
      } else {
        setMemoryState({ status: "ready", items });
      }
    });
  }, []);

  const loadSkills = React.useCallback(() => {
    setSkillsState({ status: "loading" });
    void workspaceSkillsAdapter.list().then((inst) => {
      if (inst.bridge.status === "pending") {
        setSkillsState({ status: "error", message: inst.bridge.detail });
        return;
      }
      void Promise.all([
        workspaceSkillsAdapter.hermesStaticCatalog(),
        workspaceSkillsAdapter.hermesLiveOverlay(),
      ]).then(([cat, live]) => {
        const catalogCount =
          cat.data != null ? cat.data.count ?? cat.data.entries.length : null;
        const catalogSource = cat.data?.source ?? null;
        const catalogPreview =
          cat.data != null && Array.isArray(cat.data.entries) && cat.data.entries.length > 0
            ? [...cat.data.entries]
                .sort((a, b) => a.catalog_id.localeCompare(b.catalog_id))
                .slice(0, CATALOG_PREVIEW_N)
            : [];
        setSkillsState({
          status: "ready",
          skills: inst.skills,
          catalogCount,
          catalogError: cat.bridge.status === "pending" ? cat.bridge.detail : undefined,
          catalogSource,
          catalogPreview,
          live: live.bridge.status === "ready" ? live.overlay : null,
        });
      });
    });
  }, []);

  React.useEffect(() => {
    if (activeTab !== "memory") return;
    if (memoryState.status !== "idle") return;
    loadMemory();
  }, [activeTab, memoryState.status, loadMemory]);

  React.useEffect(() => {
    if (activeTab !== "skills") return;
    if (skillsState.status !== "idle") return;
    loadSkills();
  }, [activeTab, skillsState.status, loadSkills]);

  return (
    <aside
      className={cn(
        "hww-inspector flex h-full min-h-0 w-[min(100vw,22rem)] shrink-0 flex-col overflow-hidden",
        "border-l border-white/[0.08] bg-[#040d14]/95 shadow-[inset_1px_0_0_0_rgba(255,255,255,0.04)]",
        "md:w-[min(100vw,350px)]",
      )}
      style={{
        boxShadow: "-4px 0 16px rgba(0, 0, 0, 0.2)",
      }}
      aria-label="Inspector"
    >
      <div className="flex shrink-0 items-center justify-between gap-2 border-b border-white/[0.08] px-3 py-2.5">
        <div className="min-w-0">
          <h2 className="text-sm font-semibold text-white/90">Inspector</h2>
          {sessionId ? (
            <p className="mt-0.5 truncate text-[10px] text-white/45">This chat is saved on the server</p>
          ) : (
            <p className="mt-0.5 text-[10px] text-white/45">Start chatting to create a session</p>
          )}
          {executionMode ? (
            <p className="mt-1 text-[10px] text-white/55">
              Execution:{" "}
              <span className="font-medium text-white/80">
                {executionMode.selected_mode}
                {executionMode.browser_adapter ? ` (${executionMode.browser_adapter})` : ""}
              </span>
            </p>
          ) : null}
        </div>
        <Button
          type="button"
          variant="ghost"
          size="icon"
          className="h-8 w-8 text-white/50 hover:text-white/90"
          onClick={onClose}
          aria-label="Close inspector"
        >
          <X className="h-4 w-4" strokeWidth={1.5} />
        </Button>
      </div>

      <div className="flex shrink-0 gap-0 overflow-x-auto border-b border-white/[0.08]">
        {TABS.map((tab) => {
          const active = activeTab === tab.id;
          return (
            <button
              key={tab.id}
              type="button"
              onClick={() => {
                setActiveTab(tab.id);
              }}
              className={cn(
                "shrink-0 px-2.5 py-2.5 text-[11px] font-medium transition-colors",
                active ? "border-b-2 text-[#ffb27a]" : "border-b-2 border-transparent text-white/45 hover:text-white/75",
              )}
              style={
                active
                  ? { borderBottomColor: "rgba(196, 92, 18, 0.8)" }
                  : { borderBottomColor: "transparent" }
              }
            >
              {tab.label}
            </button>
          );
        })}
      </div>

      <div className="hww-scroll min-h-0 flex-1 overflow-y-auto">
        {activeTab === "activity" ? <ActivityBody events={events} /> : null}
        {activeTab === "logs" ? <LogsBody events={events} /> : null}
        {activeTab === "artifacts" ? <ArtifactsTabBody rows={artifactRows} /> : null}
        {activeTab === "files" ? <FilesTabBody fileRows={fileRows} /> : null}
        {activeTab === "memory" ? (
          <MemoryTabBody state={memoryState} onRetry={loadMemory} />
        ) : null}
        {activeTab === "skills" ? (
          <SkillsTabBody state={skillsState} onRetry={loadSkills} onReloadAfterAction={loadSkills} />
        ) : null}
      </div>
    </aside>
  );
}

export type { WorkspaceInspectorEvent } from "./workspaceInspectorEvents";
