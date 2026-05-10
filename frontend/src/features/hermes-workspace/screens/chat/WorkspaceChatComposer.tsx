/**
 * Hermes Workspace chat: upstream-style PromptInput shell — `PromptInput` in repomix
 * uses `var(--composer-bg)` + `rounded-3xl` + `PromptInputTextarea` then `PromptInputActions` with
 * attach + model (left) and mic + send (right). v2 attachment uploads go through `POST /api/chat/attachments`.
 */

import * as React from "react";
import { ArrowUp, ChevronRight, Lightbulb, Link2, Loader2, Sparkles, X } from "lucide-react";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import type {
  ChatContextMetersPayload,
  ChatCapabilitiesPayload,
  ModelCatalogItem,
  ModelCatalogPayload,
} from "@/lib/ham/types";
import { humanizeHermesCatalogId } from "@/features/hermes-workspace/lib/workspaceHumanLabels";
import { isDashboardChatGatewayReady } from "@/lib/ham/types";
import { WorkspaceVoiceMessageInput } from "./WorkspaceVoiceMessageInput";
import { toast } from "sonner";
import {
  WorkspaceChatComposerActionsMenu,
  type ComposerExportPdfState,
  type ComposerGenerateImageState,
  type ComposerGenerateVideoState,
} from "./WorkspaceChatComposerActionsMenu";
import { WorkspaceChatAttachmentPreviewList } from "./WorkspaceChatAttachmentPreview";
import {
  type WorkspaceComposerAttachment,
  MAX_WORKSPACE_ATTACHMENT_COUNT,
} from "./composerAttachmentHelpers";
import { ContextMeterCluster } from "./ContextMeterCluster";
import { WorkspaceOpenRouterModelPicker } from "./WorkspaceOpenRouterModelPicker";
import type { SuggestionChip } from "./WorkspaceChatEmptyState";

const VOICE_DEBUG_FLAG = "ham.voiceDebug";

function voiceDebugEnabled(): boolean {
  if (typeof window === "undefined") return false;
  try {
    return window.localStorage.getItem(VOICE_DEBUG_FLAG) === "1";
  } catch {
    return false;
  }
}

function pushVoiceDebug(payload: Record<string, unknown>): void {
  if (!voiceDebugEnabled() || typeof window === "undefined") return;
  const event = { ...payload, ts: Date.now() };
  const w = window as unknown as { __HAM_VOICE_DEBUG__?: Array<Record<string, unknown>> };
  const arr = Array.isArray(w.__HAM_VOICE_DEBUG__) ? [...w.__HAM_VOICE_DEBUG__, event] : [event];
  if (arr.length > 500) arr.splice(0, arr.length - 500);
  w.__HAM_VOICE_DEBUG__ = arr;
  console.debug("[ham.voice]", event);
}

export type WorkspaceGohamDesktopChipProps = {
  linked: boolean;
  /** True while modal is checking or running trusted connect — chip shows spinner. */
  busy?: boolean;
  onOpenModal: () => void;
};

type WorkspaceChatComposerProps = {
  value: string;
  onChange: (v: string) => void;
  onSubmit: () => void;
  disabled: boolean;
  sending: boolean;
  voiceTranscribing: boolean;
  onVoiceBlob: (blob: Blob) => void;
  attachments: WorkspaceComposerAttachment[];
  onAddAttachments: (files: File[]) => void;
  onRemoveAttachment: (id: string) => void;
  onRetryAttachmentUpload?: (id: string) => void | Promise<void>;
  /** Clipboard / OS paste — image or file payloads from the textarea */
  onPasteFiles?: (files: File[]) => void;
  catalog: ModelCatalogPayload | null;
  modelId: string | null;
  onModelIdChange: (id: string | null) => void;
  /** When false, mic is off (persisted workspace Voice → STT disabled). Default true if omitted. */
  sttDictationEnabled?: boolean;
  sttUnavailableReason?: string | null;
  sttMode?: "auto" | "live" | "record";
  onSttModeChange?: (mode: "auto" | "live" | "record") => Promise<void> | void;
  /** Windows Desktop shell: GOHAM local web bridge entry (trusted connect via preload). */
  gohamDesktopChip?: WorkspaceGohamDesktopChipProps | null;
  /** Capability copy from `GET /api/chat/capabilities` — optional. */
  chatCapabilities?: ChatCapabilitiesPayload | null;
  exportPdf: ComposerExportPdfState;
  generateImage: ComposerGenerateImageState;
  generateVideo: ComposerGenerateVideoState;
  /** When true, show context meter rings before voice/send. */
  contextMetersEnabled?: boolean;
  contextMetersPayload?: ChatContextMetersPayload | null;
  /** Models that failed with OPENROUTER_MODEL_REJECTED this session (picker hint only). */
  failedChatModelIds?: ReadonlySet<string> | null;
  /** Horizontally scrolling starter prompts above the deck (similar to Cursor’s AI shortcuts row). */
  quickSuggestions?: readonly SuggestionChip[] | null;
  /** Runs when a starter prompt pill is clicked (typically sends the bundled prompt immediately). */
  onQuickSuggestion?: (prompt: string) => void;
  /** When this identity changes (e.g. chat session id), the dismissible starter row is shown again. */
  quickTipsResetSignal?: string | null;
};

const COMPOSER_MENU_FOOTER_HINT =
  "Docs/spreadsheets text-extracted; videos stored only (no transcript yet). OCR/video vision not yet.";

/** Tooltip-only: full honesty without bloating the menu panel. */
function attachMenuCapabilityTitle(
  caps: ChatCapabilitiesPayload | null | undefined,
): string | null {
  if (!caps) return null;
  const lines = [...(caps.limitations ?? [])];
  if (caps.notes?.trim()) lines.push(caps.notes.trim());
  const text = lines.join(" ");
  return text.length ? text : null;
}

function modelDetailTitle(
  catalog: ModelCatalogPayload | null,
  modelId: string | null,
  caps: ChatCapabilitiesPayload | null | undefined,
): string | null {
  const pill = primaryModelPillText(catalog, modelId);
  if (!caps?.limitations?.length) return pill;
  const extra = caps.limitations.slice(0, 2).join(" ");
  return pill ? `${pill} — ${extra}` : extra;
}

function attachMenuDisabledReason(
  uploadsPending: boolean,
  voiceBusy: boolean,
  sending: boolean,
  composerDisabled: boolean,
): string | null {
  if (uploadsPending) return "Wait for uploads";
  if (voiceBusy) return "Finish voice first";
  if (sending) return "Sending…";
  if (composerDisabled) return "Composer locked";
  return null;
}

