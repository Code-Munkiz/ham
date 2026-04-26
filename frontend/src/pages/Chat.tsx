/**
 * `/chat` workbench: **single owner** for layout, split state, and right execution pane.
 * `AppLayout` does not manage competing split logic for this route (see AppLayout comment).
 */
import * as React from "react";
import { useAuth } from "@clerk/clerk-react";
import {
  Paperclip,
  Sparkles,
  Zap,
  Shield,
  Activity,
  Monitor,
  Globe,
  Layout,
  ChevronDown,
  ChevronUp,
  Radio,
  X,
  AlertCircle,
  Radar,
  History,
  MessageSquare,
  Plus,
  Search,
} from "lucide-react";
import { toast } from "sonner";
import { useNavigate } from "react-router-dom";
import { cn } from "@/lib/utils";
import { ChatComposerStrip } from "@/components/chat/ChatComposerStrip";
import type { WorkbenchMode, UplinkId } from "@/components/chat/ChatComposerStrip";
import { CloudAgentLaunchModal } from "@/components/chat/CloudAgentLaunchModal";
import { VoiceMessageInput } from "@/components/chat/VoiceMessageInput";
import { applyHamUiActions } from "@/lib/ham/applyUiActions";
import {
  ensureProjectIdForWorkspaceRoot,
  fetchContextEngine,
  fetchModelsCatalog,
  fetchProjectAgents,
  fetchChatSessions,
  fetchChatSession,
  fetchManagedDeployHookStatus,
  fetchManagedDeployApprovalStatus,
  fetchManagedMissionsList,
  type ManagedMissionRow,
  type ManagedDeployApprovalStatusPayload,
  postManagedDeployApprovalDecision,
  type VercelHookMapping,
  getApiBase,
  listHamProjects,
  patchHamProjectMetadata,
  HamAccessRestrictedError,
  postChatStream,
  postChatTranscribe,
  postCursorAgentSync,
  postManagedDeployHook,
  type ManagedDeployHookResult,
  type HamChatStreamAuth,
  type HamOperatorResult,
  type HamChatOperatorPayload,
  type ChatSessionSummary,
} from "@/lib/ham/api";
import {
  buildManagedCompletionMessage,
  buildManagedReviewChatMessage,
  completionInjectionSignature,
  isCloudAgentTerminal,
  reviewChatInjectionSignature,
  shouldEmitReviewChatLine,
} from "@/lib/ham/managedCloudAgent";
import { CLIENT_MODEL_CATALOG_FALLBACK } from "@/lib/ham/modelCatalogFallback";
import type {
  CloudMissionHandling,
  ManagedDeployHandoffState,
  ManagedMissionReview,
  ModelCatalogPayload,
  ProjectRecord,
} from "@/lib/ham/types";
import { PROJECT_DEFAULT_DEPLOY_APPROVAL_KEY, type ProjectDefaultDeployPolicy } from "@/lib/ham/projectDeployPolicy";
import {
  getActiveProjectName,
  getCursorCloudRepository,
  shortDigest,
} from "@/lib/ham/cloudAgentProjectDefaults";
import {
  buildPreviousWorkSummaryLine,
  stitchCloudAgentFollowUpTask,
} from "@/lib/ham/cloudAgentFollowUp";
import { inferMissionTitleForCard, isCloudAgentHandoffRequest } from "@/lib/ham/cloudAgentChatHandoff";
import {
  formatManagedMissionStatusChatLine,
  isCloudAgentStatusChatQuestion,
} from "@/lib/ham/cloudAgentStatusChat";
import {
  loadPendingCursorAgentSessionSnapshot,
  savePendingCursorAgentSessionSnapshot,
} from "@/lib/ham/pendingCursorAgentSession";
import { ProjectsRegistryPanel } from "@/components/chat/ProjectsRegistryPanel";
import { ManagedCloudAgentProvider } from "@/contexts/ManagedCloudAgentContext";
import { useManagedCloudAgentPoll } from "@/hooks/useManagedCloudAgentPoll";
import { getChatGatewayReadinessToken } from "@/lib/ham/types";
import { useAgent } from "@/lib/ham/AgentContext";
import { useWorkspace } from "@/lib/ham/WorkspaceContext";
import { ResizableWorkbenchSplit } from "@/components/war-room/ResizableWorkbenchSplit";
import { WarRoomPane } from "@/components/war-room/WarRoomPane";
import { LiveManagedMissionBanner } from "@/components/war-room/LiveManagedMissionBanner";
import type { WarRoomTabId } from "@/components/war-room/uplinkConfig";
import { OperatorWorkspace } from "@/features/operator-workspace";
import type {
  OperatorAttachment,
  OperatorMessage,
  OperatorSessionItem,
} from "@/features/operator-workspace";

type ChatRow = {
  id: string;
  role: "user" | "assistant" | "system";
  content: string;
  timestamp: string;
};

type ChatViewMode = "chat" | "split" | "preview" | "war_room" | "browser";

/** Local-only composer attachment (inlined into outbound message text; no API change). */
type ComposerAttachmentKind = "image" | "text" | "binary";

type ComposerAttachment = {
  id: string;
  name: string;
  size: number;
  kind: ComposerAttachmentKind;
  /** Image: data URL. Text: file body. Binary: omitted at send (placeholder only). */
  payload: string;
};

const MAX_CHAT_ATTACHMENT_BYTES = 500 * 1024;
const CHAT_ATTACHMENT_ACCEPT =
  "image/*,.txt,.csv,.json,.pdf,.xlsx,text/plain,text/csv,application/json,application/pdf,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet";
const USE_OPERATOR_WORKSPACE = true;

const TEXT_FILE_EXTENSIONS = new Set([".txt", ".csv", ".json"]);
const IMAGE_FILE_EXTENSIONS = new Set([
  ".png",
  ".jpg",
  ".jpeg",
  ".gif",
  ".webp",
  ".svg",
  ".bmp",
  ".ico",
]);

function fileExtensionLower(name: string): string {
  const i = name.lastIndexOf(".");
  return i >= 0 ? name.slice(i).toLowerCase() : "";
}

function formatAttachmentByteSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  const kb = bytes / 1024;
  if (kb < 1024) return `${kb >= 10 ? kb.toFixed(0) : kb.toFixed(1)} KB`;
  return `${(kb / 1024).toFixed(1)} MB`;
}

function classifyComposerAttachment(file: File): ComposerAttachmentKind {
  const ext = fileExtensionLower(file.name);
  if (file.type.startsWith("image/") || IMAGE_FILE_EXTENSIONS.has(ext)) return "image";
  if (
    TEXT_FILE_EXTENSIONS.has(ext) ||
    file.type.startsWith("text/") ||
    file.type === "application/json" ||
    file.type === "text/csv"
  ) {
    return "text";
  }
  return "binary";
}

function readFileAsDataURL(file: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const r = new FileReader();
    r.onload = () => {
      const res = r.result;
      if (typeof res === "string") resolve(res);
      else reject(new Error("Could not read file as data URL"));
    };
    r.onerror = () => reject(r.error ?? new Error("File read failed"));
    r.readAsDataURL(file);
  });
}

function readFileAsText(file: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const r = new FileReader();
    r.onload = () => {
      const res = r.result;
      if (typeof res === "string") resolve(res);
      else reject(new Error("Could not read file as text"));
    };
    r.onerror = () => reject(r.error ?? new Error("File read failed"));
    r.readAsText(file);
  });
}

function binaryAttachmentPlaceholder(name: string, size: number): string {
  return `[Attached: ${name} (${formatAttachmentByteSize(size)}) — contents not inlined for this file type.]`;
}

function buildOutboundMessageWithAttachment(
  trimmedText: string,
  attachment: ComposerAttachment | null,
): string {
  if (!attachment) return trimmedText;
  if (attachment.kind === "binary") {
    const block = binaryAttachmentPlaceholder(attachment.name, attachment.size);
    return trimmedText ? `${block}\n\n${trimmedText}` : block;
  }
  const header =
    attachment.kind === "image"
      ? `[Attached image: ${attachment.name} (${formatAttachmentByteSize(attachment.size)})]`
      : `[Attached file: ${attachment.name} (${formatAttachmentByteSize(attachment.size)})]`;
  const body = attachment.payload.trimEnd();
  const combined = `${header}\n${body}`;
  return trimmedText ? `${combined}\n\n${trimmedText}` : combined;
}

function formatShortcutAge(t: number): string {
  const s = Math.floor((Date.now() - t) / 1000);
  if (s < 0) return "now";
  if (s < 60) return `${s}s ago`;
  const m = Math.floor(s / 60);
  if (m < 60) return `${m}m ago`;
  const h = Math.floor(m / 60);
  if (h < 48) return `${h}h ago`;
  return new Date(t).toLocaleDateString();
}

const RECENT_MISSIONS_KEY = "ham_recent_missions_v1";
const MOUNT_STORAGE_KEY = "ham_project_mount_v1";
const ACTIVE_CLOUD_AGENT_KEY = "ham_active_cloud_agent_id";
const CLOUD_MISSION_HANDLING_KEY = "ham_cloud_mission_handling";
const ACTIVE_SESSION_KEY = "ham_active_chat_session_id";
const MANAGED_COMPLETION_STORAGE_KEY = "ham_managed_completion_v1";
const MANAGED_REVIEW_CHAT_STORAGE_KEY = "ham_managed_review_chat_v1";
const MANAGED_DEPLOY_CHAT_STORAGE_KEY = "ham_managed_deploy_chat_v1";

/** Matches `format_operator_assistant_message` for a successful Cursor Cloud Agent preview (server). */
const OPERATOR_CURSOR_ASSISTANT_HEAD = "**Operator — Cursor Cloud Agent preview**";

function condensedCursorOperatorBubbleText(content: string): string | null {
  if (!content.startsWith(OPERATOR_CURSOR_ASSISTANT_HEAD)) return null;
  return "Cloud Agent preview ready — use the mission card below.";
}

function loadManagedCompletionMap(): Record<string, string> {
  try {
    const raw = localStorage.getItem(MANAGED_COMPLETION_STORAGE_KEY);
    if (!raw) return {};
    const o = JSON.parse(raw) as unknown;
    if (typeof o !== "object" || o === null || Array.isArray(o)) return {};
    return o as Record<string, string>;
  } catch {
    return {};
  }
}

function saveManagedCompletionMap(m: Record<string, string>) {
  try {
    localStorage.setItem(MANAGED_COMPLETION_STORAGE_KEY, JSON.stringify(m));
  } catch {
    /* ignore */
  }
}

function loadManagedReviewChatMap(): Record<string, string> {
  try {
    const raw = localStorage.getItem(MANAGED_REVIEW_CHAT_STORAGE_KEY);
    if (!raw) return {};
    const o = JSON.parse(raw) as unknown;
    if (typeof o !== "object" || o === null || Array.isArray(o)) return {};
    return o as Record<string, string>;
  } catch {
    return {};
  }
}

function saveManagedReviewChatMap(m: Record<string, string>) {
  try {
    localStorage.setItem(MANAGED_REVIEW_CHAT_STORAGE_KEY, JSON.stringify(m));
  } catch {
    /* ignore */
  }
}

function loadManagedDeployChatMap(): Record<string, string> {
  try {
    const raw = localStorage.getItem(MANAGED_DEPLOY_CHAT_STORAGE_KEY);
    if (!raw) return {};
    const o = JSON.parse(raw) as unknown;
    if (typeof o !== "object" || o === null || Array.isArray(o)) return {};
    return o as Record<string, string>;
  } catch {
    return {};
  }
}

function saveManagedDeployChatMap(m: Record<string, string>) {
  try {
    localStorage.setItem(MANAGED_DEPLOY_CHAT_STORAGE_KEY, JSON.stringify(m));
  } catch {
    /* ignore */
  }
}

type RecentMission = { id: string; label?: string; t: number };

function loadRecentMissions(): RecentMission[] {
  try {
    const raw = localStorage.getItem(RECENT_MISSIONS_KEY);
    if (!raw) return [];
    const j = JSON.parse(raw) as unknown;
    if (!Array.isArray(j)) return [];
    return j.filter(
      (x): x is RecentMission =>
        typeof x === "object" &&
        x !== null &&
        typeof (x as RecentMission).id === "string" &&
        typeof (x as RecentMission).t === "number",
    );
  } catch {
    return [];
  }
}

function saveRecentMissions(items: RecentMission[]) {
  try {
    localStorage.setItem(RECENT_MISSIONS_KEY, JSON.stringify(items.slice(0, 24)));
  } catch {
    /* ignore */
  }
}

function parseStoredMissionHandling(raw: string | null | undefined): CloudMissionHandling {
  if (raw === "managed") return "managed";
  return "direct";
}

function directivePlaceholder(mode: WorkbenchMode): string {
  if (mode === "ask") return "Ask HAM to inspect, explain, or answer…";
  if (mode === "plan") return "Plan scope, risks, and the safest path before execution…";
  return "Delegate execution — mission directive…";
}

function uplinkPipelineLabel(id: UplinkId): string {
  if (id === "cloud_agent") return "CLOUD_AGENT";
  if (id === "factory_ai") return "FACTORY_AI";
  return "ELIZA_OS";
}

function workbenchLayoutTriggerLabel(mode: ChatViewMode): string {
  if (mode === "split") return "Split";
  if (mode === "preview") return "Preview";
  if (mode === "war_room") return "War Room";
  if (mode === "browser") return "Browser";
  return "View";
}

type TranscriptColumnProps = {
  messages: ChatRow[];
  primaryPersona: { name: string; avatarUrl: string | null } | null;
  /** Human-readable name for the active HAM project (not `project_id`). */
  activeProjectName: string | null;
  /** In-thread Cloud Agent mission preview (digest-locked) + confirm launch — from `operator_result.pending_cursor_agent`. */
  pendingCursorAgent: Record<string, unknown> | null;
  operatorCursorAgentToken: string;
  onOperatorCursorAgentTokenChange: (v: string) => void;
  onCursorAgentLaunch: () => void;
  onDismissCursorPreview: () => void;
  cursorAgentActionsDisabled: boolean;
  /** Chat handoff: save `cursor_cloud_repository` then preview. */
  cloudHandoffRepoSetup: { missionText: string; repoInput: string } | null;
  onHandoffRepoInputChange: (v: string) => void;
  onHandoffSaveRepoAndPreview: () => void;
  onDismissHandoffRepoSetup: () => void;
  handoffRepoSaving: boolean;
};

