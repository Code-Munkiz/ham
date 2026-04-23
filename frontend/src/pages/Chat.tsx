/**
 * `/chat` workbench: **single owner** for layout, split state, and right execution pane.
 * `AppLayout` does not manage competing split logic for this route (see AppLayout comment).
 */
import * as React from "react";
import { useAuth } from "@clerk/clerk-react";
import {
  Paperclip,
  Sparkles,
  Shield,
  Activity,
  Zap,
  Monitor,
  Globe,
  Layout,
  ChevronDown,
  X,
  AlertCircle,
  Radar,
  History,
  Mic,
  MessageSquare,
  Plus,
} from "lucide-react";
import { toast } from "sonner";
import { useNavigate } from "react-router-dom";
import { cn } from "@/lib/utils";
import { ChatComposerStrip } from "@/components/chat/ChatComposerStrip";
import type { WorkbenchMode, UplinkId } from "@/components/chat/ChatComposerStrip";
import { CloudAgentLaunchModal } from "@/components/chat/CloudAgentLaunchModal";
import { applyHamUiActions } from "@/lib/ham/applyUiActions";
import {
  ensureProjectIdForWorkspaceRoot,
  fetchContextEngine,
  fetchCursorAgent,
  fetchCursorAgentConversation,
  fetchModelsCatalog,
  fetchProjectAgents,
  fetchChatSessions,
  fetchChatSession,
  listHamProjects,
  HamAccessRestrictedError,
  postChatStream,
  type HamChatStreamAuth,
  type HamOperatorResult,
  type ChatSessionSummary,
} from "@/lib/ham/api";
import {
  buildManagedCompletionMessage,
  completionInjectionSignature,
  isCloudAgentTerminal,
  MANAGED_CLOUD_AGENT_POLL_MS,
} from "@/lib/ham/managedCloudAgent";
import { CLIENT_MODEL_CATALOG_FALLBACK } from "@/lib/ham/modelCatalogFallback";
import type { CloudMissionHandling, ManagedMissionSnapshot, ModelCatalogPayload } from "@/lib/ham/types";
import { ManagedCloudAgentProvider } from "@/contexts/ManagedCloudAgentContext";
import { isDashboardChatGatewayReady } from "@/lib/ham/types";
import { useAgent } from "@/lib/ham/AgentContext";
import { useWorkspace } from "@/lib/ham/WorkspaceContext";
import { ExecutionSurfaceChrome } from "@/components/war-room/ExecutionSurfaceChrome";
import { ResizableWorkbenchSplit } from "@/components/war-room/ResizableWorkbenchSplit";
import { WarRoomPane } from "@/components/war-room/WarRoomPane";
import type { WarRoomTabId } from "@/components/war-room/uplinkConfig";

type ChatRow = {
  id: string;
  role: "user" | "assistant" | "system";
  content: string;
  timestamp: string;
};

type ChatViewMode = "chat" | "split" | "preview" | "war_room";

const RECENT_MISSIONS_KEY = "ham_recent_missions_v1";
const MOUNT_STORAGE_KEY = "ham_project_mount_v1";
const ACTIVE_CLOUD_AGENT_KEY = "ham_active_cloud_agent_id";
const CLOUD_MISSION_HANDLING_KEY = "ham_cloud_mission_handling";
const ACTIVE_SESSION_KEY = "ham_active_chat_session_id";
const MANAGED_COMPLETION_STORAGE_KEY = "ham_managed_completion_v1";

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
  return "View";
}

type TranscriptColumnProps = {
  messages: ChatRow[];
  primaryPersona: { name: string; avatarUrl: string | null } | null;
};