type VoiceUiState = "idle" | "recording" | "live" | "stopping" | "transcribing" | "error";

function chatModelPickerRows(c: ModelCatalogPayload | null): ModelCatalogItem[] {
  if (!c?.items?.length) return [];
  return c.items.filter((x) => !x.id.startsWith("cursor:"));
}

function primaryModelPillText(
  catalog: ModelCatalogPayload | null,
  modelId: string | null,
): string | null {
  if (!catalog) return null;
  if (modelId) {
    const it = catalog.items.find((i) => i.id === modelId);
    if (it) return it.label || it.id;
    return modelId;
  }
  const m = (catalog.gateway_mode || "").toLowerCase();
  if (m === "http" && catalog.http_chat_model_primary) {
    const raw = catalog.http_chat_model_primary.trim();
    const nicer = humanizeHermesCatalogId(raw);
    return nicer || raw;
  }
  const first = catalog.items.find((i) => i.supports_chat);
  return first ? first.label || first.id : null;
}

function collectComposerPasteFiles(dt: DataTransfer | null): File[] {
  if (!dt) return [];
  const out: File[] = [];
  const seen = new Set<string>();
  if (dt.files?.length) {
    for (let i = 0; i < dt.files.length; i += 1) {
      const f = dt.files.item(i);
      if (!f) continue;
      const key = `${f.name}\0${f.size}\0${f.type}`;
      if (seen.has(key)) continue;
      seen.add(key);
      out.push(f);
    }
  }
  if (dt.items?.length) {
    for (let i = 0; i < dt.items.length; i += 1) {
      const it = dt.items[i];
      if (!it || it.kind !== "file") continue;
      const f = it.getAsFile();
      if (!f) continue;
      const key = `${f.name}\0${f.size}\0${f.type}`;
      if (seen.has(key)) continue;
      seen.add(key);
      out.push(f);
    }
  }
  return out;
}

function ComposerQuickTipsBar({
  suggestions,
  composerBusy,
  onPick,
  onDismiss,
}: {
  suggestions: readonly SuggestionChip[];
  composerBusy: boolean;
  onPick: (prompt: string) => void;
  onDismiss: () => void;
}) {
  const scrollRef = React.useRef<HTMLDivElement | null>(null);
  const [canScrollAhead, setCanScrollAhead] = React.useState(false);

  const syncOverflow = React.useCallback(() => {
    const el = scrollRef.current;
    if (!el) return;
    const { scrollLeft, scrollWidth, clientWidth } = el;
    const overflow = scrollWidth > clientWidth + 1;
    const remainder = scrollWidth - scrollLeft - clientWidth;
    const next = overflow && remainder > 2;
    setCanScrollAhead(next);
  }, []);

  React.useLayoutEffect(() => {
    syncOverflow();
  }, [syncOverflow, suggestions.length]);

  React.useEffect(() => {
    const el = scrollRef.current;
    if (!el || typeof ResizeObserver === "undefined") return;
    const ro = new ResizeObserver(() => syncOverflow());
    ro.observe(el);
    el.addEventListener("scroll", syncOverflow, { passive: true });
    return () => {
      ro.disconnect();
      el.removeEventListener("scroll", syncOverflow);
    };
  }, [syncOverflow, suggestions.length]);

  const scrollStarterPromptsAhead = React.useCallback(() => {
    const el = scrollRef.current;
    if (!el) return;
    const dx = Math.max(120, Math.round(el.clientWidth * 0.65));
    el.scrollBy({ left: dx, behavior: "smooth" });
    window.requestAnimationFrame(() => syncOverflow());
  }, [syncOverflow]);

  return (
    <div
      role="toolbar"
      aria-label="Starter prompts"
      data-hww-composer-quick-tips
      data-hww-composer-quick-tips-overflow={canScrollAhead ? "scrollable" : "idle"}
      className="mb-2 flex min-h-9 max-w-full min-w-0 items-center gap-2 overflow-x-hidden"
    >
      <Lightbulb
        className="my-1 h-4 w-4 shrink-0 text-amber-200/75"
        strokeWidth={1.75}
        aria-hidden
      />
      <div
        ref={scrollRef}
        data-hww-composer-quick-tips-scroll
        className="-mx-0.5 flex min-w-0 flex-1 items-center gap-2 overflow-x-auto overflow-y-hidden hww-composer-quick-tips-scroll"
      >
        <span
          className="inline-flex shrink-0 items-center gap-1.5 rounded-full border border-white/[0.09] bg-white/[0.03] px-2.5 py-1 text-[10px] font-semibold uppercase tracking-wide text-white/45"
          aria-hidden
        >
          <Sparkles className="h-3 w-3 text-sky-300/80" strokeWidth={1.85} aria-hidden />
          Quick prompts
        </span>
        {suggestions.map((s) => {
          const Icon = s.icon;
          return (
            <button
              key={s.label}
              type="button"
              disabled={composerBusy}
              onClick={() => onPick(s.prompt)}
              title={s.label}
              className={cn(
                "inline-flex max-w-[min(100%,240px)] shrink-0 cursor-pointer items-center gap-2 rounded-full border border-white/[0.1]",
                "bg-white/[0.04] px-3 py-1.5 text-left text-[11px] font-medium text-[#e4edf4] outline-none ring-emerald-500/30 transition",
                "hover:border-emerald-500/35 hover:bg-white/[0.07] hover:text-white disabled:cursor-not-allowed disabled:opacity-40",
                "focus-visible:ring-2",
              )}
            >
              <Icon className="h-3.5 w-3.5 shrink-0 text-emerald-300/85" strokeWidth={1.5} />
              <span className="min-w-0 truncate">{s.label}</span>
            </button>
          );
        })}
      </div>
      {canScrollAhead ? (
        <button
          type="button"
          aria-label="Show more starter prompts"
          title="Scroll starter prompts"
          data-hww-composer-quick-tips-scroll-next
          data-hww-composer-quick-tips-scroll-next-active="true"
          onClick={scrollStarterPromptsAhead}
          className={cn(
            "inline-flex h-6 min-h-6 w-6 min-w-6 shrink-0 cursor-pointer items-center justify-center rounded-md border border-white/[0.08] bg-white/[0.03] text-white/80 outline-none transition",
            "hover:border-white/[0.16] hover:bg-white/[0.06] hover:text-white",
            "focus-visible:border-emerald-400/35 focus-visible:ring-2 focus-visible:ring-emerald-400/35",
          )}
        >
          <ChevronRight className="h-3 w-3 shrink-0" strokeWidth={2.25} aria-hidden />
        </button>
      ) : null}
      <Button
        type="button"
        variant="ghost"
        size="icon"
        className="size-8 min-h-8 min-w-8 shrink-0 text-white/50 hover:bg-white/[0.06] hover:text-white"
        aria-label="Hide starter prompts"
        title="Hide starter prompts"
        onClick={onDismiss}
      >
        <X className="h-4 w-4" strokeWidth={1.75} />
      </Button>
    </div>
  );
}