function TranscriptColumn({
  messages,
  primaryPersona,
  activeProjectName,
  pendingCursorAgent,
  operatorCursorAgentToken,
  onOperatorCursorAgentTokenChange,
  onCursorAgentLaunch,
  onDismissCursorPreview,
  cursorAgentActionsDisabled,
  cloudHandoffRepoSetup,
  onHandoffRepoInputChange,
  onHandoffSaveRepoAndPreview,
  onDismissHandoffRepoSetup,
  handoffRepoSaving,
}: TranscriptColumnProps) {
  const lastAssistantIndex = React.useMemo(() => {
    for (let i = messages.length - 1; i >= 0; i--) {
      if (messages[i]?.role === "assistant") return i;
    }
    return -1;
  }, [messages]);

  return (
    <div className="h-full min-h-0 flex flex-col overflow-hidden">
      <div className="flex-1 overflow-y-auto p-12 space-y-16 scrollbar-hide relative">
        <div className="max-w-3xl mx-auto space-y-16 pb-32">
          {messages.map((msg, i) => {
            const condensed =
              pendingCursorAgent && msg.role === "assistant" && i === lastAssistantIndex
                ? condensedCursorOperatorBubbleText(msg.content)
                : null;
            const displayContent = condensed ?? msg.content;
            return (
            <div
              key={msg.id}
              className={cn(
                "flex gap-10 group animate-in fade-in slide-in-from-bottom-3 duration-700",
                msg.role === "user" ? "flex-row-reverse" : "",
              )}
            >
              <div
                className={cn(
                  "h-11 w-11 shrink-0 border flex items-center justify-center overflow-hidden transition-all rotate-3 group-hover:rotate-0",
                  msg.role === "assistant"
                    ? "bg-[#FF6B00]/10 border-[#FF6B00]/30 text-[#FF6B00] shadow-[0_0_30px_rgba(255,107,0,0.15)]"
                    : msg.role === "system"
                      ? "bg-white/5 border-white/10 text-white/20"
                      : "bg-white border-white text-black shadow-xl",
                )}
              >
                {msg.role === "assistant" ? (
                  primaryPersona?.avatarUrl ? (
                    <img src={primaryPersona.avatarUrl} alt="" className="h-full w-full object-cover" />
                  ) : (
                    <Sparkles className="h-6 w-6" />
                  )
                ) : msg.role === "system" ? (
                  <Shield className="h-5 w-5" />
                ) : (
                  <span className="text-[11px] font-black uppercase">User</span>
                )}
              </div>

              <div className={cn("flex flex-col gap-4 min-w-0 max-w-2xl", msg.role === "user" ? "items-end" : "items-start")}>
                <div className="flex items-center gap-4 opacity-40 group-hover:opacity-100 transition-opacity">
                  <span className="text-[9px] font-black uppercase tracking-[0.4em] text-white italic">
                    {msg.role === "assistant" && primaryPersona?.name ? primaryPersona.name : msg.role}
                  </span>
                  <span className="text-[8px] font-mono text-white/20">{msg.timestamp}</span>
                </div>
                <div
                  className={cn(
                    "relative p-8 border transition-all duration-300",
                    msg.role === "user"
                      ? "bg-white/[0.04] border-white/10 text-white/90 rounded-2xl rounded-tr-none shadow-2xl"
                      : msg.role === "system"
                        ? "bg-black border-white/10 text-[#FF6B00]/60 font-mono text-[10px] tracking-tight italic rounded-lg"
                        : "bg-[#0a0a0a] border-white/5 text-white/80 group-hover:border-white/20 rounded-2xl rounded-tl-none shadow-lg",
                  )}
                >
                  {msg.role === "assistant" && primaryPersona?.avatarUrl ? (
                    <div className="absolute -right-6 -top-6 opacity-25 pointer-events-none overflow-hidden h-16 w-16 border border-white/10 rounded-2xl rotate-12 group-hover:rotate-0 transition-transform bg-black">
                      <img src={primaryPersona.avatarUrl} alt="" className="w-full h-full object-cover" />
                    </div>
                  ) : null}
                  <span className="text-[13px] font-medium leading-[1.6] uppercase tracking-[0.02em] whitespace-pre-wrap">
                    {displayContent}
                  </span>
                </div>
              </div>
            </div>
            );
          })}

          {cloudHandoffRepoSetup ? (
            <div className="flex gap-10 animate-in fade-in slide-in-from-bottom-3 duration-700">
              <div className="h-11 w-11 shrink-0 border flex items-center justify-center overflow-hidden border-amber-500/40 bg-amber-500/10 text-amber-200">
                <AlertCircle className="h-5 w-5" />
              </div>
              <div className="flex min-w-0 max-w-2xl flex-1 flex-col items-start gap-3">
                <div className="space-y-1">
                  <span className="text-[9px] font-black uppercase tracking-[0.4em] text-amber-200/90">
                    Cloud Agent — repository required
                  </span>
                  <p className="text-[12px] font-medium leading-snug text-white/80">
                    No Cloud Agent repository is configured for this project. Enter the GitHub repository URL, then
                    save to update project metadata and run a mission preview. Launch still needs your token.
                  </p>
                </div>
                <div className="w-full space-y-2 rounded-2xl border border-amber-500/25 bg-amber-950/20 p-4">
                  <p className="text-[9px] font-bold uppercase tracking-widest text-white/45">Repository URL</p>
                  <input
                    type="url"
                    autoComplete="off"
                    value={cloudHandoffRepoSetup.repoInput}
                    onChange={(e) => onHandoffRepoInputChange(e.target.value)}
                    placeholder="https://github.com/org/repo"
                    className="w-full rounded border border-white/15 bg-black/50 px-3 py-2 font-mono text-[11px] text-white"
                  />
                  <p className="text-[9px] text-white/40">
                    Mission (from your message):{" "}
                    <span className="text-white/70">{cloudHandoffRepoSetup.missionText.slice(0, 200)}
                      {cloudHandoffRepoSetup.missionText.length > 200 ? "…" : ""}
                    </span>
                  </p>
                  <div className="flex flex-wrap gap-2 pt-1">
                    <button
                      type="button"
                      disabled={handoffRepoSaving}
                      onClick={onHandoffSaveRepoAndPreview}
                      className="rounded bg-amber-600 px-4 py-2 text-[10px] font-black uppercase tracking-widest text-black disabled:opacity-50"
                    >
                      {handoffRepoSaving ? "Saving…" : "Save repo and preview mission"}
                    </button>
                    <button
                      type="button"
                      disabled={handoffRepoSaving}
                      onClick={onDismissHandoffRepoSetup}
                      className="rounded border border-white/20 px-4 py-2 text-[10px] font-black uppercase tracking-widest text-white/70"
                    >
                      Dismiss
                    </button>
                  </div>
                </div>
              </div>
            </div>
          ) : null}

          {pendingCursorAgent ? (
            <div
              className="flex gap-10 animate-in fade-in slide-in-from-bottom-3 duration-700"
            >
              <div className="h-11 w-11 shrink-0 border flex items-center justify-center overflow-hidden border-cyan-500/40 bg-cyan-500/10 text-cyan-300 shadow-[0_0_30px_rgba(0,229,255,0.12)]">
                <Radar className="h-5 w-5" />
              </div>
              <div className="flex flex-col gap-4 min-w-0 max-w-2xl items-start w-full">
                <div className="flex items-center gap-4 opacity-90">
                  <span className="text-[9px] font-black uppercase tracking-[0.4em] text-cyan-300/90 italic">
                    Cloud Agent — mission card
                  </span>
                  <span className="text-[8px] font-mono text-white/20">
                    {new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}
                  </span>
                </div>
                <div className="w-full space-y-4 rounded-2xl border border-cyan-500/30 bg-cyan-500/[0.07] p-6 shadow-lg">
                  {(() => {
                    const p = pendingCursorAgent;
                    const modeLine =
                      p.cursor_mission_handling === "direct"
                        ? "Cloud Agent · Direct"
                        : "Cloud Agent · Managed by HAM";
                    const task = String(p.cursor_task_prompt ?? "").trim();
                    const titleHint = inferMissionTitleForCard(task);
                    const isStitchedFollowUp = task.includes("Previous work:\n") && task.includes("New instruction:\n");
                    const resolvedRepo = String(p.repository ?? "").trim();
                    const overrideRepo = p.cursor_repository != null ? String(p.cursor_repository).trim() : "";
                    const refVal = p.cursor_ref != null ? String(p.cursor_ref).trim() : "";
                    const dig = String(p.proposal_digest ?? "");
                    return (
                      <div className="space-y-2 border-b border-cyan-500/20 pb-4">
                        <h3 className="text-[11px] font-black uppercase tracking-[0.2em] text-cyan-200/95">{modeLine}</h3>
                        {titleHint ? (
                          <p className="text-[10px] font-bold uppercase tracking-wide text-white/50">
                            Mission title: {titleHint}
                          </p>
                        ) : null}
                        {isStitchedFollowUp ? (
                          <p className="rounded border border-cyan-500/20 bg-black/30 px-2 py-1.5 text-[9px] leading-snug text-cyan-200/80">
                            Follow-up: <span className="text-white/70">this preview starts a new Cloud Agent launch with prior
                            context stitched in. It does not message the previous agent.</span>
                          </p>
                        ) : null}
                        <dl className="space-y-1.5 text-[11px] text-white/85">
                          <div className="flex flex-wrap gap-x-2 gap-y-0.5">
                            <dt className="shrink-0 text-[9px] font-bold uppercase tracking-widest text-white/45">
                              Project
                            </dt>
                            <dd className="min-w-0 break-words font-medium">
                              {activeProjectName || "—"}
                            </dd>
                          </div>
                          <div className="flex flex-wrap gap-x-2 gap-y-0.5">
                            <dt className="shrink-0 text-[9px] font-bold uppercase tracking-widest text-white/45">
                              Task
                            </dt>
                            <dd className="min-w-0 line-clamp-3 break-words font-medium" title={task}>
                              {task || "—"}
                            </dd>
                          </div>
                          <div className="flex flex-wrap gap-x-2 gap-y-0.5">
                            <dt className="shrink-0 text-[9px] font-bold uppercase tracking-widest text-white/45">
                              Repository
                            </dt>
                            <dd className="min-w-0 break-all font-mono text-[10px] text-white/80">
                              {resolvedRepo || "—"}
                              {overrideRepo && overrideRepo !== resolvedRepo ? (
                                <span className="block text-[9px] text-amber-400/80 normal-case">
                                  Override: {overrideRepo}
                                </span>
                              ) : null}
                            </dd>
                          </div>
                          <div className="flex flex-wrap gap-x-2 gap-y-0.5">
                            <dt className="shrink-0 text-[9px] font-bold uppercase tracking-widest text-white/45">Ref</dt>
                            <dd className="min-w-0 break-words font-mono text-[10px] text-white/80">
                              {refVal || "default branch"}
                            </dd>
                          </div>
                        </dl>
                        <p className="pt-1 text-[9px] font-mono text-white/35" title={dig || undefined}>
                          Digest: {shortDigest(dig) || "—"}
                        </p>
                      </div>
                    );
                  })()}
                  <div>
                    <p className="text-[9px] font-bold uppercase tracking-widest text-white/45 mb-2">Server detail</p>
                    <div className="whitespace-pre-wrap text-[12px] font-medium leading-[1.6] uppercase tracking-[0.02em] text-white/80 max-h-[min(50vh,320px)] overflow-y-auto">
                      {String(pendingCursorAgent.summary_preview ?? "")}
                    </div>
                  </div>
                  <p className="text-[9px] text-white/40">
                    Paste <span className="font-mono">HAM_CURSOR_AGENT_LAUNCH_TOKEN</span> to confirm launch. No
                    auto-launch.
                  </p>
                  <input
                    type="password"
                    autoComplete="off"
                    placeholder="HAM_CURSOR_AGENT_LAUNCH_TOKEN"
                    value={operatorCursorAgentToken}
                    onChange={(e) => onOperatorCursorAgentTokenChange(e.target.value)}
                    className="w-full rounded border border-white/15 bg-black/50 px-3 py-2 font-mono text-[11px] text-white"
                  />
                  <div className="flex flex-wrap gap-2">
                    <button
                      type="button"
                      disabled={cursorAgentActionsDisabled}
                      onClick={onCursorAgentLaunch}
                      className="rounded bg-cyan-600 px-4 py-2 text-[10px] font-black uppercase tracking-widest text-white disabled:opacity-50"
                    >
                      Launch
                    </button>
                    <button
                      type="button"
                      disabled={cursorAgentActionsDisabled}
                      onClick={onDismissCursorPreview}
                      className="rounded border border-white/20 px-4 py-2 text-[10px] font-black uppercase tracking-widest text-white/70"
                    >
                      Dismiss
                    </button>
                  </div>
                </div>
              </div>
            </div>
          ) : null}
        </div>
      </div>
    </div>
  );
}