function TranscriptColumn({ messages, primaryPersona }: TranscriptColumnProps) {
  return (
    <div className="h-full min-h-0 flex flex-col overflow-hidden">
      <div className="flex-1 overflow-y-auto p-12 space-y-16 scrollbar-hide relative">
        <div className="max-w-3xl mx-auto space-y-16 pb-32">
          {messages.map((msg) => (
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
                    {msg.content}
                  </span>
                </div>
              </div>
            </div>
          ))}
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
  const [maxMode, setMaxMode] = React.useState(false);
  const [worker, setWorker] = React.useState("builder");
  const [projectId, setProjectId] = React.useState<string | null>(null);
  const [activeAgentNote, setActiveAgentNote] = React.useState<string | null>(null);
  const SETTINGS_OP_KEY = "ham_operator_settings_token";
  const LAUNCH_OP_KEY = "ham_operator_launch_token";
  const [operatorSettingsToken, setOperatorSettingsToken] = React.useState(() =>
    typeof sessionStorage !== "undefined"
      ? sessionStorage.getItem(SETTINGS_OP_KEY) ?? ""
      : "",
  );
  const [operatorLaunchToken, setOperatorLaunchToken] = React.useState(() =>
    typeof sessionStorage !== "undefined" ? sessionStorage.getItem(LAUNCH_OP_KEY) ?? "" : "",
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
  const [hamProjects, setHamProjects] = React.useState<{ id: string; name: string; root: string }[]>([]);
  const [projectsLoading, setProjectsLoading] = React.useState(false);
  const [warBlink, setWarBlink] = React.useState(true);
  const [reduceMotion, setReduceMotion] = React.useState(false);
  const [cloudLaunchOpen, setCloudLaunchOpen] = React.useState(false);
  const [managedLastSnapshot, setManagedLastSnapshot] = React.useState<ManagedMissionSnapshot | null>(null);
  const [managedSnapshotAt, setManagedSnapshotAt] = React.useState<number | null>(null);
  const [managedPollRefreshNonce, setManagedPollRefreshNonce] = React.useState(0);
  /** Latest gates for `processManagedAgentPollForCompletion` (read each call, no stale closure). */
  const managedCompletionGatesRef = React.useRef({
    uplinkId: "factory_ai" as UplinkId,
    cloudMissionHandling: "direct" as CloudMissionHandling,
    activeCloudAgentId: null as string | null,
  });

  /** Chat history sidebar */
  const [historyOpen, setHistoryOpen] = React.useState(false);
  const [historySessions, setHistorySessions] = React.useState<ChatSessionSummary[]>([]);
  const [historyLoading, setHistoryLoading] = React.useState(false);

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
    (id: string | null, opts?: { label?: string; mission_handling?: CloudMissionHandling }) => {
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
    },
    [pushRecentMission, cloudMissionHandling],
  );

  const onManagedSnapshotChange = React.useCallback((snapshot: ManagedMissionSnapshot | null) => {
    setManagedLastSnapshot(snapshot);
    setManagedSnapshotAt(snapshot ? Date.now() : null);
  }, []);

  const refreshManagedCloudMission = React.useCallback(() => {
    setManagedPollRefreshNonce((n) => n + 1);
  }, []);

  React.useEffect(() => {
    if (uplinkId !== "cloud_agent" || cloudMissionHandling !== "managed" || !activeCloudAgentId?.trim()) {
      setManagedLastSnapshot(null);
      setManagedSnapshotAt(null);
    }
  }, [uplinkId, cloudMissionHandling, activeCloudAgentId]);

  const managedCloudAgentContextValue = React.useMemo(
    () => ({
      activeCloudAgentId,
      cloudMissionHandling,
      lastSnapshot: managedLastSnapshot,
      lastUpdated: managedSnapshotAt,
      refresh: refreshManagedCloudMission,
    }),
    [
      activeCloudAgentId,
      cloudMissionHandling,
      managedLastSnapshot,
      managedSnapshotAt,
      refreshManagedCloudMission,
    ],
  );

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
          setHamProjects(
            r.projects.map((p) => ({ id: p.id, name: p.name ?? p.id, root: p.root })),
          );
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
    if (!import.meta.env.DEV) {
      const raw = import.meta.env.VITE_HAM_API_BASE as string | undefined;
      if (!raw?.trim()) {
        toast.error(
          "Chat needs a Ham API URL. Set VITE_HAM_API_BASE in Vercel (or your host) and redeploy — otherwise the app calls localhost and replies never arrive.",
          { duration: 12_000, id: "ham-api-base-missing" },
        );
      }
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

  /** Start a brand-new chat session. */
  const startNewChat = React.useCallback(() => {
    setSessionId(null);
    setMessages([]);
    setChatError(null);
    setHistoryOpen(false);
  }, []);

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

  React.useEffect(() => {
    if (uplinkId !== "cloud_agent" || cloudMissionHandling !== "managed") {
      try {
        localStorage.removeItem(MANAGED_COMPLETION_STORAGE_KEY);
      } catch {
        /* ignore */
      }
    }
  }, [uplinkId, cloudMissionHandling]);

  React.useEffect(() => {
    if (
      viewMode !== "chat" ||
      uplinkId !== "cloud_agent" ||
      cloudMissionHandling !== "managed" ||
      !activeCloudAgentId?.trim()
    ) {
      return;
    }
    let dead = false;
    const id = activeCloudAgentId.trim();
    const run = async () => {
      if (dead) return;
      try {
        const [agent, conv] = await Promise.all([
          fetchCursorAgent(id),
          fetchCursorAgentConversation(id),
        ]);
        if (dead) return;
        processManagedAgentPollForCompletion(agent, conv);
      } catch {
        /* fetch errors: no completion injection */
      }
    };
    void run();
    const t = window.setInterval(() => {
      if (!dead) void run();
    }, MANAGED_CLOUD_AGENT_POLL_MS);
    return () => {
      dead = true;
      window.clearInterval(t);
    };
  }, [
    viewMode,
    uplinkId,
    cloudMissionHandling,
    activeCloudAgentId,
    processManagedAgentPollForCompletion,
  ]);

  const applyOperatorResultSideEffects = React.useCallback((op: HamOperatorResult | null | undefined) => {
    if (!op?.handled) return;
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
  }, []);

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
          ...(modelId ? { model_id: modelId } : {}),
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
      applyOperatorResultSideEffects(res.operator_result);
      applyHamUiActions(res.actions ?? [], {
        navigate,
        setIsControlPanelOpen,
        isControlPanelOpen,
        setWorkbenchView: setViewMode,
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

  const handleSend = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!input.trim() || sending) return;
    const text = input.trim();
    if (viewMode === "preview") {
      setViewMode("chat");
    }
    setInput("");
    setChatError(null);

    const userRow: ChatRow = {
      id: `pending-user-${Date.now()}`,
      role: "user",
      content: text,
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

    setSending(true);
    try {
      const streamAuth: HamChatStreamAuth | undefined = clerkEnabled
        ? { sessionToken: await getClerkSessionToken() }
        : undefined;
      const res = await postChatStream(
        {
          session_id: sessionId ?? undefined,
          messages: [{ role: "user", content: text }],
          ...(modelId ? { model_id: modelId } : {}),
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
      applyOperatorResultSideEffects(res.operator_result);
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

  const pipelineStatus = `${uplinkPipelineLabel(uplinkId)} · ${workbenchMode.toUpperCase()} — ${
    sending ? "SENDING" : isDashboardChatGatewayReady(catalog) ? "GATEWAY_READY" : "GATEWAY_OFFLINE"
  }`;

  managedCompletionGatesRef.current = { uplinkId, cloudMissionHandling, activeCloudAgentId };

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

        {/* Dynamic Workbench Canvas: chat-only, preview full-width, or resizable split + uplink panes */}
        <div className="flex flex-1 min-h-0 flex-col relative overflow-hidden">
          {viewMode === "chat" ? (
            <TranscriptColumn messages={messages} primaryPersona={primaryPersona} />
          ) : viewMode === "preview" ? (
            <ExecutionSurfaceChrome
              mode="preview"
              onClose={() => setViewMode("chat")}
              browserOnly={browserOnly}
            >
              <WarRoomPane
                uplinkId={uplinkId}
                activeCloudAgentId={activeCloudAgentId}
                cloudMissionHandling={uplinkId === "cloud_agent" ? cloudMissionHandling : undefined}
                onManagedSnapshotChange={uplinkId === "cloud_agent" ? onManagedSnapshotChange : undefined}
                managedPollRefreshNonce={uplinkId === "cloud_agent" ? managedPollRefreshNonce : undefined}
                onManagedPollForCompletion={uplinkId === "cloud_agent" ? processManagedAgentPollForCompletion : undefined}
                embedUrl={paneEmbedUrl}
                onEmbedUrlChange={setPaneEmbedUrl}
                requestedTabId={requestedTabId}
                requestedTabNonce={requestedTabNonce}
                browserOnly={browserOnly}
              />
            </ExecutionSurfaceChrome>
          ) : (
            <ResizableWorkbenchSplit
              left={<TranscriptColumn messages={messages} primaryPersona={primaryPersona} />}
              right={
                <ExecutionSurfaceChrome
                  mode={viewMode === "war_room" ? "war_room" : "split"}
                  onClose={() => setViewMode("chat")}
                  warRoomSignal={viewMode === "war_room"}
                  reduceMotion={reduceMotion}
                  warBlink={warBlink}
                  browserOnly={browserOnly}
                >
                  <WarRoomPane
                    uplinkId={uplinkId}
                    activeCloudAgentId={activeCloudAgentId}
                    cloudMissionHandling={uplinkId === "cloud_agent" ? cloudMissionHandling : undefined}
                    onManagedSnapshotChange={uplinkId === "cloud_agent" ? onManagedSnapshotChange : undefined}
                    managedPollRefreshNonce={uplinkId === "cloud_agent" ? managedPollRefreshNonce : undefined}
                    onManagedPollForCompletion={uplinkId === "cloud_agent" ? processManagedAgentPollForCompletion : undefined}
                    embedUrl={paneEmbedUrl}
                    onEmbedUrlChange={setPaneEmbedUrl}
                    requestedTabId={requestedTabId}
                    requestedTabNonce={requestedTabNonce}
                    browserOnly={browserOnly}
                  />
                </ExecutionSurfaceChrome>
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
                <div
                  className="pointer-events-none absolute -inset-0.5 z-0 rounded-xl bg-gradient-to-r from-[#FF6B00]/15 to-[#FF6B00]/5 opacity-15 blur-md transition duration-500 group-focus-within:opacity-50"
                  aria-hidden
                />
                <div className="relative z-10 flex flex-col overflow-visible rounded-lg border border-white/10 bg-[#0d0d0d] shadow-xl">
                   <div className="relative z-20 rounded-t-lg bg-black/35">
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
                        toolsCount={selectedAgent.assignedTools?.length ?? 0}
                        onOpenCloudAgentLaunch={() => setCloudLaunchOpen(true)}
                        catalog={catalog}
                        catalogLoading={catalogLoading}
                      />
                   </div>
                   <div className="flex flex-col border-t border-white/5">
                      <div className="flex items-start px-4 pt-2 pb-2 gap-2">
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
                              className="flex items-center gap-1.5 text-[8px] text-white/25 hover:text-[#FF6B00] font-black uppercase tracking-widest transition-colors px-1.5 py-1 rounded"
                            >
                               <Paperclip className="h-3 w-3" />
                               Attach
                            </button>
                            <button
                              type="button"
                              title="Dictation (browser-dependent)"
                              className="flex items-center gap-1.5 text-[8px] text-white/25 hover:text-[#FF6B00] font-black uppercase tracking-widest transition-colors px-1.5 py-1 rounded"
                            >
                               <Mic className="h-3 w-3" />
                               Mic
                            </button>
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
              <span className="text-[10px] font-black uppercase tracking-[0.2em] text-[#FF6B00]">CHAT_HISTORY</span>
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
            <div className="flex-1 overflow-y-auto p-4 space-y-2">
              {historyLoading ? (
                <p className="text-[10px] text-white/30">Loading…</p>
              ) : historySessions.length === 0 ? (
                <p className="text-[10px] text-white/25">No past chats yet. Start a conversation and it'll appear here.</p>
              ) : (
                historySessions.map((s) => (
                  <button
                    key={s.session_id}
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
                ))
              )}
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
            onClick={() => {
              try {
                localStorage.setItem(
                  MOUNT_STORAGE_KEY,
                  JSON.stringify({ repository: mountRepo.trim(), ref: mountRef.trim() }),
                );
              } catch {
                /* ignore */
              }
              setProjectsOpen(false);
            }}
          />
          <div className="w-full max-w-md h-full border-l border-white/10 bg-[#0a0a0a]/95 backdrop-blur-xl shadow-2xl flex flex-col text-white">
            <div className="h-12 flex items-center justify-between px-4 border-b border-white/10 shrink-0">
              <span className="text-[10px] font-black uppercase tracking-[0.2em] text-[#BC13FE]">PROJECTS_REGISTRY</span>
              <button
                type="button"
                onClick={() => {
                  try {
                    localStorage.setItem(
                      MOUNT_STORAGE_KEY,
                      JSON.stringify({ repository: mountRepo.trim(), ref: mountRef.trim() }),
                    );
                  } catch {
                    /* ignore */
                  }
                  setProjectsOpen(false);
                }}
                className="p-1.5 text-white/40 hover:text-white"
              >
                <X className="h-4 w-4" />
              </button>
            </div>
            <div className="flex-1 overflow-y-auto p-4 space-y-6">
              <div>
                <div className="flex items-center justify-between mb-2">
                  <span className="text-[9px] font-black uppercase tracking-widest text-white/40">PROJECT_MOUNT</span>
                </div>
                <label className="text-[8px] font-black text-white/30 uppercase block mb-1">GitHub repository URL</label>
                <input
                  value={mountRepo}
                  onChange={(e) => setMountRepo(e.target.value)}
                  placeholder="https://github.com/org/repo"
                  className="w-full bg-black/50 border border-white/10 px-3 py-2 text-[11px] text-white/90 mb-3 outline-none focus:border-[#FF6B00]/40"
                />
                <label className="text-[8px] font-black text-white/30 uppercase block mb-1">Ref (branch / tag)</label>
                <input
                  value={mountRef}
                  onChange={(e) => setMountRef(e.target.value)}
                  placeholder="main"
                  className="w-full bg-black/50 border border-white/10 px-3 py-2 text-[11px] text-white/90 outline-none focus:border-[#FF6B00]/40"
                />
              </div>
              <div>
                <span className="text-[9px] font-black uppercase tracking-widest text-white/40 block mb-2">
                  CLOUD_AGENT_ACTIVE_MISSION
                </span>
                <p className="text-[9px] text-white/25 mb-2 leading-relaxed">
                  Active mission id for tracker / transcript. Leave empty for not connected / no active mission. You can also
                  use Launch in the chat bar (Cloud uplink).
                </p>
                <input
                  value={activeCloudAgentId ?? ""}
                  onChange={(e) => setActiveCloudAgentIdLive(e.target.value.trim() || null)}
                  onBlur={(e) => {
                    const v = e.target.value.trim();
                    if (v) activateCloudMission(v);
                  }}
                  placeholder="Cursor agent id…"
                  className="w-full bg-black/50 border border-white/10 px-3 py-2 text-[11px] text-white/90 font-mono outline-none focus:border-[#FF6B00]/40"
                />
              </div>
              <div>
                <span className="text-[9px] font-black uppercase tracking-widest text-white/40 block mb-2">
                  Registered HAM projects
                </span>
                {projectsLoading ? (
                  <p className="text-[10px] text-white/30">Loading…</p>
                ) : hamProjects.length === 0 ? (
                  <p className="text-[10px] text-white/25">No projects registered on this API.</p>
                ) : (
                  <ul className="space-y-2">
                    {hamProjects.map((p) => (
                      <li
                        key={p.id}
                        className="border border-white/10 px-3 py-2 text-[10px] font-mono text-white/60 truncate"
                        title={p.root}
                      >
                        {p.name}
                      </li>
                    ))}
                  </ul>
                )}
              </div>
              <div>
                <span className="text-[9px] font-black uppercase tracking-widest text-white/40 block mb-2">
                  RECENT_MISSIONS
                </span>
                {recentMissions.length === 0 ? (
                  <p className="text-[10px] text-white/25">No stored missions yet.</p>
                ) : (
                  <ul className="space-y-2">
                    {[...recentMissions]
                      .sort((a, b) => b.t - a.t)
                      .map((m) => (
                        <li
                          key={m.id}
                          className="flex items-center justify-between gap-2 border border-white/10 px-3 py-2 text-[9px] text-white/50"
                        >
                          <span className="min-w-0 truncate">
                            <span className="font-mono text-[#00E5FF]">{m.id}</span>
                            {m.label ? ` · ${m.label}` : ""}
                          </span>
                          <button
                            type="button"
                            className="shrink-0 text-[8px] font-black uppercase tracking-wider text-[#FF6B00] hover:text-white"
                            onClick={() => activateCloudMission(m.id)}
                          >
                            Use
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

      <CloudAgentLaunchModal
        open={cloudLaunchOpen}
        onClose={() => setCloudLaunchOpen(false)}
        defaultMissionHandling={cloudMissionHandling}
        onActivateMission={(id, opts) => activateCloudMission(id, opts)}
        recentMissions={recentMissions}
        onRemoveRecent={removeRecentMission}
        mountDefaults={mountDefaultsForLaunch}
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