export function WorkspaceChatComposer({
  value,
  onChange,
  onSubmit,
  disabled,
  sending,
  voiceTranscribing,
  onVoiceBlob,
  attachments,
  onAddAttachments,
  onRemoveAttachment,
  onRetryAttachmentUpload,
  onPasteFiles,
  catalog,
  modelId,
  onModelIdChange,
  sttDictationEnabled = true,
  sttUnavailableReason = null,
  sttMode = "record",
  onSttModeChange,
  gohamDesktopChip = null,
  chatCapabilities = null,
  exportPdf,
  generateImage,
  generateVideo,
  contextMetersEnabled = false,
  contextMetersPayload = null,
  failedChatModelIds = null,
  quickSuggestions = null,
  onQuickSuggestion,
  quickTipsResetSignal = null,
}: WorkspaceChatComposerProps) {
  const [quickTipsDismissed, setQuickTipsDismissed] = React.useState(false);
  const [voiceState, setVoiceState] = React.useState<VoiceUiState>("idle");
  const [voiceBanner, setVoiceBanner] = React.useState<string | null>(null);
  const [isDragging, setIsDragging] = React.useState(false);
  const transitionVoiceState = React.useCallback((next: VoiceUiState, reason: string) => {
    setVoiceState((prev) => {
      if (prev === next) return prev;
      pushVoiceDebug({
        event: "voice.state.transition",
        component: "WorkspaceChatComposer",
        composerInstanceId: composerInstanceId.current,
        from: prev,
        to: next,
        reason,
      });
      return next;
    });
  }, []);

  const [liveListening, setLiveListening] = React.useState(false);
  const liveBaseDraftRef = React.useRef<string>("");
  const liveCommittedDraftRef = React.useRef<string>("");
  const liveInterimDraftRef = React.useRef<string>("");
  const voiceRecording = voiceState === "recording";
  const voiceStopping = voiceState === "stopping";
  const voiceLive = voiceState === "live";
  const voiceBusy = voiceRecording || voiceStopping || voiceTranscribing || voiceLive;

  const composerInstanceId = React.useRef(`composer-${Math.random().toString(36).slice(2, 9)}`);
  const stopVoiceRecorderRef = React.useRef<(() => void) | null>(null);
  const stopRequestedRef = React.useRef(false);
  const stopTimeoutRef = React.useRef<ReturnType<typeof setTimeout> | null>(null);
  const outerRef = React.useRef<HTMLDivElement>(null);
  const textareaWrapRef = React.useRef<HTMLDivElement>(null);
  const textareaRef = React.useRef<HTMLTextAreaElement>(null);
  const modelPickerTriggerRef = React.useRef<HTMLButtonElement>(null);
  const dragDepthRef = React.useRef(0);
  const TEXTAREA_MAX_PX = 240;
  type ComposerToolbarDensity = "comfortable" | "compact" | "tight";
  const [composerToolbarDensity, setComposerToolbarDensity] =
    React.useState<ComposerToolbarDensity>("comfortable");

  const clearStopTimeout = React.useCallback(() => {
    if (stopTimeoutRef.current) {
      clearTimeout(stopTimeoutRef.current);
      stopTimeoutRef.current = null;
    }
  }, []);

  const beginStopRequest = React.useCallback(
    (reason: string) => {
      stopRequestedRef.current = true;
      pushVoiceDebug({
        event: "voice.stop.requested",
        component: "WorkspaceChatComposer",
        composerInstanceId: composerInstanceId.current,
        reason,
        voiceState,
      });
      transitionVoiceState("stopping", reason);
      clearStopTimeout();
      pushVoiceDebug({
        event: "voice.stop.timeout_started",
        component: "WorkspaceChatComposer",
        composerInstanceId: composerInstanceId.current,
      });
      stopTimeoutRef.current = setTimeout(() => {
        if (!stopRequestedRef.current) return;
        pushVoiceDebug({
          event: "voice.stop.timeout",
          component: "WorkspaceChatComposer",
          composerInstanceId: composerInstanceId.current,
        });
        pushVoiceDebug({
          event: "voice.stop.force_idle",
          component: "WorkspaceChatComposer",
          composerInstanceId: composerInstanceId.current,
        });
        transitionVoiceState("idle", "stop_timeout_forced_idle");
        setVoiceBanner("Recording stop timed out. Please try again.");
        stopRequestedRef.current = false;
      }, 3000);
    },
    [clearStopTimeout, transitionVoiceState, voiceState],
  );

  const syncTextareaHeight = React.useCallback(() => {
    const el = textareaRef.current;
    if (!el) return;
    el.style.height = "auto";
    const sh = el.scrollHeight;
    const h = Math.min(sh, TEXTAREA_MAX_PX);
    el.style.height = `${h}px`;
    el.style.overflowY = sh > TEXTAREA_MAX_PX ? "auto" : "hidden";
  }, [TEXTAREA_MAX_PX]);

  React.useLayoutEffect(() => {
    syncTextareaHeight();
  }, [value, syncTextareaHeight]);

  React.useLayoutEffect(() => {
    const el = outerRef.current;
    if (!el) return;
    const readOuterWidthPx = () => {
      const self = el.offsetWidth;
      if (self > 0) return self;
      const rectW = Math.round(el.getBoundingClientRect()?.width ?? 0);
      if (rectW > 0) return rectW;
      const p = el.parentElement;
      const fromParent = p?.clientWidth ?? 0;
      return fromParent > 0 ? fromParent : self;
    };
    const applyLayoutMetrics = () => {
      const h = el.offsetHeight;
      if (h > 0) {
        document.documentElement.style.setProperty("--hww-chat-composer-height", `${h}px`);
      }
      const w = readOuterWidthPx();
      let next: ComposerToolbarDensity = "comfortable";
      if (w > 0 && w < 400) next = "tight";
      else if (w > 0 && w < 500) next = "compact";
      setComposerToolbarDensity((prev) => (prev === next ? prev : next));
    };
    const ro = new ResizeObserver(() => {
      applyLayoutMetrics();
    });
    ro.observe(el);
    applyLayoutMetrics();
    return () => {
      ro.disconnect();
    };
  }, [attachments.length, value, voiceRecording, voiceState, voiceTranscribing]);

  React.useEffect(() => {
    setQuickTipsDismissed(false);
  }, [quickTipsResetSignal]);

  React.useEffect(() => {
    if (voiceRecording) setVoiceBanner(null);
  }, [voiceRecording]);

  React.useEffect(() => {
    if (!liveListening) return;
    transitionVoiceState("live", "live_dictation_started");
    setVoiceBanner(null);
  }, [liveListening, transitionVoiceState]);

  React.useEffect(() => {
    if (liveListening) return;
    setVoiceState((prev) => {
      if (prev === "live") return "idle";
      return prev;
    });
  }, [liveListening]);

  React.useEffect(() => {
    if (voiceTranscribing) {
      transitionVoiceState("transcribing", "transcribe_started");
      return;
    }
    setVoiceState((prev) => {
      if (prev === "transcribing" || prev === "stopping" || prev === "live") {
        pushVoiceDebug({
          event: "voice.state.transition",
          component: "WorkspaceChatComposer",
          composerInstanceId: composerInstanceId.current,
          from: prev,
          to: "idle",
          reason: "transcribe_finished",
        });
        stopRequestedRef.current = false;
        clearStopTimeout();
        return "idle";
      }
      return prev;
    });
  }, [clearStopTimeout, transitionVoiceState, voiceTranscribing]);

  React.useEffect(() => {
    return () => {
      clearStopTimeout();
    };
  }, [clearStopTimeout]);

  React.useEffect(() => {
    pushVoiceDebug({
      event: "voice.render",
      component: "WorkspaceChatComposer",
      composerInstanceId: composerInstanceId.current,
      voiceState,
      voiceTranscribing,
    });
  }, [voiceState, voiceTranscribing]);

  const gm = catalog ? (catalog.gateway_mode || "").toLowerCase() : "";
  const byokOr = catalog?.openrouter_user_byok_connected === true;
  const pickerRows = chatModelPickerRows(catalog);
  const showModel = Boolean(
    catalog && pickerRows.length > 0 && (gm === "openrouter" || gm === "http" || gm === "mock"),
  );
  const byokPickerActive = gm === "http" && byokOr === true && Boolean(modelId);
  const gatewayOk = isDashboardChatGatewayReady(catalog);
  const modelPill = primaryModelPillText(catalog, modelId);
  const modelDetail = modelDetailTitle(catalog, modelId, chatCapabilities);
  const attachDetailsTitle = attachMenuCapabilityTitle(chatCapabilities);
  const uploadsPending = attachments.some((a) => a.uploadPhase === "uploading");
  const hasAttachErrOnly =
    attachments.length > 0 &&
    attachments.every((a) => Boolean(a.error) || a.uploadPhase === "failed") &&
    !value.trim();
  const allAttachmentsFailed =
    attachments.length > 0 &&
    attachments.every((a) => Boolean(a.error) || a.uploadPhase === "failed");
  const normalSendReady =
    gatewayOk && (value.trim() || (attachments.length > 0 && !hasAttachErrOnly));
  const canSend =
    !allAttachmentsFailed && !uploadsPending && normalSendReady && !sending && !voiceBusy;

  const sendButtonTitle = React.useMemo(() => {
    if (canSend) return "Send message (Enter)";
    if (voiceTranscribing) return "Wait for transcription to finish";
    if (voiceLive) return "Stop live dictation before sending";
    if (voiceRecording || voiceStopping) return "Stop recording before sending";
    if (uploadsPending) return "Wait for uploads to finish";
    if (allAttachmentsFailed) return "Fix or remove failed attachments";
    if (!normalSendReady && gatewayOk) return "Type a message or add attachments";
    if (!gatewayOk) return "Chat gateway not ready";
    if (sending) return "Sending…";
    return "Cannot send yet";
  }, [
    allAttachmentsFailed,
    canSend,
    gatewayOk,
    normalSendReady,
    sending,
    uploadsPending,
    voiceLive,
    voiceRecording,
    voiceStopping,
    voiceTranscribing,
  ]);

  const micColumnTitle = React.useMemo(() => {
    if (voiceTranscribing) return "Transcribing… — microphone unavailable until done";
    if (sttMode === "record") return "Record then transcribe (right-click for mode)";
    if (sttMode === "live") return "Live dictation (right-click for mode)";
    return "Auto dictation (right-click for mode)";
  }, [sttMode, voiceTranscribing]);

  const contextAccent = React.useMemo((): "red" | "amber" | "green" | null => {
    if (!contextMetersEnabled || !contextMetersPayload?.enabled) return null;
    const cols = [
      contextMetersPayload.this_turn?.color,
      contextMetersPayload.workspace?.color,
      contextMetersPayload.thread?.color,
    ];
    if (cols.includes("red")) return "red";
    if (cols.includes("amber")) return "amber";
    if (cols.includes("green")) return "green";
    return null;
  }, [contextMetersEnabled, contextMetersPayload]);

  const deckBorder = React.useMemo(() => {
    if (contextAccent === "red") return "1px solid rgba(248, 113, 113, 0.22)";
    if (contextAccent === "amber") return "1px solid rgba(251, 191, 36, 0.2)";
    if (contextAccent === "green") return "1px solid rgba(16, 185, 129, 0.2)";
    return "1px solid rgba(16, 185, 129, 0.14)";
  }, [contextAccent]);

    if (voiceTranscribing) return "Transcribing…";
    if (!gatewayOk && catalog && !sending)
      return "Chat gateway not ready — check the API model settings.";
    const macLike =
      typeof navigator !== "undefined" && /Mac|iPhone|iPad|iPod/.test(navigator.userAgent || "");
    const mod = macLike ? "⌘⇧M" : "Ctrl+Shift+M";
    return `Ask anything... (↵ to send · ⇧↵ new line · ${mod} switch model)`;
  }, [catalog, gatewayOk, sending, voiceTranscribing]);

  React.useEffect(() => {
    if (!showModel) return;
    const onKey = (e: KeyboardEvent) => {
      if (!(e.metaKey || e.ctrlKey) || !e.shiftKey) return;
      if (e.key.toLowerCase() !== "m") return;
      e.preventDefault();
      modelPickerTriggerRef.current?.focus();
    };
    window.addEventListener("keydown", onKey, true);
    return () => window.removeEventListener("keydown", onKey, true);
  }, [showModel]);

  React.useEffect(() => {
    const preventBrowseNav = (e: DragEvent) => {
      if (e.dataTransfer?.types?.includes("Files")) {
        e.preventDefault();
      }
    };
    window.addEventListener("dragover", preventBrowseNav);
    window.addEventListener("drop", preventBrowseNav);
    return () => {
      window.removeEventListener("dragover", preventBrowseNav);
      window.removeEventListener("drop", preventBrowseNav);
    };
  }, []);

  const handleAddFiles = React.useCallback(
    (files: File[]) => {
      if (uploadsPending) {
        toast.message("Wait for uploads in progress.", { duration: 4000 });
        return;
      }
      if (attachments.length >= MAX_WORKSPACE_ATTACHMENT_COUNT) {
        toast.error(`Up to ${MAX_WORKSPACE_ATTACHMENT_COUNT} attachments.`);
        return;
      }
      const remaining = Math.max(0, MAX_WORKSPACE_ATTACHMENT_COUNT - attachments.length);
      const slice = files.slice(0, remaining);
      if (files.length > remaining) {
        toast.error(`Up to ${MAX_WORKSPACE_ATTACHMENT_COUNT} attachments.`);
      }
      onAddAttachments(slice);
    },
    [attachments.length, onAddAttachments, uploadsPending],
  );

  const onDragOver = (e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
  };

  const onDrop = (e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    dragDepthRef.current = 0;
    setIsDragging(false);
    if (disabled || sending || voiceBusy || uploadsPending) return;
    const dt = e.dataTransfer?.files;
    if (!dt?.length) return;
    handleAddFiles(Array.from(dt));
  };

  const onDragEnter = (e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    if (disabled || sending || voiceBusy || uploadsPending) return;
    dragDepthRef.current += 1;
    if (dragDepthRef.current === 1) setIsDragging(true);
  };

  const onDragLeave = (e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    dragDepthRef.current = Math.max(0, dragDepthRef.current - 1);
    if (dragDepthRef.current === 0) setIsDragging(false);
  };

  const triggerBannerStop = React.useCallback(
    (ev?: React.SyntheticEvent) => {
      ev?.preventDefault?.();
      ev?.stopPropagation?.();
      if ((!voiceRecording && !voiceLive) || voiceTranscribing) return;
      pushVoiceDebug({
        event: "voice.stop.banner_click",
        component: "WorkspaceChatComposer",
        composerInstanceId: composerInstanceId.current,
      });
      beginStopRequest("banner_stop");
      pushVoiceDebug({
        event: "voice.recorder.stop.called",
        component: "WorkspaceChatComposer",
        composerInstanceId: composerInstanceId.current,
        source: "banner_stop",
      });
      stopVoiceRecorderRef.current?.();
    },
    [beginStopRequest, voiceLive, voiceRecording, voiceTranscribing],
  );

  const composeLiveDraft = React.useCallback(() => {
    const base = liveBaseDraftRef.current.trim();
    const committed = liveCommittedDraftRef.current.trim();
    const interim = liveInterimDraftRef.current.trim();
    const body = [base, committed, interim].filter(Boolean).join(" ");
    return body;
  }, []);

  const appendLiveFinalChunk = React.useCallback((chunk: string) => {
    const clean = chunk.replace(/\s+/g, " ").trim();
    if (!clean) return;
    const prior = liveCommittedDraftRef.current.trim();
    liveCommittedDraftRef.current = prior ? `${prior} ${clean}` : clean;
  }, []);

  const captureComposerPointer = React.useCallback(
    (ev: React.SyntheticEvent) => {
      const target = ev.target as HTMLElement | null;
      if (!target) return;
      pushVoiceDebug({
        event: "voice.capture.pointer",
        component: "WorkspaceChatComposer",
        composerInstanceId: composerInstanceId.current,
        targetTag: target.tagName,
        targetClass: target.className,
        voiceState,
      });
    },
    [voiceState],
  );

  const captureComposerClick = React.useCallback(
    (ev: React.SyntheticEvent) => {
      const target = ev.target as HTMLElement | null;
      if (!target) return;
      pushVoiceDebug({
        event: "voice.capture.click",
        component: "WorkspaceChatComposer",
        composerInstanceId: composerInstanceId.current,
        targetTag: target.tagName,
        targetClass: target.className,
        voiceState,
      });
    },
    [voiceState],
  );

  const deckModelPickers = (
    <>
      {showModel ? (
        <WorkspaceOpenRouterModelPicker
          catalog={catalog!}
          candidates={pickerRows}
          modelId={modelId}
          onModelIdChange={onModelIdChange}
          disabled={sending}
          title={modelDetail}
          triggerRef={modelPickerTriggerRef}
          byokPickerActive={byokPickerActive}
          failedModelIds={failedChatModelIds}
          layoutDensity={composerToolbarDensity}
        />
      ) : modelPill ? (
        <span
          className={cn(
            "inline-flex min-w-0 items-center rounded-full border border-white/[0.08] bg-transparent font-mono text-emerald-200/85",
            composerToolbarDensity === "comfortable" &&
              "max-w-[min(14rem,calc(100vw-10rem))] px-2 py-0.5 text-[10px] md:max-w-[min(18rem,calc(100vw-12rem))] md:text-[11px]",
            composerToolbarDensity === "compact" &&
              "max-w-[min(11rem,45vw)] px-2 py-0.5 text-[10px] md:max-w-[min(14rem,50vw)]",
            composerToolbarDensity === "tight" &&
              "min-w-0 max-w-full flex-1 px-1.5 py-0.5 text-[10px]",
          )}
          title={modelDetail ?? modelPill ?? undefined}
        >
          <span className="truncate">{modelPill}</span>
        </span>
      ) : null}
    </>
  );

  const leftDeckControls = (
    <>
      {gohamDesktopChip ? (
        <button
          type="button"
          onClick={gohamDesktopChip.onOpenModal}
          disabled={Boolean(sending || voiceBusy || disabled || gohamDesktopChip.busy)}
          title={
            gohamDesktopChip.linked
              ? "GOHAM linked — local web bridge (trusted). Open status."
              : "GOHAM — trusted local-control web bridge connect"
          }
          className={cn(
            "mr-1 flex shrink-0 items-center gap-1 rounded-full border font-semibold uppercase tracking-wide transition-colors disabled:opacity-45",
            composerToolbarDensity === "comfortable" && "px-2.5 py-1 text-[10px]",
            composerToolbarDensity === "compact" && "px-2 py-0.5 text-[9px]",
            composerToolbarDensity === "tight" && "px-1.5 py-0.5 text-[9px]",
            gohamDesktopChip.linked
              ? "border-emerald-400/35 bg-emerald-500/[0.12] text-emerald-100/90 hover:bg-emerald-500/20"
              : "border-white/[0.12] bg-white/[0.06] text-white/70 hover:bg-white/[0.1]",
          )}
          aria-label="GOHAM local web bridge"
          data-ham-goham-chip="desktop"
        >
          {gohamDesktopChip.busy ? (
            <Loader2 className="h-3 w-3 shrink-0 animate-spin opacity-95" aria-hidden />
          ) : (
            <Link2 className="h-3 w-3 shrink-0 opacity-90" aria-hidden />
          )}
          <span className={composerToolbarDensity === "tight" ? "sr-only" : undefined}>GOHAM</span>
        </button>
      ) : null}
      <WorkspaceChatComposerActionsMenu
        onFiles={handleAddFiles}
        attachDisabled={sending || voiceBusy || disabled || uploadsPending}
        attachDisabledReason={attachMenuDisabledReason(
          uploadsPending,
          voiceBusy,
          sending,
          disabled,
        )}
        attachDetailsTitle={attachDetailsTitle}
        menuFooterHint={COMPOSER_MENU_FOOTER_HINT}
        generateImage={generateImage}
        generateVideo={generateVideo}
        exportPdf={exportPdf}
      />
      {value.length >= 100 ? (
        <span
          className="hidden min-w-0 text-[10px] tabular-nums text-white/30 select-none sm:inline"
          title="Approximate token count"
        >
          ~{Math.ceil(value.length / 4)} tokens
        </span>
      ) : null}
      {showModel || modelPill ? (
        <div
          data-hww-model-pill
          className={cn(
            "min-w-0 shrink-0",
            composerToolbarDensity === "tight" && "min-w-0 max-w-full flex-1 basis-[8rem]",
          )}
        >
          {deckModelPickers}
        </div>
      ) : null}
    </>
  );

  const rightDeckActions = (
    <div className="flex shrink-0 flex-nowrap items-center gap-1 md:gap-1.5">
      {contextMetersEnabled ? (
        <ContextMeterCluster
          payload={contextMetersPayload}
          enabled
          density={composerToolbarDensity}
          layout={meterLayout}
        />
      ) : null}
      <div
        className={cn(
          "flex h-8 min-h-8 shrink-0 items-center self-center",
          voiceTranscribing && "pointer-events-none opacity-55",
        )}
        title={micColumnTitle}
      >
        <WorkspaceVoiceMessageInput
          compact
          hidePreview
          mode={sttMode}
          disabled={sending || voiceTranscribing || disabled || sttDictationEnabled === false}
          disabledReason={
            sttDictationEnabled === false
              ? sttUnavailableReason ||
                "Speech-to-text is off — enable it in Workspace → Settings → Voice."
              : voiceTranscribing
                ? "Transcribing…"
                : undefined
          }
          onRecordingChange={(isRecording) => {
            if (liveListening) {
              return;
            }
            pushVoiceDebug({
              event: "voice.child.isRecording.signal",
              component: "WorkspaceChatComposer",
              composerInstanceId: composerInstanceId.current,
              isRecording,
              voiceState,
              stopRequested: stopRequestedRef.current,
            });
            if (isRecording) {
              if (
                stopRequestedRef.current ||
                voiceState === "stopping" ||
                voiceState === "transcribing"
              ) {
                pushVoiceDebug({
                  event: "voice.state.blocked_bounce",
                  component: "WorkspaceChatComposer",
                  composerInstanceId: composerInstanceId.current,
                  attempted: "recording",
                  voiceState,
                  stopRequested: stopRequestedRef.current,
                });
                return;
              }
              transitionVoiceState("recording", "recorder_started");
              return;
            }
            pushVoiceDebug({
              event: "voice.recorder.onstop",
              component: "WorkspaceChatComposer",
              composerInstanceId: composerInstanceId.current,
            });
            clearStopTimeout();
            if (voiceTranscribing) {
              transitionVoiceState("transcribing", "recorder_stopped_transcribe");
            } else {
              transitionVoiceState("idle", "recorder_stopped");
              stopRequestedRef.current = false;
            }
          }}
          onStartRequested={() => {
            stopRequestedRef.current = false;
            clearStopTimeout();
          }}
          onStopRequested={() => {
            beginStopRequest("stop_requested");
            pushVoiceDebug({
              event: "voice.recorder.stop.called",
              component: "WorkspaceChatComposer",
              composerInstanceId: composerInstanceId.current,
              source: "stop_button_or_escape",
            });
          }}
          onVoiceRecorderErrorChange={setVoiceBanner}
          onStopRecorderReady={(handler) => {
            stopVoiceRecorderRef.current = handler;
          }}
          onVoiceError={(err) => {
            setVoiceBanner(err);
            transitionVoiceState("error", "recorder_error");
            stopRequestedRef.current = false;
            clearStopTimeout();
          }}
          onVoiceMessage={(blob) => {
            void onVoiceBlob(blob);
          }}
          onModeChange={(mode) => {
            void onSttModeChange?.(mode);
          }}
          onLiveListeningChange={(active) => {
            setLiveListening(active);
            if (!active) {
              onChange(composeLiveDraft());
            } else {
              liveBaseDraftRef.current = value;
              liveCommittedDraftRef.current = "";
              liveInterimDraftRef.current = "";
            }
          }}
          onLiveInterimChange={(interim) => {
            liveInterimDraftRef.current = interim;
            onChange(composeLiveDraft());
          }}
          onLiveFinalText={(text) => {
            appendLiveFinalChunk(text);
            liveInterimDraftRef.current = "";
            onChange(composeLiveDraft());
          }}
          onLiveError={(message) => {
            setVoiceBanner(message);
            transitionVoiceState("error", "live_dictation_error");
            setLiveListening(false);
          }}
        />
      </div>
      <Button
        type="submit"
        size="icon"
        disabled={!canSend}
        title={sendButtonTitle}
        className={cn(
          "size-8 min-h-8 min-w-8 shrink-0 self-center rounded-md border border-emerald-400/20 bg-transparent text-emerald-200/85 shadow-none",
          "hover:border-emerald-400/38 hover:bg-emerald-500/12 hover:text-emerald-50",
          "focus-visible:border-emerald-400/45 focus-visible:ring-2 focus-visible:ring-emerald-400/30",
          "disabled:pointer-events-none disabled:opacity-40",
          canSend && "border-emerald-400/32 text-emerald-100",
        )}
        aria-label="Send"
        data-hww-command-send
        data-hww-composer-toolbar-icon="send"
      >
        {sending ? (
          <span className={cn("h-2.5 w-2.5 animate-pulse rounded-full bg-emerald-200/85")} />
        ) : (
          <ArrowUp className="h-3.5 w-3.5 shrink-0" strokeWidth={2.2} />
        )}
      </Button>
    </div>
  );

  const composerQuickTipsBusy = disabled || sending || voiceBusy || uploadsPending;
  const showComposerQuickTips =
    !quickTipsDismissed && Boolean(quickSuggestions?.length && onQuickSuggestion);

  return (
    <div
      ref={outerRef}
      className="hww-chat-composer-outer pointer-events-auto box-border w-full max-w-full min-w-0 shrink-0 overflow-x-hidden border-t border-white/[0.06] bg-[#030a10]/90 px-3 pb-[max(0.75rem,env(safe-area-inset-bottom))] pt-2 backdrop-blur-sm md:px-6"
      data-hww-composer-instance={composerInstanceId.current}
      data-hww-composer-density={composerToolbarDensity}
      data-voice-recording={voiceRecording ? "true" : "false"}
      data-voice-transcribing={voiceTranscribing ? "true" : "false"}
      data-voice-state={voiceState}
      onPointerDownCapture={captureComposerPointer}
      onClickCapture={captureComposerClick}
    >
      {showComposerQuickTips && quickSuggestions && onQuickSuggestion ? (
        <ComposerQuickTipsBar
          suggestions={quickSuggestions}
          composerBusy={composerQuickTipsBusy}
          onPick={onQuickSuggestion}
          onDismiss={() => setQuickTipsDismissed(true)}
        />
      ) : null}
      <form
        onSubmit={(e) => {
          e.preventDefault();
          onSubmit();
        }}
        className="w-full max-w-full min-w-0 md:pl-1"
      >
        <div
          className={cn(
            "relative box-border flex min-w-0 max-w-full flex-col overflow-hidden rounded-3xl",
            "text-[#e8eef3] shadow-[0_1px_0_rgba(255,255,255,0.04)_inset,0_8px_28px_rgba(0,0,0,0.32)]",
            isDragging
              ? "ring-2 ring-emerald-400/35"
              : "ring-1 ring-emerald-950/30 focus-within:ring-2 focus-within:ring-emerald-500/25",
          )}
          style={{
            background: "linear-gradient(180deg, #0a1814 0%, #050f0c 100%)",
            border: deckBorder,
          }}
          data-hww-command-deck
          onDragEnter={onDragEnter}
          onDragLeave={onDragLeave}
          onDragOver={onDragOver}
          onDrop={onDrop}
        >
          {isDragging ? (
            <div
              className="pointer-events-none absolute inset-1 z-20 flex items-center justify-center rounded-[1.1rem] border-2 border-dashed border-emerald-400/50 bg-[#020806]/75 text-[12px] font-medium text-emerald-100/90 backdrop-blur-sm"
              aria-hidden
            >
              Drop files to attach
            </div>
          ) : null}

          {attachments.length > 0 ? (
            <div className="border-b border-white/[0.07] px-2 pb-1.5 pt-2.5 md:px-3">
              <WorkspaceChatAttachmentPreviewList
                className="mb-0"
                attachments={attachments}
                onRemove={onRemoveAttachment}
                onRetryUpload={onRetryAttachmentUpload}
              />
            </div>
          ) : null}

          {(voiceRecording || voiceStopping || voiceTranscribing || voiceLive) && (
            <div
              className="flex items-center gap-1.5 border-b border-white/[0.06] px-3 py-1.5 text-[10px] font-medium uppercase tracking-wide"
              role="status"
            >
              {voiceLive ? (
                <>
                  <span className="inline-flex h-1.5 w-1.5 shrink-0 animate-pulse rounded-full bg-emerald-400" />
                  <button
                    type="button"
                    onPointerDownCapture={triggerBannerStop}
                    onMouseDownCapture={triggerBannerStop}
                    onClick={triggerBannerStop}
                    className="pointer-events-auto rounded px-1 py-0.5 text-left text-emerald-100/90 underline-offset-2 hover:bg-emerald-400/10 hover:underline"
                    aria-label="Stop live dictation"
                    data-hww-voice-button="live-banner-stop"
                    data-hww-voice-state="live"
                  >
                    Listening… live dictation
                  </button>
                </>
              ) : voiceTranscribing || voiceStopping ? (
                <>
                  <Loader2 className="h-3.5 w-3.5 shrink-0 animate-spin text-emerald-300" />
                  <span className="text-emerald-200/90">
                    {voiceStopping ? "Stopping…" : "Transcribing…"}
                  </span>
                </>
              ) : (
                <>
                  <span className="inline-flex h-1.5 w-1.5 shrink-0 animate-pulse rounded-full bg-red-500" />
                  <button
                    type="button"
                    onPointerDownCapture={triggerBannerStop}
                    onMouseDownCapture={triggerBannerStop}
                    onClick={triggerBannerStop}
                    className="pointer-events-auto rounded px-1 py-0.5 text-left text-red-200/90 underline-offset-2 hover:bg-red-400/10 hover:underline"
                    aria-label="Stop recording from banner"
                    data-hww-voice-button="recording-banner-stop"
                    data-hww-voice-state="recording"
                  >
                    Recording — tap here or the mic to stop
                  </button>
                </>
              )}
            </div>
          )}

          <div
            className={cn(
              "hww-command-deck box-border min-w-0 max-w-full overflow-x-hidden border-t border-white/[0.08]",
              composerToolbarDensity === "comfortable" && "hww-command-deck--comfortable",
              composerToolbarDensity === "compact" && "hww-command-deck--compact",
              composerToolbarDensity === "tight" && "hww-command-deck--tight",
              composerToolbarDensity === "tight"
                ? "flex flex-col gap-0"
                : "flex min-w-0 flex-col gap-0",
            )}
            data-hww-command-deck-layout={
              composerToolbarDensity === "tight" ? "stacked" : "input-toolbar"
            }
          >
            {composerToolbarDensity !== "tight" ? (
              <>
                <div
                  ref={textareaWrapRef}
                  data-hww-command-input-slot
                  className={cn(
                    "min-h-0 min-w-0 w-full px-2.5 pb-1 pt-2 md:px-3 md:pt-2.5 md:pb-1",
                    composerToolbarDensity === "compact" && "px-2 py-1.5 md:px-2.5",
                  )}
                >
                  <label htmlFor="hww-chat-composer" className="sr-only">
                    Message
                  </label>
                  <textarea
                    ref={textareaRef}
                    id="hww-chat-composer"
                    value={value}
                    onChange={(e) => onChange(e.target.value)}
                    onPaste={(e) => {
                      if (!onPasteFiles || disabled || sending || voiceBusy || uploadsPending) return;
                      const dt = e.clipboardData;
                      const files = collectComposerPasteFiles(dt);
                      if (files.length === 0) return;
                      e.preventDefault();
                      onPasteFiles(files);
                    }}
                    onKeyDown={(e) => {
                      if (e.key === "Enter" && !e.shiftKey) {
                        e.preventDefault();
                        if (canSend) onSubmit();
                      }
                    }}
                    rows={1}
                    disabled={disabled || sending || voiceTranscribing}
                    placeholder={placeholder}
                    className="hww-command-textarea box-border min-h-[42px] w-full resize-none border-0 bg-transparent px-1 py-1 text-[13px] leading-[1.45] text-[#e8eef3] outline-none placeholder:text-white/40 focus:ring-0 focus:outline-none [box-shadow:none] overflow-x-hidden max-h-[240px] md:py-1.5"
                  />
                </div>
                <div
                  className={cn(
                    "flex min-h-10 w-full min-w-0 shrink-0 items-center justify-between gap-2 border-t border-white/[0.08]",
                    "px-2.5 py-1.5 md:px-3 md:py-2",
                    composerToolbarDensity === "compact" && "min-h-9 py-1.5 md:py-1.5",
                  )}
                >
                  <div
                    data-hww-command-deck-left
                    data-hww-command-left
                    className="flex min-h-10 min-w-0 flex-[1_1_0] flex-row flex-wrap items-center gap-1 overflow-hidden md:min-h-[2.5rem]"
                  >
                    {leftDeckControls}
                  </div>
                  <div
                    data-hww-command-deck-actions
                    data-hww-command-controls
                    data-hww-action-buttons
                    className="flex min-h-10 shrink-0 items-center justify-end gap-1 overflow-x-hidden md:min-h-[2.5rem]"
                  >
                    {rightDeckActions}
                  </div>
                </div>
              </>
            ) : null}

            {composerToolbarDensity === "tight" ? (
              <>
                <div
                  ref={textareaWrapRef}
                  data-hww-command-input-slot
                  className="flex min-h-0 min-w-0 w-full max-w-full flex-col self-stretch px-2.5 pb-1 pt-2.5 md:px-3.5"
                >
                  <label htmlFor="hww-chat-composer" className="sr-only">
                    Message
                  </label>
                  <textarea
                    ref={textareaRef}
                    id="hww-chat-composer"
                    value={value}
                    onChange={(e) => onChange(e.target.value)}
                    onPaste={(e) => {
                      if (!onPasteFiles || disabled || sending || voiceBusy || uploadsPending) return;
                      const dt = e.clipboardData;
                      const files = collectComposerPasteFiles(dt);
                      if (files.length === 0) return;
                      e.preventDefault();
                      onPasteFiles(files);
                    }}
                    onKeyDown={(e) => {
                      if (e.key === "Enter" && !e.shiftKey) {
                        e.preventDefault();
                        if (canSend) onSubmit();
                      }
                    }}
                    rows={1}
                    disabled={disabled || sending || voiceTranscribing}
                    placeholder={placeholder}
                    className="hww-command-textarea box-border min-h-[44px] w-full resize-none border-0 bg-transparent px-1 py-1 text-[13px] leading-[1.45] text-[#e8eef3] outline-none placeholder:text-white/40 focus:ring-0 focus:outline-none [box-shadow:none] overflow-x-hidden max-h-[240px]"
                  />
                </div>
                <div
                  data-hww-command-controls
                  data-hww-action-buttons
                  className="flex min-w-0 flex-wrap items-center gap-1 border-t border-white/[0.06] px-1.5 py-1.5"
                >
                  <div
                    data-hww-command-deck-left
                    data-hww-command-left
                    className="flex min-w-0 flex-1 flex-wrap items-center gap-0.5 [&>*]:max-w-full"
                  >
                    {leftDeckControls}
                  </div>
                  <div className="ml-auto flex min-w-0 shrink-0 items-center gap-0.5">
                    {rightDeckActions}
                  </div>
                </div>
              </>
            ) : null}
          </div>

          {(catalog?.gateway_mode || "").trim().toLowerCase() === "mock" &&
          chatCapabilities?.generation?.supports_video_generation ? (
            <p className="mx-2.5 mb-1 text-[11px] leading-snug text-amber-200/75 md:mx-3.5">
              Mock chat gateway: <span className="font-medium text-amber-100/90">Send</span> queues
              a Comfy video from your prompt (same as{" "}
              <span className="font-medium text-amber-100/90">+ → Generate video</span>). Use{" "}
              <span className="font-mono text-[10px] text-amber-100/85">
                HERMES_GATEWAY_MODE=openrouter
              </span>{" "}
              for normal assistant replies instead.
            </p>
          ) : null}

          {voiceBanner ? (
            <div
              className="mx-2.5 flex min-h-0 items-start gap-2 rounded-md border border-red-500/20 bg-red-950/20 px-2 py-1.5 text-[10px] leading-snug text-red-100/90 md:mx-3.5"
              role="alert"
            >
              <span className="min-w-0 flex-1 break-words">{voiceBanner}</span>
              <button
                type="button"
                className="shrink-0 rounded px-0.5 text-[12px] leading-none text-red-200/80 hover:bg-white/10"
                aria-label="Dismiss voice message"
                onClick={() => setVoiceBanner(null)}
              >
                ×
              </button>
            </div>
          ) : null}
        </div>
      </form>
    </div>
  );
}