function ChatPageInner({
  getClerkSessionToken,
}: {
  getClerkSessionToken: () => Promise<string | null>;
}) {
  const clerkEnabled = Boolean(
    (import.meta.env.VITE_CLERK_PUBLISHABLE_KEY as string | undefined)?.trim(),
  );
  const navigate = useNavigate();
  const { agents, selectedAgentId } = useAgent();
  const { isControlPanelOpen, setIsControlPanelOpen } = useWorkspace();
  const selectedAgent = agents.find(a => a.id === selectedAgentId) || agents[0];

  const [messages, setMessages] = React.useState<ChatRow[]>([]);
  const [input, setInput] = React.useState("");
  const [sessionId, setSessionId] = React.useState<string | null>(() => {
    try {
      return localStorage.getItem(ACTIVE_SESSION_KEY) || null;
    } catch {
      return null;
    }
  });
  const [sending, setSending] = React.useState(false);
  const [chatError, setChatError] = React.useState<string | null>(null);

  const [catalog, setCatalog] = React.useState<ModelCatalogPayload>(CLIENT_MODEL_CATALOG_FALLBACK);
  const [catalogLoading, setCatalogLoading] = React.useState(true);
  const [workbenchMode, setWorkbenchMode] = React.useState<WorkbenchMode>("agent");
  const [modelId, setModelId] = React.useState<string | null>(null);
  /** Per-request model_id is OpenRouter-only; http/mock would 422 if we forwarded a tier id. */
  const chatModelIdForApi = catalog.gateway_mode === "openrouter" ? modelId : null;
  const [maxMode, setMaxMode] = React.useState(false);
  const [worker, setWorker] = React.useState("builder");
  const [projectId, setProjectId] = React.useState<string | null>(null);
  const [activeAgentNote, setActiveAgentNote] = React.useState<string | null>(null);
  const SETTINGS_OP_KEY = "ham_operator_settings_token";
  const LAUNCH_OP_KEY = "ham_operator_launch_token";
  const CURSOR_AGENT_OP_KEY = "ham_cursor_agent_launch_token";
  const [operatorSettingsToken, setOperatorSettingsToken] = React.useState(() =>
    typeof sessionStorage !== "undefined"
      ? sessionStorage.getItem(SETTINGS_OP_KEY) ?? ""
      : "",
  );
  const [operatorLaunchToken, setOperatorLaunchToken] = React.useState(() =>
    typeof sessionStorage !== "undefined" ? sessionStorage.getItem(LAUNCH_OP_KEY) ?? "" : "",
  );
  const [operatorCursorAgentToken, setOperatorCursorAgentToken] = React.useState(() =>
    typeof sessionStorage !== "undefined" ? sessionStorage.getItem(CURSOR_AGENT_OP_KEY) ?? "" : "",
  );
  const [pendingApply, setPendingApply] = React.useState<Record<string, unknown> | null>(
    null,
  );
  const [pendingLaunch, setPendingLaunch] = React.useState<Record<string, unknown> | null>(
    null,
  );
  const [pendingRegister, setPendingRegister] = React.useState<Record<
    string,
    unknown
  > | null>(null);
  const [pendingCursorAgent, setPendingCursorAgent] = React.useState<Record<string, unknown> | null>(
    null,
  );
  /** Chat-native handoff: need repo before preview (PATCH metadata + preview). */
  const [cloudHandoffRepoSetup, setCloudHandoffRepoSetup] = React.useState<{
    missionText: string;
    repoInput: string;
  } | null>(null);
  const [handoffRepoSaving, setHandoffRepoSaving] = React.useState(false);
  /** Optional overrides for `cursor_agent_preview` — not the default path (use main input for the task). */
  const [caRepo, setCaRepo] = React.useState("");
  const [caRef, setCaRef] = React.useState("");
  const [caMission, setCaMission] = React.useState<"direct" | "managed">("managed");
  /** When a prior managed mission exists, stitch summary + new instruction into the next preview (new launch only). */
  const [cloudFollowUpMode, setCloudFollowUpMode] = React.useState<"continue" | "fresh">("continue");
  const [cloudAgentOptionsOpen, setCloudAgentOptionsOpen] = React.useState(false);
  /** Collapses AGENT/MODEL/BUILDER/CLOUD strip + Cloud Agent options (session-only). */
  const [showAgentControls, setShowAgentControls] = React.useState(false);
  const [composerAttachment, setComposerAttachment] = React.useState<ComposerAttachment | null>(null);
  const composerFileInputRef = React.useRef<HTMLInputElement>(null);
  /** OpenAI transcription in flight after VoiceMessageInput stop. */
  const [voiceTranscribing, setVoiceTranscribing] = React.useState(false);
  /** Option A: once user edits repo/ref, autofill must not clobber. */
  const cloudTargetTouchedRef = React.useRef({ repo: false, ref: false });
  /** Primary HAM profile from Agent Builder (avatar + name in transcript). */
  const [primaryPersona, setPrimaryPersona] = React.useState<{
    name: string;
    avatarUrl: string | null;
  } | null>(null);

  const [uplinkId, setUplinkId] = React.useState<UplinkId>("factory_ai");
  const [viewMode, setViewMode] = React.useState<ChatViewMode>("chat");
  const [layoutMenuOpen, setLayoutMenuOpen] = React.useState(false);
  const layoutMenuRef = React.useRef<HTMLDivElement>(null);
  const [projectsOpen, setProjectsOpen] = React.useState(false);
  const [mountRepo, setMountRepo] = React.useState("");
  const [mountRef, setMountRef] = React.useState("");
  const [paneEmbedUrl, setPaneEmbedUrl] = React.useState("");
  const [requestedTabId, setRequestedTabId] = React.useState<WarRoomTabId | undefined>(undefined);
  const [requestedTabNonce, setRequestedTabNonce] = React.useState(0);
  const [browserOnly, setBrowserOnly] = React.useState(false);
  /** Cursor Cloud Agent id for War Room / Cloud Agent uplink (proxied via Ham API). */
  const [activeCloudAgentId, setActiveCloudAgentId] = React.useState<string | null>(null);
  const [cloudMissionHandling, setCloudMissionHandling] = React.useState<CloudMissionHandling>("direct");
  /** Id last set by `activateCloudMission` or restored on load — not live typing in Projects. */
  const lastCommittedCloudAgentIdRef = React.useRef<string | null>(null);
  const [recentMissions, setRecentMissions] = React.useState<RecentMission[]>([]);
  const [hamProjects, setHamProjects] = React.useState<ProjectRecord[]>([]);
  const [projectsLoading, setProjectsLoading] = React.useState(false);
  const [warBlink, setWarBlink] = React.useState(true);
  const [reduceMotion, setReduceMotion] = React.useState(false);
  const [cloudLaunchOpen, setCloudLaunchOpen] = React.useState(false);
  /** Latest gates for `processManagedAgentPollForCompletion` (read each call, no stale closure). */
  const managedCompletionGatesRef = React.useRef({
    uplinkId: "factory_ai" as UplinkId,
    cloudMissionHandling: "direct" as CloudMissionHandling,
    activeCloudAgentId: null as string | null,
  });

  const [deployHookConfigured, setDeployHookConfigured] = React.useState<boolean | null>(null);
  const [deployHookVercelMapping, setDeployHookVercelMapping] = React.useState<VercelHookMapping | null>(null);
  const [deployUserResult, setDeployUserResult] = React.useState<"none" | "accepted" | "failed">("none");
  const [deployTriggering, setDeployTriggering] = React.useState(false);
  const [deployResultMessage, setDeployResultMessage] = React.useState<string | null>(null);
  const [deployApprovalStatus, setDeployApprovalStatus] = React.useState<ManagedDeployApprovalStatusPayload | null>(null);
  const [deployApprovalLoading, setDeployApprovalLoading] = React.useState(false);
  const lastDeployHandoffAgentRef = React.useRef<string | null | undefined>(undefined);

  /** Chat history sidebar */
  const [historyOpen, setHistoryOpen] = React.useState(false);
  const [historySessions, setHistorySessions] = React.useState<ChatSessionSummary[]>([]);
  const [historyLoading, setHistoryLoading] = React.useState(false);
  const [historySearchQuery, setHistorySearchQuery] = React.useState("");
  const [serverMissions, setServerMissions] = React.useState<ManagedMissionRow[]>([]);
  const [serverMissionsLoading, setServerMissionsLoading] = React.useState(false);

  /** Dedupe recent missions: same id → newest timestamp wins (single list order: newest first after push). */
  const pushRecentMission = React.useCallback((id: string, label?: string) => {
    const trimmed = id.trim();
    if (!trimmed) return;
    setRecentMissions((prev) => {
      const filtered = prev.filter((m) => m.id !== trimmed);
      const entry: RecentMission = { id: trimmed, t: Date.now(), ...(label ? { label } : {}) };
      const next = [entry, ...filtered].slice(0, 24);
      saveRecentMissions(next);
      return next;
    });
  }, []);

  const removeRecentMission = React.useCallback((id: string) => {
    setRecentMissions((prev) => {
      const next = prev.filter((m) => m.id !== id);
      saveRecentMissions(next);
      return next;
    });
  }, []);

  /** SSOT for `activeCloudAgentId` without mutating recent list (typing in Projects field). */
  const setActiveCloudAgentIdLive = React.useCallback((id: string | null) => {
    const trimmed = id?.trim() || null;
    setActiveCloudAgentId(trimmed);
    if (!trimmed) {
      setCloudMissionHandling("direct");
      lastCommittedCloudAgentIdRef.current = null;
      try {
        localStorage.removeItem(CLOUD_MISSION_HANDLING_KEY);
      } catch {
        /* ignore */
      }
    }
    try {
      if (trimmed) localStorage.setItem(ACTIVE_CLOUD_AGENT_KEY, trimmed);
      else localStorage.removeItem(ACTIVE_CLOUD_AGENT_KEY);
    } catch {
      /* ignore */
    }
  }, []);

  /**
   * Single activation path for an established mission id: state + localStorage + recent (dedupe, newest wins).
   * Use for Launch modal, Projects “Use”, and committing the mission field (blur).
   * `mission_handling` from the modal is always applied; if omitted, preserve mode only when the id matches the
   * last committed id (avoids clobbering Managed on blur, and resets to Direct for new ids without the modal).
   */
  const activateCloudMission = React.useCallback(
    (
      id: string | null,
      opts?: {
        label?: string;
        mission_handling?: CloudMissionHandling;
        /**
         * When present and the resulting state is **Cloud + Managed**, the workbench enters Split and opens the
         * right Cloud Agent tab (Tracker vs Transcript) — not used for localStorage-only restores.
         * `assumeCloudUplink`: set when switching uplink in the same tick (e.g. History → open mission) so Split
         * still opens before `uplinkId` state has committed.
         */
        managedSplit?:
          | { kind: "new_launch" }
          | { kind: "existing"; assumeCloudUplink?: boolean; openTab?: WarRoomTabId };
      },
    ) => {
      const trimmed = id?.trim() || null;
      setActiveCloudAgentId(trimmed);

      let nextHandling: CloudMissionHandling;
      if (!trimmed) {
        nextHandling = "direct";
      } else if (opts?.mission_handling !== undefined) {
        nextHandling = opts.mission_handling;
      } else {
        const committed = lastCommittedCloudAgentIdRef.current?.trim() || null;
        nextHandling =
          committed && committed === trimmed ? cloudMissionHandling : "direct";
      }
      setCloudMissionHandling(nextHandling);
      lastCommittedCloudAgentIdRef.current = trimmed;

      try {
        if (trimmed) {
          localStorage.setItem(ACTIVE_CLOUD_AGENT_KEY, trimmed);
          localStorage.setItem(CLOUD_MISSION_HANDLING_KEY, nextHandling);
          pushRecentMission(trimmed, opts?.label);
        } else {
          localStorage.removeItem(ACTIVE_CLOUD_AGENT_KEY);
          localStorage.removeItem(CLOUD_MISSION_HANDLING_KEY);
        }
      } catch {
        /* ignore */
      }

      const assumeCloudUplink =
        opts?.managedSplit?.kind === "existing" && opts.managedSplit.assumeCloudUplink === true;
      const cloudOkForSplit = uplinkId === "cloud_agent" || assumeCloudUplink;
      if (opts?.managedSplit && cloudOkForSplit && trimmed && nextHandling === "managed") {
        setViewMode("split");
        const ms = opts.managedSplit;
        let nextTab: WarRoomTabId =
          ms.kind === "new_launch" ? "tracker" : (ms.kind === "existing" && ms.openTab ? ms.openTab : "transcript");
        setRequestedTabId(nextTab);
        setRequestedTabNonce((n) => n + 1);
      }
    },
    [pushRecentMission, cloudMissionHandling, uplinkId],
  );

  const openServerManagedMission = React.useCallback(
    (agentId: string) => {
      const trimmed = agentId.trim();
      if (!trimmed) return;
      setUplinkId("cloud_agent");
      activateCloudMission(trimmed, {
        mission_handling: "managed",
        managedSplit: { kind: "existing", assumeCloudUplink: true, openTab: "overview" },
      });
      setHistoryOpen(false);
    },
    [activateCloudMission],
  );

  React.useEffect(() => {
    if (!historyOpen) return;
    let cancelled = false;
    setServerMissionsLoading(true);
    void fetchManagedMissionsList(40).then((rows) => {
      if (!cancelled) setServerMissions(rows);
    }).finally(() => {
      if (!cancelled) setServerMissionsLoading(false);
    });
    return () => {
      cancelled = true;
    };
  }, [historyOpen]);

  React.useEffect(() => {
    const onDocMouseDown = (e: MouseEvent) => {
      if (layoutMenuRef.current?.contains(e.target as Node)) return;
      setLayoutMenuOpen(false);
    };
    document.addEventListener("mousedown", onDocMouseDown);
    return () => document.removeEventListener("mousedown", onDocMouseDown);
  }, []);

  React.useEffect(() => {
    let initialRecent = loadRecentMissions();
    try {
      const m = localStorage.getItem(MOUNT_STORAGE_KEY);
      if (m) {
        const o = JSON.parse(m) as { repository?: string; ref?: string };
        if (typeof o.repository === "string") setMountRepo(o.repository);
        if (typeof o.ref === "string") setMountRef(o.ref);
      }
    } catch {
      /* ignore */
    }
    let aid: string | null = null;
    try {
      aid = localStorage.getItem(ACTIVE_CLOUD_AGENT_KEY)?.trim() || null;
      setActiveCloudAgentId(aid);
      if (aid) {
        setCloudMissionHandling(parseStoredMissionHandling(localStorage.getItem(CLOUD_MISSION_HANDLING_KEY)));
        lastCommittedCloudAgentIdRef.current = aid;
      } else {
        setCloudMissionHandling("direct");
        lastCommittedCloudAgentIdRef.current = null;
      }
    } catch {
      /* ignore */
    }
    if (aid && !initialRecent.some((m) => m.id === aid)) {
      initialRecent = [{ id: aid, t: Date.now() }, ...initialRecent.filter((m) => m.id !== aid)].slice(0, 24);
      saveRecentMissions(initialRecent);
    }
    setRecentMissions(initialRecent);
  }, []);

  const mountDefaultsForLaunch = React.useMemo(() => {
    const r = mountRepo.trim();
    if (!r) return undefined;
    return { repository: r, ref: mountRef.trim() };
  }, [mountRepo, mountRef]);

  React.useEffect(() => {
    const mq = window.matchMedia("(prefers-reduced-motion: reduce)");
    setReduceMotion(mq.matches);
    const fn = () => setReduceMotion(mq.matches);
    mq.addEventListener("change", fn);
    return () => mq.removeEventListener("change", fn);
  }, []);

  React.useEffect(() => {
    if (viewMode !== "war_room" || reduceMotion) return;
    const id = window.setInterval(() => setWarBlink((b) => !b), 1000);
    return () => window.clearInterval(id);
  }, [viewMode, reduceMotion]);

  React.useEffect(() => {
    if (!projectsOpen) return;
    let cancelled = false;
    setProjectsLoading(true);
    void listHamProjects()
      .then((r) => {
        if (!cancelled) {
          setHamProjects(r.projects);
        }
      })
      .catch(() => {
        if (!cancelled) setHamProjects([]);
      })
      .finally(() => {
        if (!cancelled) setProjectsLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [projectsOpen]);

  const persistProjectMount = React.useCallback(() => {
    try {
      localStorage.setItem(
        MOUNT_STORAGE_KEY,
        JSON.stringify({ repository: mountRepo.trim(), ref: mountRef.trim() }),
      );
    } catch {
      /* ignore */
    }
  }, [mountRepo, mountRef]);

  const closeProjectsPanel = React.useCallback(() => {
    persistProjectMount();
    setProjectsOpen(false);
  }, [persistProjectMount]);

  const onUpdateProjectDefaultPolicy = React.useCallback(
    async (projectId: string, policy: ProjectDefaultDeployPolicy) => {
      try {
        const updated = await patchHamProjectMetadata(projectId, {
          [PROJECT_DEFAULT_DEPLOY_APPROVAL_KEY]: policy,
        });
        setHamProjects((prev) => prev.map((p) => (p.id === projectId ? updated : p)));
        toast.success("Saved project default deploy policy");
      } catch (e: unknown) {
        const msg = e instanceof Error ? e.message : "Update failed";
        toast.error(msg);
        throw e;
      }
    },
    [],
  );

  React.useEffect(() => {
    let cancelled = false;
    setCatalogLoading(true);
    void fetchModelsCatalog()
      .then((c) => {
        if (!cancelled) setCatalog(c);
      })
      .catch(() => {
        if (!cancelled) setCatalog(CLIENT_MODEL_CATALOG_FALLBACK);
      })
      .finally(() => {
        if (!cancelled) setCatalogLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  /** HTTP Hermes chat ignores `cursor:*` picks; clear stale selection so the strip does not show Opus. */
  React.useEffect(() => {
    if (catalog.gateway_mode !== "http") return;
    setModelId((mid) => (mid?.startsWith("cursor:") ? null : mid));
  }, [catalog.gateway_mode]);

  React.useEffect(() => {
    let cancelled = false;
    void (async () => {
      try {
        const ctx = await fetchContextEngine();
        const id = await ensureProjectIdForWorkspaceRoot(ctx.cwd);
        if (!cancelled) setProjectId(id);
      } catch {
        if (!cancelled) setProjectId(null);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  /** On project change: clear target overrides so autofill can apply for the new project. */
  React.useEffect(() => {
    setCaRepo("");
    setCaRef("");
    cloudTargetTouchedRef.current = { repo: false, ref: false };
  }, [projectId]);

  /** Option A: autofill metadata repo and optional ref from mount when empty and not user-touched. */
  React.useEffect(() => {
    if (!projectId) return;
    const rec = hamProjects.find((p) => p.id === projectId);
    const metaRepo = getCursorCloudRepository(rec?.metadata) ?? "";
    const mref = mountRef.trim();
    setCaRepo((r) => {
      if (cloudTargetTouchedRef.current.repo) return r;
      if (r.trim()) return r;
      return metaRepo || r;
    });
    setCaRef((r) => {
      if (cloudTargetTouchedRef.current.ref) return r;
      if (r.trim()) return r;
      return mref || r;
    });
  }, [projectId, hamProjects, mountRef]);

  const activeProjectName = React.useMemo(
    () => getActiveProjectName(hamProjects, projectId),
    [hamProjects, projectId],
  );

  const showCloudAgentMissingRepoHint = Boolean(
    projectId &&
      !getCursorCloudRepository(hamProjects.find((p) => p.id === projectId)?.metadata) &&
      !caRepo.trim(),
  );

  React.useEffect(() => {
    let cancelled = false;
    if (!projectId) {
      setPrimaryPersona(null);
      return;
    }
    void (async () => {
      try {
        const cfg = await fetchProjectAgents(projectId);
        const prof = cfg.profiles.find((p) => p.id === cfg.primary_agent_id);
        if (cancelled) return;
        if (!prof) {
          setPrimaryPersona(null);
          return;
        }
        const url = prof.avatar_url?.trim() || null;
        setPrimaryPersona({ name: prof.name, avatarUrl: url });
      } catch {
        if (!cancelled) setPrimaryPersona(null);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [projectId]);

  React.useEffect(() => {
    if (import.meta.env.DEV) return;
    try {
      getApiBase();
    } catch {
      toast.error(
        "Chat needs a Ham API URL. For the web build, set VITE_HAM_API_BASE on your host. For the desktop app, set HAM_DESKTOP_API_BASE (or ham-desktop-config.json) — see desktop/README.md.",
        { duration: 12_000, id: "ham-api-base-missing" },
      );
    }
  }, []);

  // Persist sessionId to localStorage whenever it changes.
  React.useEffect(() => {
    try {
      if (sessionId) {
        localStorage.setItem(ACTIVE_SESSION_KEY, sessionId);
      } else {
        localStorage.removeItem(ACTIVE_SESSION_KEY);
      }
    } catch {
      /* ignore */
    }
  }, [sessionId]);

  // On mount: if we have a saved sessionId, reload its history from the backend.
  React.useEffect(() => {
    if (!sessionId) return;
    let cancelled = false;
    void (async () => {
      try {
        const detail = await fetchChatSession(sessionId);
        if (cancelled) return;
        const ts = () =>
          new Date().toLocaleTimeString([], {
            hour12: false,
            hour: "2-digit",
            minute: "2-digit",
            second: "2-digit",
          });
        setMessages(
          detail.messages.map((m, i) => ({
            id: `${sessionId}-restored-${i}-${m.role}`,
            role: m.role,
            content: m.content,
            timestamp: ts(),
          })),
        );
        setPendingCursorAgent(loadPendingCursorAgentSessionSnapshot(sessionId));
      } catch {
        // Session not found on backend — stale localStorage. Clear and start fresh.
        setSessionId(null);
      }
    })();
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Fetch chat history list when the history sidebar opens.
  React.useEffect(() => {
    if (!historyOpen) return;
    let cancelled = false;
    setHistoryLoading(true);
    void fetchChatSessions(50, 0)
      .then((r) => {
        if (!cancelled) setHistorySessions(r.sessions);
      })
      .catch(() => {
        if (!cancelled) setHistorySessions([]);
      })
      .finally(() => {
        if (!cancelled) setHistoryLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [historyOpen]);

  const dismissCursorPreview = React.useCallback(() => {
    if (sessionId) savePendingCursorAgentSessionSnapshot(sessionId, null);
    setPendingCursorAgent(null);
  }, [sessionId]);

  /** Start a brand-new chat session. */
  const startNewChat = React.useCallback(() => {
    if (sessionId) savePendingCursorAgentSessionSnapshot(sessionId, null);
    setSessionId(null);
    setMessages([]);
    setPendingCursorAgent(null);
    setChatError(null);
    setHistoryOpen(false);
  }, [sessionId]);

  /** Load a past session into the transcript. */
  const loadSession = React.useCallback(async (sid: string) => {
    try {
      const detail = await fetchChatSession(sid);
      const ts = () =>
        new Date().toLocaleTimeString([], {
          hour12: false,
          hour: "2-digit",
          minute: "2-digit",
          second: "2-digit",
        });
      setSessionId(sid);
      setMessages(
        detail.messages.map((m, i) => ({
          id: `${sid}-loaded-${i}-${m.role}`,
          role: m.role,
          content: m.content,
          timestamp: ts(),
        })),
      );
      setPendingCursorAgent(loadPendingCursorAgentSessionSnapshot(sid));
      setChatError(null);
      setHistoryOpen(false);
    } catch {
      toast.error("Failed to load chat session.");
    }
  }, []);

  const timeStr = () =>
    new Date().toLocaleTimeString([], {
      hour12: false,
      hour: "2-digit",
      minute: "2-digit",
      second: "2-digit",
    });

  const processManagedAgentPollForCompletion = React.useCallback(
    (agent: Record<string, unknown>, conversation: unknown) => {
      const g = managedCompletionGatesRef.current;
      if (g.uplinkId !== "cloud_agent" || g.cloudMissionHandling !== "managed") return;
      const aid = g.activeCloudAgentId?.trim();
      if (!aid) return;
      if (!isCloudAgentTerminal(agent)) return;
      const map = loadManagedCompletionMap();
      if (map[aid] !== undefined) return;
      const sig = completionInjectionSignature(agent, aid);
      map[aid] = sig;
      saveManagedCompletionMap(map);
      const content = buildManagedCompletionMessage(agent, conversation);
      const t = new Date().toLocaleTimeString([], {
        hour12: false,
        hour: "2-digit",
        minute: "2-digit",
        second: "2-digit",
      });
      setMessages((prev) => [
        ...prev,
        {
          id: `ham-managed-cloud-completion-${aid}-${Date.now()}`,
          role: "system",
          content,
          timestamp: t,
        },
      ]);
    },
    [],
  );

  const processManagedAgentReviewForChat = React.useCallback(
    (agent: Record<string, unknown>, _conversation: unknown, review: ManagedMissionReview) => {
      const g = managedCompletionGatesRef.current;
      if (g.uplinkId !== "cloud_agent" || g.cloudMissionHandling !== "managed") return;
      const aid = g.activeCloudAgentId?.trim();
      if (!aid) return;
      if (!isCloudAgentTerminal(agent) || !shouldEmitReviewChatLine(review)) return;
      const done = buildManagedCompletionMessage(agent, _conversation);
      const rline = buildManagedReviewChatMessage(review);
      if (rline.trim() === done.trim()) return;
      const map = loadManagedReviewChatMap();
      if (map[aid] !== undefined) return;
      const sig = reviewChatInjectionSignature(aid, review, agent);
      map[aid] = sig;
      saveManagedReviewChatMap(map);
      const t = new Date().toLocaleTimeString([], {
        hour12: false,
        hour: "2-digit",
        minute: "2-digit",
        second: "2-digit",
      });
      setMessages((prev) => [
        ...prev,
        {
          id: `ham-managed-cloud-review-${aid}-${Date.now()}`,
          role: "system",
          content: rline,
          timestamp: t,
        },
      ]);
    },
    [],
  );

  const processManagedDeployForChat = React.useCallback(
    (r: ManagedDeployHookResult, aid: string) => {
      const g = managedCompletionGatesRef.current;
      if (g.uplinkId !== "cloud_agent" || g.cloudMissionHandling !== "managed") return;
      if (g.activeCloudAgentId?.trim() !== aid) return;
      const map = loadManagedDeployChatMap();
      if (map[aid] !== undefined) return;
      map[aid] = "1";
      saveManagedDeployChatMap(map);
      const t = new Date().toLocaleTimeString([], {
        hour12: false,
        hour: "2-digit",
        minute: "2-digit",
        second: "2-digit",
      });
      setMessages((prev) => [
        ...prev,
        {
          id: `ham-managed-deploy-handoff-${aid}-${Date.now()}`,
          role: "system",
          content: `[HAM] Deploy handoff: ${r.message}`,
          timestamp: t,
        },
      ]);
    },
    [],
  );

  React.useEffect(() => {
    if (uplinkId !== "cloud_agent" || cloudMissionHandling !== "managed") {
      try {
        localStorage.removeItem(MANAGED_COMPLETION_STORAGE_KEY);
        localStorage.removeItem(MANAGED_REVIEW_CHAT_STORAGE_KEY);
        localStorage.removeItem(MANAGED_DEPLOY_CHAT_STORAGE_KEY);
      } catch {
        /* ignore */
      }
    }
  }, [uplinkId, cloudMissionHandling]);

  const managedPollEnabled =
    uplinkId === "cloud_agent" && cloudMissionHandling === "managed" && Boolean(activeCloudAgentId?.trim());

  const managedCloudPoll = useManagedCloudAgentPoll({
    enabled: managedPollEnabled,
    agentId: activeCloudAgentId?.trim() ?? "",
    onAfterSuccess: processManagedAgentPollForCompletion,
    onTerminalReviewForChat: processManagedAgentReviewForChat,
  });

  React.useEffect(() => {
    const aid = activeCloudAgentId?.trim() ?? null;
    if (lastDeployHandoffAgentRef.current === undefined) {
      lastDeployHandoffAgentRef.current = aid;
      return;
    }
    if (lastDeployHandoffAgentRef.current === aid) return;
    lastDeployHandoffAgentRef.current = aid;
    setDeployUserResult("none");
    setDeployResultMessage(null);
    setDeployTriggering(false);
    setDeployApprovalStatus(null);
  }, [activeCloudAgentId]);

  React.useEffect(() => {
    if (uplinkId !== "cloud_agent" || cloudMissionHandling !== "managed" || !activeCloudAgentId?.trim()) {
      setDeployHookConfigured(null);
      setDeployHookVercelMapping(null);
      return;
    }
    let cancelled = false;
    const aid = activeCloudAgentId.trim();
    void fetchManagedDeployHookStatus(aid).then((p) => {
      if (!cancelled) {
        setDeployHookConfigured(p.configured);
        setDeployHookVercelMapping(p.vercel_mapping ?? null);
      }
    });
    return () => {
      cancelled = true;
    };
  }, [uplinkId, cloudMissionHandling, activeCloudAgentId]);

  const refreshDeployApproval = React.useCallback(async () => {
    if (uplinkId !== "cloud_agent" || cloudMissionHandling !== "managed") {
      setDeployApprovalStatus(null);
      return;
    }
    const aid = activeCloudAgentId?.trim();
    if (!aid) {
      setDeployApprovalStatus(null);
      return;
    }
    setDeployApprovalLoading(true);
    try {
      const s = await fetchManagedDeployApprovalStatus(aid);
      setDeployApprovalStatus(s);
    } catch {
      setDeployApprovalStatus(null);
    } finally {
      setDeployApprovalLoading(false);
    }
  }, [uplinkId, cloudMissionHandling, activeCloudAgentId]);

  const postDeployApproval = React.useCallback(
    async (args: {
      state: "approved" | "denied";
      note?: string;
      override?: boolean;
      override_justification?: string | null;
    }) => {
      const aid = activeCloudAgentId?.trim();
      if (!aid || uplinkId !== "cloud_agent" || cloudMissionHandling !== "managed") return;
      await postManagedDeployApprovalDecision({
        agent_id: aid,
        source: "operator_ui",
        state: args.state,
        note: args.note,
        override: args.override,
        override_justification: args.override_justification,
      });
      await refreshDeployApproval();
    },
    [activeCloudAgentId, uplinkId, cloudMissionHandling, refreshDeployApproval],
  );

  React.useEffect(() => {
    if (uplinkId !== "cloud_agent" || cloudMissionHandling !== "managed" || !activeCloudAgentId?.trim()) {
      setDeployApprovalStatus(null);
      return;
    }
    void refreshDeployApproval();
  }, [uplinkId, cloudMissionHandling, activeCloudAgentId, refreshDeployApproval]);

  const triggerManagedDeploy = React.useCallback(async () => {
    const aid = activeCloudAgentId?.trim();
    if (!aid) return;
    if (uplinkId !== "cloud_agent" || cloudMissionHandling !== "managed") return;
    if (!managedCloudPoll.lastDeployReadiness?.ready) return;
    if (deployHookConfigured === false) return;
    if (deployApprovalStatus?.policy === "hard" && !deployApprovalStatus.deploy_hook_would_allow) {
      setDeployUserResult("failed");
      setDeployResultMessage("Deploy is blocked: managed deploy approval policy is hard. Approve in Overview (right pane) first.");
      return;
    }
    setDeployTriggering(true);
    setDeployResultMessage(null);
    try {
      const r = await postManagedDeployHook(aid);
      setDeployResultMessage(r.message);
      if (r.outcome === "not_configured" || r.outcome === "approval_required" || !r.ok) {
        setDeployUserResult("failed");
      } else {
        setDeployUserResult("accepted");
      }
      if (r.ok) {
        void refreshDeployApproval();
      }
      processManagedDeployForChat(r, aid);
    } catch (e: unknown) {
      setDeployUserResult("failed");
      setDeployResultMessage(e instanceof Error ? e.message : "Request failed");
    } finally {
      setDeployTriggering(false);
    }
  }, [
    activeCloudAgentId,
    uplinkId,
    cloudMissionHandling,
    managedCloudPoll.lastDeployReadiness,
    deployHookConfigured,
    deployApprovalStatus,
    processManagedDeployForChat,
    refreshDeployApproval,
  ]);

  const deployHandoffState = React.useMemo((): ManagedDeployHandoffState => {
    if (deployTriggering) return "triggering";
    if (deployUserResult === "accepted") return "hook_accepted";
    if (deployUserResult === "failed") return "hook_failed";
    if (deployHookConfigured === null) return "idle";
    if (deployHookConfigured === false) return "hook_not_configured";
    const r = managedCloudPoll.lastDeployReadiness;
    if (!r) return "idle";
    if (!r.ready) return "not_ready";
    return "ready";
  }, [
    deployTriggering,
    deployUserResult,
    deployHookConfigured,
    managedCloudPoll.lastDeployReadiness,
  ]);

  const managedCloudAgentContextValue = React.useMemo(
    () => ({
      activeCloudAgentId,
      cloudMissionHandling,
      lastSnapshot: managedCloudPoll.lastSnapshot,
      lastReview: managedCloudPoll.lastReview,
      lastDeployReadiness: managedCloudPoll.lastDeployReadiness,
      lastUpdated: managedCloudPoll.lastUpdated,
      pollError: managedCloudPoll.pollError,
      pollPending: managedCloudPoll.pollPending,
      refresh: managedCloudPoll.refresh,
      deployHookConfigured,
      deployHookVercelMapping,
      deployHandoffState,
      deployHandoffMessage: deployResultMessage,
      triggerManagedDeploy:
        uplinkId === "cloud_agent" && cloudMissionHandling === "managed" ? triggerManagedDeploy : null,
      deployApprovalStatus,
      deployApprovalLoading,
      refreshDeployApproval,
      postDeployApproval,
    }),
    [
      activeCloudAgentId,
      cloudMissionHandling,
      managedCloudPoll.lastSnapshot,
      managedCloudPoll.lastReview,
      managedCloudPoll.lastDeployReadiness,
      managedCloudPoll.lastUpdated,
      managedCloudPoll.pollError,
      managedCloudPoll.pollPending,
      managedCloudPoll.refresh,
      deployHookConfigured,
      deployHookVercelMapping,
      deployHandoffState,
      deployResultMessage,
      uplinkId,
      triggerManagedDeploy,
      deployApprovalStatus,
      deployApprovalLoading,
      refreshDeployApproval,
      postDeployApproval,
    ],
  );

  const hasCloudFollowUpContext = React.useMemo(
    () =>
      uplinkId === "cloud_agent" &&
      caMission === "managed" &&
      (Boolean(activeCloudAgentId?.trim()) || recentMissions.length > 0),
    [uplinkId, caMission, activeCloudAgentId, recentMissions],
  );

  const previousWorkSummaryForStitch = React.useMemo(
    () =>
      buildPreviousWorkSummaryLine({
        lastSnapshot: managedCloudPoll.lastSnapshot,
        activeAgentId: activeCloudAgentId,
        firstRecent: recentMissions[0] ?? null,
      }),
    [managedCloudPoll.lastSnapshot, activeCloudAgentId, recentMissions],
  );

  const cloudAgentPreviewTitle = React.useMemo(() => {
    if (sending) return "Wait for the current request to finish.";
    if (!projectId) return "Select a project in Projects first.";
    if (!input.trim()) return "Type a mission in the message box first.";
    if (hasCloudFollowUpContext && cloudFollowUpMode === "continue") {
      return "Preview uses prior mission summary + your new instruction (new Cloud Agent launch). Does not message the previous agent.";
    }
    return "Builds a Cloud Agent preview digest; does not launch. Does not start the agent.";
  }, [sending, projectId, input, hasCloudFollowUpContext, cloudFollowUpMode]);

  const applyOperatorResultSideEffects = React.useCallback(
    (op: HamOperatorResult | null | undefined, streamSessionId?: string | null) => {
      if (op == null) return;
      // Server omits `handled` in some proxies; only skip when explicitly false.
      if (op.handled === false) return;

      const sid = streamSessionId?.trim() || null;
      const persistCursorSnapshot = (payload: Record<string, unknown> | null) => {
        if (sid) savePendingCursorAgentSessionSnapshot(sid, payload);
      };

      if (op.pending_apply) {
        setPendingApply(op.pending_apply as Record<string, unknown>);
      } else if (op.intent === "apply_settings" && op.ok) {
        setPendingApply(null);
      }
      if (op.pending_launch) {
        setPendingLaunch(op.pending_launch as Record<string, unknown>);
      } else if (op.intent === "launch_run" && op.ok) {
        setPendingLaunch(null);
      }
      if (op.pending_register) {
        setPendingRegister(op.pending_register as Record<string, unknown>);
      } else if (op.intent === "register_project" && op.ok) {
        setPendingRegister(null);
      }
      if (op.pending_cursor_agent) {
        setPendingCursorAgent(op.pending_cursor_agent as Record<string, unknown>);
        persistCursorSnapshot(op.pending_cursor_agent as Record<string, unknown>);
      } else if (op.intent === "cursor_agent_launch" && op.ok) {
        setPendingCursorAgent(null);
        persistCursorSnapshot(null);
      }
    },
    [],
  );

  const runOperatorConfirm = async (opts: {
    messages: { role: "user" | "assistant" | "system"; content: string }[];
    operator: {
      phase: "apply_settings" | "register_project" | "launch_run";
      confirmed: boolean;
      project_id?: string | null;
      changes?: Record<string, unknown> | null;
      base_revision?: string | null;
      name?: string | null;
      root?: string | null;
      prompt?: string | null;
    };
    bearer: string;
  }) => {
    if (!opts.bearer.trim()) {
      toast.error("Paste the operator token to confirm.");
      return;
    }
    setChatError(null);
    setSending(true);
    const userRow: ChatRow = {
      id: `pending-user-${Date.now()}`,
      role: "user",
      content: opts.messages[0]?.content ?? "[operator]",
      timestamp: timeStr(),
    };
    const assistantPlaceId = `assist-pending-${Date.now()}`;
    const assistantRow: ChatRow = {
      id: assistantPlaceId,
      role: "assistant",
      content: "",
      timestamp: timeStr(),
    };
    setMessages((prev) => [...prev, userRow, assistantRow]);
    setViewMode("chat");
    try {
      const streamAuth: HamChatStreamAuth = clerkEnabled
        ? { sessionToken: await getClerkSessionToken(), hamOperatorToken: opts.bearer }
        : opts.bearer;
      const res = await postChatStream(
        {
          session_id: sessionId ?? undefined,
          messages: opts.messages,
          ...(chatModelIdForApi ? { model_id: chatModelIdForApi } : {}),
          ...(projectId ? { project_id: projectId } : {}),
          workbench_mode: workbenchMode,
          worker,
          max_mode: maxMode,
          operator: opts.operator,
        },
        {
          onSession: (sid) => setSessionId(sid),
          onDelta: (delta) => {
            setMessages((prev) =>
              prev.map((m) =>
                m.id === assistantPlaceId ? { ...m, content: m.content + delta } : m,
              ),
            );
          },
        },
        streamAuth,
      );
      setSessionId(res.session_id);
      setMessages(
        res.messages.map((m, i) => ({
          id: `${res.session_id}-${i}-${m.role}`,
          role: m.role,
          content: m.content,
          timestamp: timeStr(),
        })),
      );
      applyOperatorResultSideEffects(res.operator_result, res.session_id);
      applyHamUiActions(res.actions ?? [], {
        navigate,
        setIsControlPanelOpen,
        isControlPanelOpen,
        setWorkbenchView: setViewMode,
        setBrowserMode: (active) => {
          setBrowserOnly(active);
          if (active) {
            setRequestedTabId("browser");
            setRequestedTabNonce((n) => n + 1);
          }
        },
      });
    } catch (err) {
      if (err instanceof HamAccessRestrictedError) {
        const msg =
          "Access restricted: this Ham deployment only allows approved email addresses or domains. Ask an admin or check Clerk sign-up restrictions.";
        setChatError(msg);
        toast.error(msg, { duration: 12_000, id: "ham-access-restricted" });
      } else if (
        err instanceof Error &&
        err.message === "Chat stream ended without a done event"
      ) {
        // Stream dropped mid-response — partial content is already in messages
        // state via onDelta. Don't clear it; the backend persists partial turns.
        const msg =
          "Response was interrupted — your partial message has been saved.";
        setChatError(msg);
        toast.error(msg, { duration: 8_000, id: "ham-stream-interrupted" });
      } else {
        const msg = err instanceof Error ? err.message : "Request failed";
        setChatError(msg);
        toast.error(msg, { duration: 8_000 });
      }
    } finally {
      setSending(false);
    }
  };

  const runOperatorPayloadStream = async (opts: {
    messages: { role: "user" | "assistant" | "system"; content: string }[];
    operator: HamChatOperatorPayload;
    /** Set for `cursor_agent_launch` and other operator writes that require `HAM_*` on `X-Ham-Operator-Authorization` when Clerk owns `Authorization`. */
    hamOperatorToken?: string;
    /**
     * When true, the last user line is already in `messages` state (e.g. chat handoff). Only append
     * the assistant placeholder; `messages[0]` is still the payload sent to the API.
     */
    transcriptUserAlreadyInTranscript?: boolean;
  }) => {
    if (opts.operator.phase === "cursor_agent_launch" && !opts.hamOperatorToken?.trim()) {
      toast.error("Paste HAM_CURSOR_AGENT_LAUNCH_TOKEN to launch.");
      return;
    }
    setChatError(null);
    setSending(true);
    const userRow: ChatRow = {
      id: `pending-user-${Date.now()}`,
      role: "user",
      content: opts.messages[0]?.content ?? "[operator]",
      timestamp: timeStr(),
    };
    const assistantPlaceId = `assist-pending-${Date.now()}`;
    const assistantRow: ChatRow = {
      id: assistantPlaceId,
      role: "assistant",
      content: "",
      timestamp: timeStr(),
    };
    if (opts.transcriptUserAlreadyInTranscript) {
      setMessages((prev) => [...prev, assistantRow]);
    } else {
      setMessages((prev) => [...prev, userRow, assistantRow]);
    }
    setViewMode("chat");
    try {
      let streamAuth: HamChatStreamAuth | undefined;
      if (opts.hamOperatorToken?.trim()) {
        const h = opts.hamOperatorToken.trim();
        streamAuth = clerkEnabled
          ? { sessionToken: await getClerkSessionToken(), hamOperatorToken: h }
          : h;
      } else {
        streamAuth = clerkEnabled ? { sessionToken: await getClerkSessionToken() } : undefined;
      }
      const res = await postChatStream(
        {
          session_id: sessionId ?? undefined,
          messages: opts.messages,
          ...(chatModelIdForApi ? { model_id: chatModelIdForApi } : {}),
          ...(projectId ? { project_id: projectId } : {}),
          workbench_mode: workbenchMode,
          worker,
          max_mode: maxMode,
          operator: opts.operator,
        },
        {
          onSession: (sid) => setSessionId(sid),
          onDelta: (delta) => {
            setMessages((prev) =>
              prev.map((m) =>
                m.id === assistantPlaceId ? { ...m, content: m.content + delta } : m,
              ),
            );
          },
        },
        streamAuth,
      );
      setSessionId(res.session_id);
      applyOperatorResultSideEffects(res.operator_result, res.session_id);
      setMessages(
        res.messages.map((m, i) => ({
          id: `${res.session_id}-${i}-${m.role}`,
          role: m.role,
          content: m.content,
          timestamp: timeStr(),
        })),
      );
      const op = res.operator_result;
      if (op?.intent === "cursor_agent_launch" && op.ok && op.data) {
        const d = op.data as Record<string, unknown>;
        if (d.mission_handling === "managed") {
          const rawId = d.agent_id ?? d.external_id;
          const aid = typeof rawId === "string" ? rawId.trim() : "";
          if (aid) {
            setUplinkId("cloud_agent");
            activateCloudMission(aid, {
              mission_handling: "managed",
              managedSplit: { kind: "new_launch" },
            });
          }
        }
      }
      applyHamUiActions(res.actions ?? [], {
        navigate,
        setIsControlPanelOpen,
        isControlPanelOpen,
        setWorkbenchView: setViewMode,
        setBrowserMode: (active) => {
          setBrowserOnly(active);
          if (active) {
            setRequestedTabId("browser");
            setRequestedTabNonce((n) => n + 1);
          }
        },
      });
    } catch (err) {
      if (err instanceof HamAccessRestrictedError) {
        const msg =
          "Access restricted: this Ham deployment only allows approved email addresses or domains. Ask an admin or check Clerk sign-up restrictions.";
        setChatError(msg);
        toast.error(msg, { duration: 12_000, id: "ham-access-restricted" });
      } else if (
        err instanceof Error &&
        err.message === "Chat stream ended without a done event"
      ) {
        const msg =
          "Response was interrupted — your partial message has been saved.";
        setChatError(msg);
        toast.error(msg, { duration: 8_000, id: "ham-stream-interrupted" });
      } else {
        const msg = err instanceof Error ? err.message : "Request failed";
        setChatError(msg);
        toast.error(msg, { duration: 8_000 });
      }
    } finally {
      setSending(false);
    }
  };

  const runCursorAgentPreviewCore = async (opts: {
    rawTask: string;
    /** Last message sent to the chat API (operator turn context). */
    apiUserMessageLine: string;
    transcriptUserAlreadyInTranscript: boolean;
  }) => {
    if (!projectId) {
      toast.error("Select a project (Projects) first.");
      return;
    }
    const rawTask = opts.rawTask.trim();
    if (!rawTask) {
      toast.error("Add a task text.");
      return;
    }
    const useStitch = hasCloudFollowUpContext && cloudFollowUpMode === "continue";
    const taskForOperator = useStitch
      ? stitchCloudAgentFollowUpTask(previousWorkSummaryForStitch, rawTask)
      : rawTask;
    await runOperatorPayloadStream({
      messages: [{ role: "user", content: opts.apiUserMessageLine }],
      transcriptUserAlreadyInTranscript: opts.transcriptUserAlreadyInTranscript,
      operator: {
        phase: "cursor_agent_preview",
        project_id: projectId,
        cursor_task_prompt: taskForOperator,
        cursor_repository: caRepo.trim() || null,
        cursor_ref: caRef.trim() || null,
        cursor_mission_handling: caMission,
      },
    });
  };

  const runChatNativeHandoffPreview = async (utterance: string) => {
    const raw = utterance.trim();
    const useStitch = hasCloudFollowUpContext && cloudFollowUpMode === "continue";
    const apiLine = useStitch
      ? `[Cloud Agent handoff — follow-up] ${raw}`
      : `[Cloud Agent handoff] ${raw}`;
    await runCursorAgentPreviewCore({
      rawTask: raw,
      apiUserMessageLine: apiLine,
      transcriptUserAlreadyInTranscript: true,
    });
  };

  const onHandoffSaveRepoAndPreview = async () => {
    if (!projectId || !cloudHandoffRepoSetup) return;
    const url = cloudHandoffRepoSetup.repoInput.trim();
    if (!url) {
      toast.error("Enter a repository URL.");
      return;
    }
    setHandoffRepoSaving(true);
    setChatError(null);
    try {
      const updated = await patchHamProjectMetadata(projectId, { cursor_cloud_repository: url });
      setHamProjects((prev) => prev.map((p) => (p.id === projectId ? { ...p, ...updated } : p)));
      if (!cloudTargetTouchedRef.current.repo) {
        setCaRepo(url);
      }
      const mission = cloudHandoffRepoSetup.missionText;
      setCloudHandoffRepoSetup(null);
      setUplinkId("cloud_agent");
      setCaMission("managed");
      setCloudMissionHandling("managed");
      await runChatNativeHandoffPreview(mission);
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : "Failed to save repository";
      setChatError(msg);
      toast.error(msg, { duration: 10_000 });
    } finally {
      setHandoffRepoSaving(false);
    }
  };

  const handleCloudAgentPreview = () => {
    if (!projectId) {
      toast.error("Select a project (Projects) first.");
      return;
    }
    const rawTask = input.trim();
    if (!rawTask) {
      toast.error("Type the mission in the message box, then click Preview.");
      return;
    }
    const useStitch = hasCloudFollowUpContext && cloudFollowUpMode === "continue";
    const userLine = useStitch
      ? `[Cloud Agent — preview — follow-up context] ${rawTask}`
      : `[Cloud Agent — preview] ${rawTask}`;
    void runCursorAgentPreviewCore({
      rawTask,
      apiUserMessageLine: userLine,
      transcriptUserAlreadyInTranscript: false,
    });
  };

  const handleCursorAgentTokenChange = (v: string) => {
    setOperatorCursorAgentToken(v);
    try {
      sessionStorage.setItem(CURSOR_AGENT_OP_KEY, v);
    } catch {
      /* ignore */
    }
  };

  const handleCursorAgentLaunchFromCard = () => {
    const p = pendingCursorAgent;
    if (!p) return;
    void runOperatorPayloadStream({
      messages: [{ role: "user", content: "[cursor_agent_launch operator]" }],
      operator: {
        phase: "cursor_agent_launch",
        confirmed: true,
        project_id: String(p.project_id ?? ""),
        cursor_task_prompt: String(p.cursor_task_prompt ?? ""),
        cursor_proposal_digest: String(p.proposal_digest ?? ""),
        cursor_base_revision: String(p.base_revision ?? ""),
        cursor_repository: p.cursor_repository ? String(p.cursor_repository) : null,
        cursor_ref: p.cursor_ref ? String(p.cursor_ref) : null,
        cursor_model: p.cursor_model ? String(p.cursor_model) : "default",
        cursor_auto_create_pr: Boolean(p.cursor_auto_create_pr),
        cursor_branch_name: p.cursor_branch_name ? String(p.cursor_branch_name) : null,
        cursor_expected_deliverable: p.cursor_expected_deliverable
          ? String(p.cursor_expected_deliverable)
          : null,
        cursor_mission_handling: p.cursor_mission_handling === "direct" ? "direct" : "managed",
      },
      hamOperatorToken: operatorCursorAgentToken,
    });
  };

  const processComposerSelectedFile = React.useCallback(async (file: File) => {
    if (file.size > MAX_CHAT_ATTACHMENT_BYTES) {
      toast.error(`File is too large (max ${formatAttachmentByteSize(MAX_CHAT_ATTACHMENT_BYTES)}).`);
      return;
    }
    const id = `att-${Date.now()}-${Math.random().toString(36).slice(2, 9)}`;
    const name = file.name || "attachment";
    const size = file.size;
    const kind = classifyComposerAttachment(file);
    try {
      if (kind === "image") {
        const dataUrl = await readFileAsDataURL(file);
        setComposerAttachment({ id, name, size, kind: "image", payload: dataUrl });
      } else if (kind === "text") {
        const t = await readFileAsText(file);
        setComposerAttachment({ id, name, size, kind: "text", payload: t });
      } else {
        setComposerAttachment({ id, name, size, kind: "binary", payload: "" });
      }
    } catch {
      toast.error("Could not read the selected file.");
    }
  }, []);

  const handleComposerFileInputChange = React.useCallback(
    (e: React.ChangeEvent<HTMLInputElement>) => {
      const list = e.target.files;
      e.target.value = "";
      const file = list?.[0];
      if (file) void processComposerSelectedFile(file);
    },
    [processComposerSelectedFile],
  );

  const handleVoiceDictationComplete = React.useCallback(async (blob: Blob) => {
    if (!blob.size) {
      toast.error("No audio captured.");
      return;
    }
    const filename = blob.type.includes("webm")
      ? "dictation.webm"
      : blob.type.includes("mp4") || blob.type.includes("mpeg")
        ? "dictation.m4a"
        : "dictation.webm";
    setVoiceTranscribing(true);
    try {
      const text = (await postChatTranscribe(blob, filename)).trim();
      if (!text) {
        toast.message("No text returned from transcription.");
        return;
      }
      setInput((prev) => (prev.trim() ? `${prev.trim()}\n${text}` : text));
    } catch (err) {
      if (err instanceof HamAccessRestrictedError) {
        toast.error(
          "Access restricted: this Ham deployment only allows approved email addresses or domains.",
          { duration: 12_000, id: "ham-access-restricted" },
        );
      } else {
        toast.error(err instanceof Error ? err.message : "Transcription failed.");
      }
    } finally {
      setVoiceTranscribing(false);
    }
  }, []);

  const handleSend = async (e: React.FormEvent) => {
    e.preventDefault();
    if ((!input.trim() && !composerAttachment) || sending || voiceTranscribing) return;
    const trimmedInput = input.trim();
    const textForOutbound = buildOutboundMessageWithAttachment(trimmedInput, composerAttachment);
    if (viewMode === "preview") {
      setViewMode("chat");
    }

    const aidStatus = activeCloudAgentId?.trim() ?? "";
    if (aidStatus && isCloudAgentStatusChatQuestion(trimmedInput)) {
      setInput("");
      setComposerAttachment(null);
      setChatError(null);
      const userRowStatus: ChatRow = {
        id: `pending-user-${Date.now()}`,
        role: "user",
        content: textForOutbound,
        timestamp: timeStr(),
      };
      const assistantStatusId = `assist-status-${Date.now()}`;
      const assistantStatusRow: ChatRow = {
        id: assistantStatusId,
        role: "assistant",
        content: "Checking managed mission status…",
        timestamp: timeStr(),
      };
      setMessages((prev) => [...prev, userRowStatus, assistantStatusRow]);
      setViewMode("chat");
      setSending(true);
      try {
        const row = await postCursorAgentSync(aidStatus);
        const line = formatManagedMissionStatusChatLine(row);
        setMessages((prev) =>
          prev.map((m) => (m.id === assistantStatusId ? { ...m, content: line } : m)),
        );
      } catch (err) {
        const msg = err instanceof Error ? err.message : "Could not sync mission status.";
        setMessages((prev) =>
          prev.map((m) => (m.id === assistantStatusId ? { ...m, content: msg } : m)),
        );
      } finally {
        setSending(false);
      }
      return;
    }

    const isHandoff = isCloudAgentHandoffRequest(trimmedInput);
    if (isHandoff && !projectId) {
      toast.error("Select a project (Projects) first to use a Cloud Agent handoff from chat.");
      return;
    }

    const userRow: ChatRow = {
      id: `pending-user-${Date.now()}`,
      role: "user",
      content: textForOutbound,
      timestamp: timeStr(),
    };

    if (isHandoff && projectId) {
      setInput("");
      setComposerAttachment(null);
      setChatError(null);
      setCloudHandoffRepoSetup(null);
      setMessages((prev) => [...prev, userRow]);
      setUplinkId("cloud_agent");
      setCaMission("managed");
      setCloudMissionHandling("managed");
      const rec = hamProjects.find((p) => p.id === projectId);
      const metaRepo = getCursorCloudRepository(rec?.metadata) ?? "";
      const effectiveRepo = (metaRepo || caRepo.trim()).trim();
      if (!effectiveRepo) {
        setCloudHandoffRepoSetup({
          missionText: textForOutbound,
          repoInput: mountRepo.trim() || "https://github.com/Code-Munkiz/ham",
        });
        return;
      }
      setSending(true);
      try {
        await runChatNativeHandoffPreview(textForOutbound);
      } finally {
        setSending(false);
      }
      return;
    }

    setInput("");
    setComposerAttachment(null);
    setChatError(null);

    const assistantPlaceId = `assist-pending-${Date.now()}`;
    const assistantRow: ChatRow = {
      id: assistantPlaceId,
      role: "assistant",
      content: "",
      timestamp: timeStr(),
    };
    setMessages((prev) => [...prev, userRow, assistantRow]);

    setSending(true);
    try {
      const streamAuth: HamChatStreamAuth | undefined = clerkEnabled
        ? { sessionToken: await getClerkSessionToken() }
        : undefined;
      const res = await postChatStream(
        {
          session_id: sessionId ?? undefined,
          messages: [{ role: "user", content: textForOutbound }],
          ...(chatModelIdForApi ? { model_id: chatModelIdForApi } : {}),
          ...(projectId ? { project_id: projectId } : {}),
          workbench_mode: workbenchMode,
          worker,
          max_mode: maxMode,
        },
        {
          onSession: (sid) => setSessionId(sid),
          onDelta: (delta) => {
            setMessages((prev) =>
              prev.map((m) =>
                m.id === assistantPlaceId
                  ? { ...m, content: m.content + delta }
                  : m,
              ),
            );
          },
        },
        streamAuth,
      );
      setSessionId(res.session_id);
      applyOperatorResultSideEffects(res.operator_result, res.session_id);
      setMessages(
        res.messages.map((m, i) => ({
          id: `${res.session_id}-${i}-${m.role}`,
          role: m.role,
          content: m.content,
          timestamp: timeStr(),
        })),
      );
      setActiveAgentNote(
        res.active_agent?.guidance_applied
          ? `Active agent guidance: ${res.active_agent.profile_name}`
          : null,
      );
      applyHamUiActions(res.actions ?? [], {
        navigate,
        setIsControlPanelOpen,
        isControlPanelOpen,
        setWorkbenchView: setViewMode,
        setBrowserMode: (active) => {
          setBrowserOnly(active);
          if (active) {
            setRequestedTabId("browser");
            setRequestedTabNonce((n) => n + 1);
          }
        },
      });
    } catch (err) {
      if (err instanceof HamAccessRestrictedError) {
        const msg =
          "Access restricted: this Ham deployment only allows approved email addresses or domains. Ask an admin or check Clerk sign-up restrictions.";
        setChatError(msg);
        toast.error(msg, { duration: 12_000, id: "ham-access-restricted" });
      } else if (
        err instanceof Error &&
        err.message === "Chat stream ended without a done event"
      ) {
        // Stream dropped mid-response — partial content is already in messages
        // state via onDelta. Don't clear it; the backend persists partial turns.
        const msg =
          "Response was interrupted — your partial message has been saved.";
        setChatError(msg);
        toast.error(msg, { duration: 8_000, id: "ham-stream-interrupted" });
      } else {
        const msg = err instanceof Error ? err.message : "Request failed";
        setChatError(msg);
        toast.error(msg, { duration: 8_000 });
      }
    } finally {
      setSending(false);
    }
  };

  const gatewayReadiness = getChatGatewayReadinessToken(catalog, {
    sending,
    catalogLoading,
  });
  /** War-room / legacy chat: full uplink + workbench + gateway token. */
  const pipelineStatus = `${uplinkPipelineLabel(uplinkId)} · ${workbenchMode.toUpperCase()} — ${gatewayReadiness}`;
  /** Operator Workspace: Hermes-style — show gateway honesty only (no FACTORY_AI / workbench rail). */
  const operatorWorkspaceStatus = gatewayReadiness;

  const workbenchMissionBannerActive =
    uplinkId === "cloud_agent" &&
    cloudMissionHandling === "managed" &&
    Boolean(activeCloudAgentId?.trim()) &&
    viewMode !== "chat";

  managedCompletionGatesRef.current = { uplinkId, cloudMissionHandling, activeCloudAgentId };

  const operatorMessages: OperatorMessage[] = messages;
  const operatorSessions: OperatorSessionItem[] = historySessions.map((session) => ({
    sessionId: session.session_id,
    preview: session.preview || "",
    turnCount: session.turn_count,
    createdAt: session.created_at ?? null,
    isActive: session.session_id === sessionId,
  }));
  const operatorAttachment: OperatorAttachment | null = composerAttachment
    ? {
        id: composerAttachment.id,
        name: composerAttachment.name,
        size: composerAttachment.size,
        kind: composerAttachment.kind,
        payload: composerAttachment.payload,
      }
    : null;
  const handleWorkspaceDictationText = (text: string) => {
    const next = text.trim();
    if (!next) return;
    setInput((prev) => (prev.trim() ? `${prev.trim()}\n${next}` : next));
  };

  const filteredHistorySessions = React.useMemo(() => {
    const q = historySearchQuery.trim().toLowerCase();
    if (!q) return historySessions;
    return historySessions.filter(
      (s) =>
        (s.preview || "").toLowerCase().includes(q) ||
        s.session_id.toLowerCase().includes(q),
    );
  }, [historySessions, historySearchQuery]);

  if (USE_OPERATOR_WORKSPACE) {
    return (
      <ManagedCloudAgentProvider value={managedCloudAgentContextValue}>
        <div className="flex h-full w-full flex-1 bg-[#030b11] font-sans relative overflow-hidden">
          <OperatorWorkspace
            activeAgentNote={activeAgentNote}
            activeProjectName={activeProjectName}
            messages={operatorMessages}
            sessions={operatorSessions}
            input={input}
            sending={sending}
            voiceTranscribing={voiceTranscribing}
            pipelineStatus={operatorWorkspaceStatus}
            chatError={chatError}
            attachment={operatorAttachment}
            attachmentAccept={CHAT_ATTACHMENT_ACCEPT}
            onInputChange={setInput}
            onAttachmentSelect={(file) => void processComposerSelectedFile(file)}
            onAttachmentClear={() => setComposerAttachment(null)}
            onDictationText={handleWorkspaceDictationText}
            onVoiceBlob={(blob) => void handleVoiceDictationComplete(blob)}
            onVoiceError={(message) => toast.error(message)}
            onSend={(event) => void handleSend(event)}
            onOpenHistory={() => setHistoryOpen(true)}
            onStartNewChat={startNewChat}
            onSelectSession={(sid) => void loadSession(sid)}
          />

          {historyOpen ? (
            <div className="fixed inset-0 z-[100] flex">
              <button
                type="button"
                aria-label="Close chat history"
                className="flex-1 bg-black/60 backdrop-blur-md"
                onClick={() => {
                  setHistorySearchQuery("");
                  setHistoryOpen(false);
                }}
              />
              <div className="w-full max-w-md h-full border-l border-white/[0.08] bg-[#060d14]/97 backdrop-blur-xl shadow-2xl flex flex-col text-white">
                <div className="shrink-0 border-b border-white/[0.08] px-4 py-3">
                  <div className="flex items-center justify-between gap-3">
                    <div className="min-w-0">
                      <span className="text-[10px] font-semibold uppercase tracking-[0.14em] text-white/55">
                        Sessions
                      </span>
                      <p className="text-[11px] text-white/35 mt-0.5">
                        Open a past conversation or start fresh.
                      </p>
                    </div>
                    <div className="flex items-center gap-1.5 shrink-0">
                      <button
                        type="button"
                        onClick={startNewChat}
                        className="flex items-center gap-1 rounded-lg border border-white/12 bg-white/[0.03] px-2.5 py-1.5 text-[11px] font-medium text-white/75 hover:border-white/18 hover:bg-white/[0.06]"
                      >
                        <Plus className="h-3.5 w-3.5 opacity-80" />
                        New
                      </button>
                      <button
                        type="button"
                        onClick={() => {
                          setHistorySearchQuery("");
                          setHistoryOpen(false);
                        }}
                        className="p-2 rounded-lg text-white/45 hover:text-white/90 hover:bg-white/[0.06]"
                        aria-label="Close"
                      >
                        <X className="h-4 w-4" />
                      </button>
                    </div>
                  </div>
                  <div className="relative mt-3">
                    <Search className="pointer-events-none absolute left-2.5 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-white/35" />
                    <input
                      type="search"
                      value={historySearchQuery}
                      onChange={(e) => setHistorySearchQuery(e.target.value)}
                      placeholder="Filter sessions"
                      className="w-full rounded-lg border border-white/10 bg-black/30 py-2 pl-8 pr-3 text-sm text-white/88 placeholder:text-white/35 outline-none focus-visible:border-white/20 focus-visible:ring-1 focus-visible:ring-white/10"
                      autoComplete="off"
                    />
                  </div>
                </div>
                <div className="flex-1 overflow-y-auto p-4 space-y-6">
                  {USE_OPERATOR_WORKSPACE ? null : (
                  <div>
                    <p className="text-[9px] font-black uppercase tracking-widest text-[#00E5FF] mb-2">Managed missions (server)</p>
                    <p className="text-[8px] text-white/25 mb-2 leading-relaxed">
                      Authoritative list from HAM&rsquo;s mission registry &mdash; use Open to focus this agent in Cloud (managed)
                      and land on <span className="text-white/40">Overview</span>.
                    </p>
                    {serverMissionsLoading ? (
                      <p className="text-[10px] text-white/30">Loading missions…</p>
                    ) : serverMissions.length === 0 ? (
                      <p className="text-[10px] text-white/25">No managed missions on this API host yet.</p>
                    ) : (
                      <ul className="space-y-2">
                        {serverMissions.filter((m) => (m.cursor_agent_id || "").trim()).map((m) => {
                          const aid = (m.cursor_agent_id || "").trim();
                          const reg = m.mission_registry_id ? `${m.mission_registry_id.slice(0, 8)}…` : "—";
                          const last = m.last_server_observed_at || m.updated_at;
                          return (
                            <li
                              key={m.mission_registry_id || aid}
                              className="border border-white/10 bg-white/[0.02] rounded-lg px-3 py-2.5"
                            >
                              <div className="flex items-start justify-between gap-2">
                                <div className="min-w-0 flex-1">
                                  <p className="text-[8px] font-mono text-white/35 truncate" title={aid}>
                                    {aid}
                                  </p>
                                  <p className="text-[10px] text-white/70 mt-0.5 truncate" title={m.repository_observed || m.repo_key || ""}>
                                    {m.repo_key || m.repository_observed || "—"}
                                  </p>
                                  <p className="text-[8px] text-white/30 mt-1">
                                    <span className="text-white/45">Status: </span>
                                    {m.mission_lifecycle || "—"}
                                    {m.cursor_status_last_observed ? (
                                      <span className="text-white/25"> · {m.cursor_status_last_observed}</span>
                                    ) : null}
                                  </p>
                                  {last ? (
                                    <p className="text-[7px] text-white/20 mt-0.5">Last seen (server): {last}</p>
                                  ) : null}
                                  <p className="text-[7px] text-white/15 mt-0.5 font-mono">registry {reg}</p>
                                </div>
                                <button
                                  type="button"
                                  onClick={() => openServerManagedMission(aid)}
                                  className="shrink-0 text-[8px] font-black uppercase tracking-widest text-[#00E5FF] border border-[#00E5FF]/30 rounded px-2 py-1 hover:bg-[#00E5FF]/10"
                                >
                                  Open
                                </button>
                              </div>
                            </li>
                          );
                        })}
                      </ul>
                    )}
                  </div>
                  )}
                  <div>
                    <p className="text-[9px] font-semibold uppercase tracking-[0.12em] text-white/38 mb-2">
                      {historySearchQuery.trim() ? "Matching" : "Recent"}
                    </p>
                    {historyLoading ? (
                      <p className="text-[10px] text-white/30">Loading…</p>
                    ) : historySessions.length === 0 ? (
                      <p className="text-[10px] text-white/25">No past chats yet. Start a conversation and it'll appear here.</p>
                    ) : filteredHistorySessions.length === 0 ? (
                      <p className="text-[10px] text-white/30">No sessions match that filter.</p>
                    ) : (
                      <ul className="space-y-2">
                        {filteredHistorySessions.map((s) => (
                          <li key={s.session_id} className="list-none">
                            <button
                              type="button"
                              onClick={() => {
                                void loadSession(s.session_id);
                                setHistorySearchQuery("");
                                setHistoryOpen(false);
                              }}
                              className={cn(
                                "w-full text-left border rounded-[0.7rem] px-3.5 py-2.5 transition-colors group",
                                s.session_id === sessionId
                                  ? "border-[#c45c12]/40 bg-gradient-to-b from-[#1a120a]/50 to-[#0f0c09]/40"
                                  : "border-white/[0.1] bg-white/[0.02] hover:border-white/16 hover:bg-white/[0.05]",
                              )}
                            >
                              <div className="flex items-center justify-between gap-2 mb-0.5">
                                <span className="text-[9px] tabular-nums text-white/32">
                                  {s.turn_count} turn{s.turn_count !== 1 ? "s" : ""}
                                </span>
                                {s.created_at && (
                                  <span className="text-[9px] text-white/25 shrink-0">
                                    {new Date(s.created_at).toLocaleDateString(undefined, {
                                      month: "short",
                                      day: "numeric",
                                    })}
                                  </span>
                                )}
                              </div>
                              <p className="text-[12px] font-medium text-white/78 group-hover:text-white/95 truncate leading-snug">
                                {s.preview || "Untitled session"}
                              </p>
                            </button>
                          </li>
                        ))}
                      </ul>
                    )}
                  </div>
                </div>
              </div>
            </div>
          ) : null}

          {projectsOpen ? (
            <div className="fixed inset-0 z-[100] flex">
              <button
                type="button"
                aria-label="Close projects"
                className="flex-1 bg-black/70 backdrop-blur-xl"
                onClick={closeProjectsPanel}
              />
              <ProjectsRegistryPanel
                mountRepo={mountRepo}
                setMountRepo={setMountRepo}
                mountRef={mountRef}
                setMountRef={setMountRef}
                activeCloudAgentId={activeCloudAgentId}
                setActiveCloudAgentIdLive={setActiveCloudAgentIdLive}
                onActiveMissionBlurCommit={(trimmed) => {
                  if (trimmed) {
                    activateCloudMission(trimmed, { managedSplit: { kind: "existing" } });
                  }
                }}
                recentMissions={recentMissions}
                formatShortcutAge={formatShortcutAge}
                onShortcutUse={(id) => activateCloudMission(id, { managedSplit: { kind: "existing" } })}
                projects={hamProjects}
                projectsLoading={projectsLoading}
                onOpenActivity={() => {
                  closeProjectsPanel();
                  navigate("/activity");
                }}
                onBindProject={(pid) => {
                  setProjectId(pid);
                  closeProjectsPanel();
                }}
                onUpdateProjectDefaultPolicy={onUpdateProjectDefaultPolicy}
                activeCloudAgentIdForShortcut={activeCloudAgentId}
                onClose={closeProjectsPanel}
              />
            </div>
          ) : null}

          <CloudAgentLaunchModal
            open={cloudLaunchOpen}
            onClose={() => setCloudLaunchOpen(false)}
            defaultMissionHandling={cloudMissionHandling}
            onActivateMission={(id, opts) => activateCloudMission(id, opts)}
            recentMissions={recentMissions}
            onRemoveRecent={removeRecentMission}
            mountDefaults={mountDefaultsForLaunch}
            projectId={projectId}
          />
        </div>
      </ManagedCloudAgentProvider>
    );
  }

  return (
    <ManagedCloudAgentProvider value={managedCloudAgentContextValue}>
    <div className="flex h-full bg-[#000000] font-sans relative overflow-hidden">
      {/* Background Rail Grid */}
      <div className="absolute inset-0 opacity-[0.012] pointer-events-none" 
           style={{ backgroundImage: 'linear-gradient(#fff 1px, transparent 1px), linear-gradient(90deg, #fff 1px, transparent 1px)', backgroundSize: '80px 80px' }} />

      {/* Main Dynamic Workspace Area */}
      <div className="flex-1 flex flex-col relative z-20 overflow-hidden">
        
        {/* Workbench Header */}
        <div className="h-12 flex items-center px-8 border-b border-white/5 bg-black/60 justify-between shrink-0">
           <div className="flex items-center gap-6">
              <div className="flex items-center gap-4">
                 <div className="h-2 w-2 rounded-full bg-[#FF6B00] shadow-[0_0_10px_#FF6B00]" />
                 <span className="text-[10px] font-black tracking-[0.2em] text-[#FF6B00] uppercase italic">Workbench_Session</span>
              </div>
              {activeAgentNote && (
                <span
                  className="text-[9px] font-bold text-emerald-500/80 uppercase tracking-widest truncate max-w-[min(280px,40vw)] hidden sm:inline"
                  title={activeAgentNote}
                >
                  {activeAgentNote}
                </span>
              )}
           </div>
           
           <div className="flex items-center gap-3 shrink-0">
              <button
                type="button"
                onClick={() => setIsControlPanelOpen(!isControlPanelOpen)}
                className={cn(
                  "flex items-center gap-3 px-4 py-1.5 border transition-all rounded-lg group shadow-xl",
                  isControlPanelOpen
                    ? "bg-[#FF6B00]/10 border-[#FF6B00]/40 text-[#FF6B00]"
                    : "bg-white/5 border-white/10 text-white/40 hover:text-white",
                )}
              >
                 <Activity className="h-3.5 w-3.5" />
                 <span className="text-[10px] font-black uppercase tracking-widest">Control Panel</span>
                 <ChevronDown className={cn("h-3 w-3 transition-transform duration-300", isControlPanelOpen ? "rotate-180" : "")} />
              </button>
              <button
                type="button"
                onClick={startNewChat}
                title="New chat"
                className="flex items-center gap-2 px-4 py-1.5 border border-white/10 bg-white/5 text-white/50 hover:text-white rounded-lg transition-colors"
              >
                <Plus className="h-3.5 w-3.5" />
                <span className="text-[10px] font-black uppercase tracking-widest">New</span>
              </button>
              <button
                type="button"
                onClick={() => setHistoryOpen(true)}
                className={cn(
                  "flex items-center gap-2 px-4 py-1.5 border rounded-lg transition-colors",
                  historyOpen
                    ? "bg-[#FF6B00]/10 border-[#FF6B00]/40 text-[#FF6B00]"
                    : "border-white/10 bg-white/5 text-white/50 hover:text-white",
                )}
              >
                <MessageSquare className="h-3.5 w-3.5" />
                <span className="text-[10px] font-black uppercase tracking-widest">History</span>
              </button>
              <button
                type="button"
                onClick={() => setProjectsOpen(true)}
                className="flex items-center gap-2 px-4 py-1.5 border border-white/10 bg-white/5 text-white/50 hover:text-white rounded-lg transition-colors"
              >
                <History className="h-3.5 w-3.5" />
                <span className="text-[10px] font-black uppercase tracking-widest">Projects</span>
              </button>
           </div>
        </div>
        
        {/* RIGHT-SIDE CONTROL PANEL OVERLAY - HANDLED BY APPLAYOUT NOW */}

        {/* Dynamic Workbench Canvas: optional live mission ribbon, then chat-only, preview, or resizable split */}
        <div className="flex flex-1 min-h-0 flex-col relative overflow-hidden">
          <LiveManagedMissionBanner when={workbenchMissionBannerActive} />
          {viewMode === "chat" ? (
            <TranscriptColumn
              messages={messages}
              primaryPersona={primaryPersona}
              activeProjectName={activeProjectName}
              pendingCursorAgent={pendingCursorAgent}
              operatorCursorAgentToken={operatorCursorAgentToken}
              onOperatorCursorAgentTokenChange={handleCursorAgentTokenChange}
              onCursorAgentLaunch={handleCursorAgentLaunchFromCard}
              onDismissCursorPreview={dismissCursorPreview}
              cursorAgentActionsDisabled={sending}
              cloudHandoffRepoSetup={cloudHandoffRepoSetup}
              onHandoffRepoInputChange={(v) =>
                setCloudHandoffRepoSetup((s) => (s ? { ...s, repoInput: v } : s))
              }
              onHandoffSaveRepoAndPreview={onHandoffSaveRepoAndPreview}
              onDismissHandoffRepoSetup={() => setCloudHandoffRepoSetup(null)}
              handoffRepoSaving={handoffRepoSaving}
            />
          ) : viewMode === "preview" ? (
            <WarRoomPane
              uplinkId={uplinkId}
              activeCloudAgentId={activeCloudAgentId}
              cloudMissionHandling={uplinkId === "cloud_agent" ? cloudMissionHandling : undefined}
              embedUrl={paneEmbedUrl}
              onEmbedUrlChange={setPaneEmbedUrl}
              requestedTabId={requestedTabId}
              requestedTabNonce={requestedTabNonce}
              browserOnly={browserOnly}
              executionMode="preview"
              onCloseExecution={() => setViewMode("chat")}
              workbenchMissionBannerActive={workbenchMissionBannerActive}
              onOpenProjectsRegistry={() => setProjectsOpen(true)}
            />
          ) : (
            <ResizableWorkbenchSplit
              left={
                <div
                  className={cn(
                    "flex h-full min-h-0 min-w-0 flex-col",
                    workbenchMissionBannerActive && "border-t border-white/[0.03]",
                  )}
                >
                  <TranscriptColumn
                    messages={messages}
                    primaryPersona={primaryPersona}
                    activeProjectName={activeProjectName}
                    pendingCursorAgent={pendingCursorAgent}
                    operatorCursorAgentToken={operatorCursorAgentToken}
                    onOperatorCursorAgentTokenChange={handleCursorAgentTokenChange}
                    onCursorAgentLaunch={handleCursorAgentLaunchFromCard}
                    onDismissCursorPreview={dismissCursorPreview}
                    cursorAgentActionsDisabled={sending}
                    cloudHandoffRepoSetup={cloudHandoffRepoSetup}
                    onHandoffRepoInputChange={(v) =>
                      setCloudHandoffRepoSetup((s) => (s ? { ...s, repoInput: v } : s))
                    }
                    onHandoffSaveRepoAndPreview={onHandoffSaveRepoAndPreview}
                    onDismissHandoffRepoSetup={() => setCloudHandoffRepoSetup(null)}
                    handoffRepoSaving={handoffRepoSaving}
                  />
                </div>
              }
              right={
                <WarRoomPane
                  uplinkId={uplinkId}
                  activeCloudAgentId={activeCloudAgentId}
                  cloudMissionHandling={uplinkId === "cloud_agent" ? cloudMissionHandling : undefined}
                  embedUrl={paneEmbedUrl}
                  onEmbedUrlChange={setPaneEmbedUrl}
                  requestedTabId={requestedTabId}
                  requestedTabNonce={requestedTabNonce}
                  browserOnly={browserOnly}
                  executionMode={viewMode === "war_room" ? "war_room" : "split"}
                  onCloseExecution={() => setViewMode("chat")}
                  warRoomSignal={viewMode === "war_room"}
                  reduceMotion={reduceMotion}
                  warBlink={warBlink}
                  workbenchMissionBannerActive={workbenchMissionBannerActive}
                  onOpenProjectsRegistry={() => setProjectsOpen(true)}
                />
              }
            />
          )}
        </div>

        {/* COMPOSER Interface — compact (~⅓ shorter than prior) */}
        <div className="px-6 sm:px-10 pb-6 pt-2 bg-gradient-to-t from-black via-black/95 to-transparent relative z-30">
          <div className="max-w-3xl mx-auto space-y-2">
             <div className="flex flex-wrap items-center gap-2 px-0.5">
               <span className="text-[8px] font-mono font-bold uppercase tracking-widest text-white/40">{pipelineStatus}</span>
             </div>
             {chatError ? (
               <div className="flex items-center gap-2 rounded-lg border border-destructive/30 bg-destructive/10 px-4 py-2 text-[11px] font-bold uppercase tracking-widest text-destructive">
                 <AlertCircle className="h-4 w-4 shrink-0" />
                 {chatError}
               </div>
             ) : null}

             {(pendingApply || pendingLaunch || pendingRegister) && (
               <div className="rounded-lg border border-[#FF6B00]/30 bg-[#FF6B00]/5 px-4 py-3 space-y-3 text-[11px] text-white/80">
                 <div className="font-black uppercase tracking-widest text-[#FF6B00]">
                   Operator confirmation
                 </div>
                 {pendingApply && (
                   <div className="space-y-2">
                     <p>
                       Agent Builder preview is ready for project{" "}
                       <span className="font-mono text-white">
                         {String(pendingApply.project_id)}
                       </span>
                       . Paste{" "}
                       <span className="font-mono">HAM_SETTINGS_WRITE_TOKEN</span> and
                       apply.
                     </p>
                     <input
                       type="password"
                       autoComplete="off"
                       placeholder="HAM_SETTINGS_WRITE_TOKEN"
                       value={operatorSettingsToken}
                       onChange={(e) => {
                         const v = e.target.value;
                         setOperatorSettingsToken(v);
                         sessionStorage.setItem(SETTINGS_OP_KEY, v);
                       }}
                       className="w-full rounded border border-white/15 bg-black/40 px-3 py-2 font-mono text-[11px] text-white"
                     />
                     <button
                       type="button"
                       disabled={sending}
                       onClick={() =>
                         void runOperatorConfirm({
                           messages: [
                             {
                               role: "user",
                               content: "[confirm apply Agent Builder preview]",
                             },
                           ],
                           operator: {
                             phase: "apply_settings",
                             confirmed: true,
                             project_id: String(pendingApply.project_id),
                             changes: pendingApply.changes as Record<string, unknown>,
                             base_revision: String(pendingApply.base_revision),
                           },
                           bearer: operatorSettingsToken,
                         })
                       }
                       className="rounded bg-[#FF6B00] px-4 py-2 text-[10px] font-black uppercase tracking-widest text-black disabled:opacity-50"
                     >
                       Apply preview
                     </button>
                   </div>
                 )}
                 {pendingLaunch && (
                   <div className="space-y-2">
                     <p>
                       Launch bridge run for{" "}
                       <span className="font-mono">{String(pendingLaunch.project_id)}</span>{" "}
                       (requires <span className="font-mono">HAM_RUN_LAUNCH_TOKEN</span> on
                       API).
                     </p>
                     <input
                       type="password"
                       autoComplete="off"
                       placeholder="HAM_RUN_LAUNCH_TOKEN"
                       value={operatorLaunchToken}
                       onChange={(e) => {
                         const v = e.target.value;
                         setOperatorLaunchToken(v);
                         sessionStorage.setItem(LAUNCH_OP_KEY, v);
                       }}
                       className="w-full rounded border border-white/15 bg-black/40 px-3 py-2 font-mono text-[11px] text-white"
                     />
                     <button
                       type="button"
                       disabled={sending}
                       onClick={() =>
                         void runOperatorConfirm({
                           messages: [
                             { role: "user", content: "[confirm launch bridge run]" },
                           ],
                           operator: {
                             phase: "launch_run",
                             confirmed: true,
                             project_id: String(pendingLaunch.project_id),
                             prompt: String(pendingLaunch.prompt ?? ""),
                           },
                           bearer: operatorLaunchToken,
                         })
                       }
                       className="rounded bg-[#FF6B00] px-4 py-2 text-[10px] font-black uppercase tracking-widest text-black disabled:opacity-50"
                     >
                       Confirm launch
                     </button>
                   </div>
                 )}
                 {pendingRegister && (
                   <div className="space-y-2">
                     <p>
                       Register{" "}
                       <span className="font-mono">{String(pendingRegister.name)}</span> →{" "}
                       <span className="font-mono">{String(pendingRegister.root)}</span>
                     </p>
                     <input
                       type="password"
                       autoComplete="off"
                       placeholder="HAM_SETTINGS_WRITE_TOKEN"
                       value={operatorSettingsToken}
                       onChange={(e) => {
                         const v = e.target.value;
                         setOperatorSettingsToken(v);
                         sessionStorage.setItem(SETTINGS_OP_KEY, v);
                       }}
                       className="w-full rounded border border-white/15 bg-black/40 px-3 py-2 font-mono text-[11px] text-white"
                     />
                     <button
                       type="button"
                       disabled={sending}
                       onClick={() =>
                         void runOperatorConfirm({
                           messages: [
                             { role: "user", content: "[confirm register project]" },
                           ],
                           operator: {
                             phase: "register_project",
                             confirmed: true,
                             name: String(pendingRegister.name),
                             root: String(pendingRegister.root),
                           },
                           bearer: operatorSettingsToken,
                         })
                       }
                       className="rounded bg-[#FF6B00] px-4 py-2 text-[10px] font-black uppercase tracking-widest text-black disabled:opacity-50"
                     >
                       Confirm register
                     </button>
                   </div>
                 )}
               </div>
             )}

             <form onSubmit={handleSend} className="relative isolate group shadow-xl">
                <input
                  ref={composerFileInputRef}
                  type="file"
                  className="sr-only"
                  tabIndex={-1}
                  accept={CHAT_ATTACHMENT_ACCEPT}
                  onChange={handleComposerFileInputChange}
                  aria-hidden
                />
                <div
                  className="pointer-events-none absolute -inset-0.5 z-0 rounded-xl bg-gradient-to-r from-[#FF6B00]/15 to-[#FF6B00]/5 opacity-15 blur-md transition duration-500 group-focus-within:opacity-50"
                  aria-hidden
                />
                <div className="relative z-10 flex flex-col overflow-visible rounded-lg border border-white/10 bg-[#0d0d0d] shadow-xl">
                   <div className="flex items-center justify-between gap-2 border-b border-white/5 bg-black/25 px-3 py-1.5 rounded-t-lg">
                     <button
                       type="button"
                       onClick={() => setShowAgentControls((v) => !v)}
                       aria-expanded={showAgentControls}
                       aria-controls="ham-chat-agent-controls-panel"
                       className={cn(
                         "inline-flex items-center gap-1.5 rounded-md px-2 py-1 text-[8px] font-black uppercase tracking-widest transition-colors",
                         showAgentControls
                           ? "bg-white/[0.08] text-[#FF6B00]"
                           : "text-white/45 hover:bg-white/[0.06] hover:text-white/70",
                       )}
                     >
                       <Radio className="h-3 w-3 shrink-0 opacity-80" aria-hidden />
                       Agent controls
                       {showAgentControls ? (
                         <ChevronUp className="h-3 w-3 shrink-0 opacity-60" aria-hidden />
                       ) : (
                         <ChevronDown className="h-3 w-3 shrink-0 opacity-60" aria-hidden />
                       )}
                     </button>
                   </div>
                   <div
                     className={cn(
                       "grid transition-[grid-template-rows] duration-300 ease-out motion-reduce:transition-none",
                       showAgentControls ? "grid-rows-[1fr]" : "grid-rows-[0fr]",
                     )}
                   >
                     <div
                       id="ham-chat-agent-controls-panel"
                       className={cn(
                         "min-h-0 transition-opacity duration-300 ease-out motion-reduce:transition-none",
                         showAgentControls ? "overflow-visible opacity-100" : "overflow-hidden opacity-0",
                       )}
                     >
                       <div className="relative z-20 bg-black/35">
                         <ChatComposerStrip
                           workbenchMode={workbenchMode}
                           onWorkbenchMode={setWorkbenchMode}
                           modelId={modelId}
                           onModelId={setModelId}
                           maxMode={maxMode}
                           onMaxMode={setMaxMode}
                           worker={worker}
                           onWorker={setWorker}
                           uplinkId={uplinkId}
                           onUplinkId={setUplinkId}
                           onOpenCloudAgentLaunch={() => setCloudLaunchOpen(true)}
                           onCloudAgentPreview={handleCloudAgentPreview}
                           cloudAgentPreviewDisabled={sending || !input.trim() || !projectId}
                           cloudAgentPreviewTitle={cloudAgentPreviewTitle}
                           catalog={catalog}
                           catalogLoading={catalogLoading}
                         />
                       </div>
                       {projectId ? (
                         <div className="border-t border-white/5 px-3 py-1.5 bg-black/20">
                           {showCloudAgentMissingRepoHint ? (
                             <p className="mb-2 text-[9px] font-bold leading-snug text-amber-400/90">
                               No Cloud Agent repository found for this project. Set{" "}
                               <span className="font-mono">cursor_cloud_repository</span> in project metadata or open{" "}
                               <span className="font-mono">Cloud Agent target</span> and enter a repository.
                             </p>
                           ) : null}
                           {uplinkId === "cloud_agent" && hasCloudFollowUpContext ? (
                             <div
                               className="mb-2 rounded border border-cyan-500/25 bg-cyan-950/30 px-2.5 py-2"
                               role="region"
                               aria-label="Cloud Agent follow-up mode"
                             >
                               <p className="text-[9px] font-bold uppercase tracking-wider text-cyan-200/90">
                                 Continue previous Cloud Agent work?
                               </p>
                               <p className="mt-0.5 text-[8px] text-white/45">
                                 Uses a new launch with stitched context. Does not send messages to the existing agent.
                               </p>
                               <div className="mt-2 flex flex-wrap gap-x-4 gap-y-1.5">
                                 <label className="flex cursor-pointer items-center gap-1.5 text-[9px] text-white/85">
                                   <input
                                     type="radio"
                                     name="ham-cloud-followup-mode"
                                     className="accent-cyan-500"
                                     checked={cloudFollowUpMode === "continue"}
                                     onChange={() => setCloudFollowUpMode("continue")}
                                   />
                                   Continue with context (default)
                                 </label>
                                 <label className="flex cursor-pointer items-center gap-1.5 text-[9px] text-white/85">
                                   <input
                                     type="radio"
                                     name="ham-cloud-followup-mode"
                                     className="accent-cyan-500"
                                     checked={cloudFollowUpMode === "fresh"}
                                     onChange={() => setCloudFollowUpMode("fresh")}
                                   />
                                   Start fresh
                                 </label>
                               </div>
                             </div>
                           ) : null}
                           <button
                             type="button"
                             onClick={() => setCloudAgentOptionsOpen((o) => !o)}
                             className="text-[8px] font-black uppercase tracking-widest text-cyan-500/60 hover:text-cyan-400/90"
                           >
                             {cloudAgentOptionsOpen ? "Hide" : "Show"} Cloud Agent target (repo / ref / mode)
                           </button>
                           {cloudAgentOptionsOpen ? (
                             <div className="mt-2 grid gap-2 sm:grid-cols-2 max-w-3xl">
                               <label className="space-y-1">
                                 <span className="text-[8px] font-bold uppercase tracking-widest text-white/35">
                                   Repository override
                                 </span>
                                 <input
                                   value={caRepo}
                                   onChange={(e) => {
                                     cloudTargetTouchedRef.current.repo = true;
                                     setCaRepo(e.target.value);
                                   }}
                                   placeholder="Optional — default from project"
                                   className="w-full rounded border border-white/10 bg-black/40 px-2 py-1 font-mono text-[10px] text-white"
                                 />
                               </label>
                               <label className="space-y-1">
                                 <span className="text-[8px] font-bold uppercase tracking-widest text-white/35">
                                   Ref override
                                 </span>
                                 <input
                                   value={caRef}
                                   onChange={(e) => {
                                     cloudTargetTouchedRef.current.ref = true;
                                     setCaRef(e.target.value);
                                   }}
                                   placeholder="Optional"
                                   className="w-full rounded border border-white/10 bg-black/40 px-2 py-1 font-mono text-[10px] text-white"
                                 />
                               </label>
                               <label className="space-y-1 sm:col-span-2">
                                 <span className="text-[8px] font-bold uppercase tracking-widest text-white/35">
                                   Mission handling
                                 </span>
                                 <select
                                   value={caMission}
                                   onChange={(e) => setCaMission(e.target.value as "direct" | "managed")}
                                   className="w-full max-w-xs rounded border border-white/10 bg-black/40 px-2 py-1 font-mono text-[10px] text-white"
                                 >
                                   <option value="managed">Managed by HAM</option>
                                   <option value="direct">Direct</option>
                                 </select>
                               </label>
                             </div>
                           ) : null}
                         </div>
                       ) : null}
                     </div>
                   </div>
                   <div className="flex flex-col border-t border-white/5">
                      <div
                        className="min-h-[34px] shrink-0 px-4 pt-2 flex items-center"
                        aria-live="polite"
                      >
                        {composerAttachment ? (
                          <div className="flex max-w-full items-center gap-2 rounded-md border border-white/10 bg-white/[0.04] py-1 pl-2.5 pr-1 text-[9px] text-white/80">
                            <Paperclip className="h-3 w-3 shrink-0 text-[#FF6B00]/70" aria-hidden />
                            <span className="min-w-0 truncate font-mono font-bold" title={composerAttachment.name}>
                              {composerAttachment.name}
                            </span>
                            <span className="shrink-0 text-white/35">
                              {formatAttachmentByteSize(composerAttachment.size)}
                            </span>
                            <button
                              type="button"
                              onClick={() => setComposerAttachment(null)}
                              className="ml-0.5 flex h-6 w-6 shrink-0 items-center justify-center rounded text-white/40 transition-colors hover:bg-white/10 hover:text-white"
                              aria-label="Remove attachment"
                            >
                              <X className="h-3.5 w-3.5" />
                            </button>
                          </div>
                        ) : null}
                      </div>
                      <div className="flex items-start px-4 pt-0 pb-2 gap-2">
                         <span className="text-[#FF6B00] font-mono text-[12px] font-bold mt-1 shrink-0 select-none" aria-hidden>
                           &gt;_
                         </span>
                         <textarea
                            value={input}
                            onChange={(e) => setInput(e.target.value)}
                            onKeyDown={(e) => {
                              if (e.key === "Enter" && !e.shiftKey) {
                                e.preventDefault();
                                void handleSend(e as unknown as React.FormEvent);
                              }
                            }}
                            placeholder={directivePlaceholder(workbenchMode)}
                            className="flex-1 bg-transparent border-none outline-none text-white text-[12px] font-bold uppercase tracking-[0.05em] placeholder:text-white/10 resize-none min-h-[48px] max-h-[140px] leading-snug"
                         />
                      </div>

                      <div className="flex min-h-8 items-center px-4 py-1 bg-white/[0.02] border-t border-white/5 justify-between gap-2 flex-wrap">
                         <div className="flex items-center gap-1 sm:gap-2">
                            <button
                              type="button"
                              disabled={sending}
                              onClick={() => composerFileInputRef.current?.click()}
                              className="flex items-center gap-1.5 text-[8px] text-white/25 hover:text-[#FF6B00] font-black uppercase tracking-widest transition-colors px-1.5 py-1 rounded disabled:opacity-40"
                            >
                               <Paperclip className="h-3 w-3" />
                               Attach
                            </button>
                            <div
                              title={
                                voiceTranscribing
                                  ? "Transcribing…"
                                  : "Voice dictation — stop recording to add text to the message"
                              }
                              className="flex items-center gap-1.5 text-[8px] text-white/25 font-black uppercase tracking-widest px-1.5 py-1 rounded min-w-0"
                            >
                              <span className="shrink-0 text-white/25 hidden sm:inline">
                                {voiceTranscribing ? "…" : "Voice"}
                              </span>
                              <VoiceMessageInput
                                compact
                                hidePreview
                                disabled={sending || voiceTranscribing}
                                onVoiceMessage={(blob) => {
                                  void handleVoiceDictationComplete(blob);
                                }}
                              />
                            </div>
                            <button
                              type="button"
                              onClick={() => setMaxMode((m) => !m)}
                              className={cn(
                                "flex items-center gap-1.5 text-[8px] font-black uppercase tracking-widest transition-colors px-1.5 py-1 rounded",
                                maxMode ? "text-[#FF6B00]" : "text-white/25 hover:text-[#FF6B00]",
                              )}
                            >
                              <Zap className="h-3 w-3" />
                              Fast
                            </button>
                         </div>

                         <div className="flex items-center gap-2 ml-auto">
                            <span className="text-[8px] font-bold uppercase tracking-widest text-white/20 hidden sm:inline">
                              Enter — send
                            </span>
                            <div className="relative" ref={layoutMenuRef}>
                              <button
                                type="button"
                                onClick={() => setLayoutMenuOpen((o) => !o)}
                                className={cn(
                                  "inline-flex items-center gap-1.5 h-7 pl-2.5 pr-2 rounded-md border text-[8px] font-black uppercase tracking-widest transition-colors",
                                  layoutMenuOpen
                                    ? "border-[#FF6B00]/50 bg-[#FF6B00]/10 text-[#FF6B00]"
                                    : "border-white/10 bg-white/[0.04] text-white/70 hover:border-white/20 hover:text-white",
                                )}
                                aria-expanded={layoutMenuOpen}
                                aria-haspopup="listbox"
                              >
                                {workbenchLayoutTriggerLabel(viewMode)}
                                <ChevronDown className={cn("h-3 w-3 opacity-60", layoutMenuOpen && "rotate-180")} />
                              </button>
                              {layoutMenuOpen ? (
                                <ul
                                  className="absolute right-0 bottom-full z-[200] mb-1 w-48 rounded-md border border-white/10 bg-[#0a0a0a] py-1 shadow-2xl"
                                  role="listbox"
                                >
                                  <li>
                                    <button
                                      type="button"
                                      role="option"
                                      className="flex w-full items-center gap-2 px-3 py-2 text-left text-[9px] font-black uppercase tracking-widest text-white/80 hover:bg-white/5"
                                      onClick={() => {
                                        setViewMode("split");
                                        setRequestedTabId("browser");
                                        setRequestedTabNonce((n) => n + 1);
                                        setBrowserOnly(true);
                                        setLayoutMenuOpen(false);
                                      }}
                                    >
                                      <Globe className="h-3.5 w-3.5 text-[#00E5FF]/80" />
                                      Browser
                                    </button>
                                  </li>
                                  <li>
                                    <button
                                      type="button"
                                      role="option"
                                      className={cn(
                                        "flex w-full items-center gap-2 px-3 py-2 text-left text-[9px] font-black uppercase tracking-widest hover:bg-white/5",
                                        viewMode === "split" ? "bg-[#FF6B00]/15 text-[#FF6B00]" : "text-white/80",
                                      )}
                                      onClick={() => {
                                        setViewMode("split");
                                        setBrowserOnly(false);
                                        setLayoutMenuOpen(false);
                                      }}
                                    >
                                      <Layout className="h-3.5 w-3.5 opacity-80" />
                                      Split
                                    </button>
                                  </li>
                                  <li>
                                    <button
                                      type="button"
                                      role="option"
                                      className={cn(
                                        "flex w-full items-center gap-2 px-3 py-2 text-left text-[9px] font-black uppercase tracking-widest hover:bg-white/5",
                                        viewMode === "preview" ? "bg-[#FF6B00]/15 text-[#FF6B00]" : "text-white/80",
                                      )}
                                      onClick={() => {
                                        setViewMode("preview");
                                        setBrowserOnly(false);
                                        setLayoutMenuOpen(false);
                                      }}
                                    >
                                      <Monitor className="h-3.5 w-3.5 opacity-80" />
                                      Preview
                                    </button>
                                  </li>
                                  <li>
                                    <button
                                      type="button"
                                      role="option"
                                      className={cn(
                                        "flex w-full items-center gap-2 px-3 py-2 text-left text-[9px] font-black uppercase tracking-widest hover:bg-white/5",
                                        viewMode === "war_room" ? "bg-[#FF6B00]/15 text-[#FF6B00]" : "text-white/80",
                                      )}
                                      onClick={() => {
                                        setViewMode("war_room");
                                        setBrowserOnly(false);
                                        setLayoutMenuOpen(false);
                                      }}
                                    >
                                      <Radar className="h-3.5 w-3.5 opacity-80" />
                                      War room
                                    </button>
                                  </li>
                                </ul>
                              ) : null}
                            </div>
                         </div>
                      </div>
                      <button type="submit" className="sr-only" tabIndex={-1}>
                        Send message
                      </button>
                   </div>
                </div>
             </form>
          </div>
        </div>
      </div>

      {/* Chat history sidebar overlay */}
      {historyOpen ? (
        <div className="fixed inset-0 z-[100] flex">
          <button
            type="button"
            aria-label="Close chat history"
            className="flex-1 bg-black/70 backdrop-blur-xl"
            onClick={() => setHistoryOpen(false)}
          />
          <div className="w-full max-w-md h-full border-l border-white/10 bg-[#0a0a0a]/95 backdrop-blur-xl shadow-2xl flex flex-col text-white">
            <div className="h-12 flex items-center justify-between px-4 border-b border-white/10 shrink-0">
              <div>
                <span className="text-[10px] font-black uppercase tracking-[0.2em] text-[#FF6B00]">HISTORY</span>
                <p className="text-[8px] text-white/30 mt-0.5">Chat sessions + server managed missions (HAM API)</p>
              </div>
              <div className="flex items-center gap-2">
                <button
                  type="button"
                  onClick={startNewChat}
                  className="flex items-center gap-1.5 px-3 py-1 text-[8px] font-black uppercase tracking-widest text-[#FF6B00] border border-[#FF6B00]/30 rounded hover:bg-[#FF6B00]/10 transition-colors"
                >
                  <Plus className="h-3 w-3" />
                  New
                </button>
                <button
                  type="button"
                  onClick={() => setHistoryOpen(false)}
                  className="p-1.5 text-white/40 hover:text-white"
                >
                  <X className="h-4 w-4" />
                </button>
              </div>
            </div>
            <div className="flex-1 overflow-y-auto p-4 space-y-6">
              <div>
                <p className="text-[9px] font-black uppercase tracking-widest text-[#00E5FF] mb-2">Managed missions (server)</p>
                <p className="text-[8px] text-white/25 mb-2 leading-relaxed">
                  Authoritative list from HAM&rsquo;s mission registry &mdash; use Open to focus this agent in Cloud (managed)
                  and land on <span className="text-white/40">Overview</span>.
                </p>
                {serverMissionsLoading ? (
                  <p className="text-[10px] text-white/30">Loading missions…</p>
                ) : serverMissions.length === 0 ? (
                  <p className="text-[10px] text-white/25">No managed missions on this API host yet.</p>
                ) : (
                  <ul className="space-y-2">
                    {serverMissions.filter((m) => (m.cursor_agent_id || "").trim()).map((m) => {
                      const aid = (m.cursor_agent_id || "").trim();
                      const reg = m.mission_registry_id ? `${m.mission_registry_id.slice(0, 8)}…` : "—";
                      const last = m.last_server_observed_at || m.updated_at;
                      return (
                        <li
                          key={m.mission_registry_id || aid}
                          className="border border-white/10 bg-white/[0.02] rounded-lg px-3 py-2.5"
                        >
                          <div className="flex items-start justify-between gap-2">
                            <div className="min-w-0 flex-1">
                              <p className="text-[8px] font-mono text-white/35 truncate" title={aid}>
                                {aid}
                              </p>
                              <p className="text-[10px] text-white/70 mt-0.5 truncate" title={m.repository_observed || m.repo_key || ""}>
                                {m.repo_key || m.repository_observed || "—"}
                              </p>
                              <p className="text-[8px] text-white/30 mt-1">
                                <span className="text-white/45">Status: </span>
                                {m.mission_lifecycle || "—"}
                                {m.cursor_status_last_observed ? (
                                  <span className="text-white/25"> · {m.cursor_status_last_observed}</span>
                                ) : null}
                              </p>
                              {last ? (
                                <p className="text-[7px] text-white/20 mt-0.5">Last seen (server): {last}</p>
                              ) : null}
                              <p className="text-[7px] text-white/15 mt-0.5 font-mono">registry {reg}</p>
                            </div>
                            <button
                              type="button"
                              onClick={() => openServerManagedMission(aid)}
                              className="shrink-0 text-[8px] font-black uppercase tracking-widest text-[#00E5FF] border border-[#00E5FF]/30 rounded px-2 py-1 hover:bg-[#00E5FF]/10"
                            >
                              Open
                            </button>
                          </div>
                        </li>
                      );
                    })}
                  </ul>
                )}
              </div>
              <div>
                <p className="text-[9px] font-black uppercase tracking-widest text-white/40 mb-2">Chat sessions</p>
                {historyLoading ? (
                  <p className="text-[10px] text-white/30">Loading…</p>
                ) : historySessions.length === 0 ? (
                  <p className="text-[10px] text-white/25">No past chats yet. Start a conversation and it'll appear here.</p>
                ) : (
                  <ul className="space-y-2">
                {historySessions.map((s) => (
                  <li key={s.session_id} className="list-none">
                  <button
                    type="button"
                    onClick={() => void loadSession(s.session_id)}
                    className={cn(
                      "w-full text-left border rounded-lg px-4 py-3 transition-colors group",
                      s.session_id === sessionId
                        ? "border-[#FF6B00]/40 bg-[#FF6B00]/10"
                        : "border-white/10 bg-white/[0.02] hover:border-white/20 hover:bg-white/5",
                    )}
                  >
                    <div className="flex items-center justify-between gap-2 mb-1">
                      <span className="text-[8px] font-mono text-white/30 truncate">
                        {s.session_id.slice(0, 8)}…
                      </span>
                      <span className="text-[8px] font-mono text-white/20 shrink-0">
                        {s.turn_count} msg{s.turn_count !== 1 ? "s" : ""}
                      </span>
                    </div>
                    <p className="text-[11px] font-bold text-white/70 group-hover:text-white/90 truncate leading-snug">
                      {s.preview || "Empty session"}
                    </p>
                    {s.created_at && (
                      <span className="text-[8px] text-white/20 mt-1 block">
                        {new Date(s.created_at).toLocaleString()}
                      </span>
                    )}
                  </button>
                  </li>
                ))}
                  </ul>
                )}
              </div>
            </div>
          </div>
        </div>
      ) : null}

      {projectsOpen ? (
        <div className="fixed inset-0 z-[100] flex">
          <button
            type="button"
            aria-label="Close projects"
            className="flex-1 bg-black/70 backdrop-blur-xl"
            onClick={closeProjectsPanel}
          />
          <ProjectsRegistryPanel
            mountRepo={mountRepo}
            setMountRepo={setMountRepo}
            mountRef={mountRef}
            setMountRef={setMountRef}
            activeCloudAgentId={activeCloudAgentId}
            setActiveCloudAgentIdLive={setActiveCloudAgentIdLive}
            onActiveMissionBlurCommit={(trimmed) => {
              if (trimmed) {
                activateCloudMission(trimmed, { managedSplit: { kind: "existing" } });
              }
            }}
            recentMissions={recentMissions}
            formatShortcutAge={formatShortcutAge}
            onShortcutUse={(id) => activateCloudMission(id, { managedSplit: { kind: "existing" } })}
            projects={hamProjects}
            projectsLoading={projectsLoading}
            onOpenActivity={() => {
              closeProjectsPanel();
              navigate("/activity");
            }}
            onBindProject={(pid) => {
              setProjectId(pid);
              closeProjectsPanel();
            }}
            onUpdateProjectDefaultPolicy={onUpdateProjectDefaultPolicy}
            activeCloudAgentIdForShortcut={activeCloudAgentId}
            onClose={closeProjectsPanel}
          />
        </div>
      ) : null}

      <CloudAgentLaunchModal
        open={cloudLaunchOpen}
        onClose={() => setCloudLaunchOpen(false)}
        defaultMissionHandling={cloudMissionHandling}
        onActivateMission={(id, opts) => activateCloudMission(id, opts)}
        recentMissions={recentMissions}
        onRemoveRecent={removeRecentMission}
        mountDefaults={mountDefaultsForLaunch}
        projectId={projectId}
      />
    </div>
    </ManagedCloudAgentProvider>
  );
}

export default function Chat() {
  const clerkPk = (import.meta.env.VITE_CLERK_PUBLISHABLE_KEY as string | undefined)?.trim();
  if (clerkPk) {
    return <ChatWithClerkSession />;
  }
  return <ChatPageInner getClerkSessionToken={async () => null} />;
}

function ChatWithClerkSession() {
  const { getToken } = useAuth();
  return <ChatPageInner getClerkSessionToken={() => getToken()} />;
}
