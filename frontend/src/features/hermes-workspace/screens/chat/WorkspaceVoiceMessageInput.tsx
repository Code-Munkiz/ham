/**
 * Mic-enabled control for Hermes Workspace chat composer (migrated from pre-workspace chat).
 */

import React, { useState } from "react";
import { cn } from "@/lib/utils";
import { useVoiceRecorder } from "@/hooks/useVoiceRecorder";
import "./WorkspaceVoiceMessageInput.css";

type DictationMode = "auto" | "live" | "record";

type SpeechRecognitionAlternative = { transcript: string; confidence: number };
type SpeechRecognitionResult = {
  isFinal: boolean;
  length: number;
  [index: number]: SpeechRecognitionAlternative;
};
type SpeechRecognitionResultList = {
  length: number;
  [index: number]: SpeechRecognitionResult;
};
type SpeechRecognitionEvent = Event & {
  resultIndex: number;
  results: SpeechRecognitionResultList;
};
type SpeechRecognitionLike = {
  continuous: boolean;
  interimResults: boolean;
  lang: string;
  onstart: ((ev: Event) => void) | null;
  onresult: ((ev: SpeechRecognitionEvent) => void) | null;
  onerror: ((ev: Event & { error?: string }) => void) | null;
  onend: ((ev: Event) => void) | null;
  start: () => void;
  stop: () => void;
};
type SpeechRecognitionCtor = new () => SpeechRecognitionLike;

function speechRecognitionCtor(): SpeechRecognitionCtor | null {
  if (typeof window === "undefined") return null;
  const w = window as unknown as {
    SpeechRecognition?: SpeechRecognitionCtor;
    webkitSpeechRecognition?: SpeechRecognitionCtor;
  };
  return w.SpeechRecognition ?? w.webkitSpeechRecognition ?? null;
}

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

interface WorkspaceVoiceMessageInputProps {
  onVoiceMessage?: (audioBlob: Blob, duration: number) => void;
  onVoiceError?: (error: string) => void;
  /** Compact composer: sync hook `error` for an inline strip above the row (avoids nested chrome in the mic column). */
  onVoiceRecorderErrorChange?: (message: string | null) => void;
  /** Fires when the built-in MediaRecorder is actively recording (for send-block + inline status in composer). */
  onRecordingChange?: (isRecording: boolean) => void;
  /** Smaller, borderless treatment for the chat composer strip (no standalone card). */
  compact?: boolean;
  placeholder?: string;
  /** When true, do not show post-record preview; use for dictation that uploads immediately. */
  hidePreview?: boolean;
  /** Disable mic controls (e.g. while transcribing or sending). */
  disabled?: boolean;
  /** When `disabled` is true, overrides default tooltip (e.g. STT off in Voice settings). */
  disabledReason?: string;
  /** Optional parent hook to request stop from external UI (banner/keyboard fallback). */
  onStopRecorderReady?: (handler: (() => void) | null) => void;
  /** Notify parent when user requested stop from any input path. */
  onStopRequested?: () => void;
  /** Notify parent when user explicitly requested a new recording start. */
  onStartRequested?: () => void;
  /** Dictation mode selection for mic click behavior. */
  mode?: DictationMode;
  onModeChange?: (mode: DictationMode) => void;
  onLiveListeningChange?: (active: boolean) => void;
  onLiveInterimChange?: (interim: string) => void;
  onLiveFinalText?: (text: string) => void;
  onLiveError?: (message: string) => void;
}

export function WorkspaceVoiceMessageInput(props: WorkspaceVoiceMessageInputProps) {
  const {
    onVoiceMessage,
    onVoiceError,
    onVoiceRecorderErrorChange,
    onRecordingChange,
    compact = false,
    hidePreview = false,
    disabled = false,
    disabledReason,
    onStopRecorderReady,
    onStopRequested,
    onStartRequested,
    mode = "record",
    onModeChange,
    onLiveListeningChange,
    onLiveInterimChange,
    onLiveFinalText,
    onLiveError,
  } = props;

  const [audioBlob, setAudioBlob] = useState<Blob | null>(null);
  const [menu, setMenu] = useState<{ x: number; y: number } | null>(null);
  const [isLiveListening, setIsLiveListening] = useState(false);
  const voiceInstanceId = React.useRef(`voice-ui-${Math.random().toString(36).slice(2, 9)}`);
  const lastStopRequestAtRef = React.useRef(0);
  const liveProducedFinalRef = React.useRef(false);
  const recognitionRef = React.useRef<SpeechRecognitionLike | null>(null);
  const micButtonRef = React.useRef<HTMLButtonElement | null>(null);
  const liveStartRequestedAtRef = React.useRef(0);

  const {
    isRecording,
    blobUrl: _blobUrl,
    error,
    duration,
    startRecording,
    stopRecording,
    cancelRecording,
  } = useVoiceRecorder({
    onRecordingComplete: (blob, dur) => {
      if (!hidePreview) {
        setAudioBlob(blob);
      }
      onVoiceMessage?.(blob, dur);
    },
    onRecordingError: onVoiceError,
  });

  const liveSupported = React.useMemo(() => Boolean(speechRecognitionCtor()), []);
  const resolvedMode: DictationMode = mode === "auto" ? (liveSupported ? "live" : "record") : mode;

  React.useEffect(() => {
    if (!menu) return;
    const close = () => setMenu(null);
    window.addEventListener("click", close);
    window.addEventListener("contextmenu", close);
    window.addEventListener("resize", close);
    return () => {
      window.removeEventListener("click", close);
      window.removeEventListener("contextmenu", close);
      window.removeEventListener("resize", close);
    };
  }, [menu]);

  React.useEffect(() => {
    onRecordingChange?.(isRecording);
    pushVoiceDebug({
      event: "voice.render",
      component: "WorkspaceVoiceMessageInput",
      voiceInstanceId: voiceInstanceId.current,
      isRecording,
      hasError: Boolean(error),
      disabled,
    });
  }, [isRecording, onRecordingChange]);

  React.useEffect(() => {
    if (!compact) return;
    onVoiceRecorderErrorChange?.(error ?? null);
  }, [compact, error, onVoiceRecorderErrorChange]);

  const stopLiveDictation = React.useCallback(() => {
    const rec = recognitionRef.current;
    if (!rec) return;
    try {
      rec.stop();
    } catch {
      /* ignore */
    }
    recognitionRef.current = null;
    setIsLiveListening(false);
    onLiveListeningChange?.(false);
  }, [onLiveListeningChange]);

  const startLiveDictation = React.useCallback(
    (opts: { allowFallbackToRecord: boolean }) => {
      const Ctor = speechRecognitionCtor();
      if (!Ctor) {
        if (opts.allowFallbackToRecord) {
          onStartRequested?.();
          void startRecording();
          return;
        }
        const msg = "Live dictation is not available in this browser.";
        onLiveError?.(msg);
        onVoiceError?.(msg);
        return;
      }
      const rec = new Ctor();
      recognitionRef.current = rec;
      liveProducedFinalRef.current = false;
      liveStartRequestedAtRef.current = Date.now();
      onStartRequested?.();
      rec.continuous = true;
      rec.interimResults = true;
      rec.lang = "en-US";
      rec.onstart = () => {
        setIsLiveListening(true);
        onLiveListeningChange?.(true);
      };
      rec.onresult = (ev) => {
        let interim = "";
        let finals = "";
        for (let i = ev.resultIndex; i < ev.results.length; i += 1) {
          const r = ev.results[i];
          const chunk = r[0]?.transcript?.trim() ?? "";
          if (!chunk) continue;
          if (r.isFinal) finals = finals ? `${finals} ${chunk}` : chunk;
          else interim = interim ? `${interim} ${chunk}` : chunk;
        }
        if (finals.trim()) {
          liveProducedFinalRef.current = true;
          onLiveFinalText?.(finals.trim());
        }
        onLiveInterimChange?.(interim.trim());
      };
      rec.onerror = (ev) => {
        const early = Date.now() - liveStartRequestedAtRef.current < 1500;
        const hadFinal = liveProducedFinalRef.current;
        const msg =
          ev?.error === "not-allowed"
            ? "Microphone permission is blocked. Allow microphone access in your browser settings."
            : "Live dictation failed to start.";
        setIsLiveListening(false);
        onLiveListeningChange?.(false);
        onLiveInterimChange?.("");
        if (opts.allowFallbackToRecord && !hadFinal && early) {
          onStartRequested?.();
          void startRecording();
          return;
        }
        onLiveError?.(msg);
        onVoiceError?.(msg);
      };
      rec.onend = () => {
        recognitionRef.current = null;
        setIsLiveListening(false);
        onLiveListeningChange?.(false);
        onLiveInterimChange?.("");
        if (opts.allowFallbackToRecord && !liveProducedFinalRef.current) {
          onStartRequested?.();
          void startRecording();
        }
      };
      try {
        rec.start();
      } catch {
        recognitionRef.current = null;
        if (opts.allowFallbackToRecord) {
          onStartRequested?.();
          void startRecording();
          return;
        }
        const msg = "Live dictation could not start.";
        onLiveError?.(msg);
        onVoiceError?.(msg);
      }
    },
    [
      onLiveError,
      onLiveFinalText,
      onLiveInterimChange,
      onLiveListeningChange,
      onStartRequested,
      onVoiceError,
      startRecording,
    ],
  );

  const requestStop = React.useCallback(
    (
      source: "pointerdown" | "click" | "banner_click" | "escape",
      ev?: React.SyntheticEvent | KeyboardEvent,
      opts: { force?: boolean } = {},
    ) => {
      ev?.preventDefault?.();
      ev?.stopPropagation?.();
      if (!isRecording && !isLiveListening && !opts.force) {
        pushVoiceDebug({
          event: "voice.stop.early_return",
          source,
          reason: "not_recording",
          component: "WorkspaceVoiceMessageInput",
          voiceInstanceId: voiceInstanceId.current,
          isRecording,
          disabled,
        });
        return;
      }
      const now = Date.now();
      if (now - lastStopRequestAtRef.current < 250) return;
      lastStopRequestAtRef.current = now;
      pushVoiceDebug({
        event:
          source === "pointerdown"
            ? "voice.stop.pointerdown"
            : source === "escape"
              ? "voice.stop.escape"
              : source === "banner_click"
                ? "voice.stop.banner_click"
                : "voice.stop.click",
        source,
        component: "WorkspaceVoiceMessageInput",
        voiceInstanceId: voiceInstanceId.current,
        isRecording,
        disabled,
      });
      if (isLiveListening) {
        onStopRequested?.();
        stopLiveDictation();
        return;
      }
      onStopRequested?.();
      stopRecording();
    },
    [disabled, isLiveListening, isRecording, onStopRequested, stopLiveDictation, stopRecording],
  );

  React.useEffect(() => {
    onStopRecorderReady?.(() => requestStop("banner_click", undefined, { force: true }));
    return () => onStopRecorderReady?.(null);
  }, [onStopRecorderReady, requestStop]);

  React.useEffect(() => {
    if (!isRecording && !isLiveListening) return;
    const onKeyDown = (ev: KeyboardEvent) => {
      if (ev.key !== "Escape") return;
      requestStop("escape", ev, { force: true });
    };
    window.addEventListener("keydown", onKeyDown, true);
    return () => window.removeEventListener("keydown", onKeyDown, true);
  }, [isLiveListening, isRecording, requestStop]);

  const handleCancelRecording = () => {
    cancelRecording();
    setAudioBlob(null);
  };

  React.useEffect(() => {
    return () => {
      try {
        recognitionRef.current?.stop();
      } catch {
        /* ignore */
      }
      recognitionRef.current = null;
    };
  }, []);

  const formatDuration = (seconds: number) => {
    const mins = Math.floor(seconds / 60);
    const secs = seconds % 60;
    return `${mins}:${secs.toString().padStart(2, "0")}`;
  };

  const active = isRecording || isLiveListening;
  const modeTitle =
    mode === "record"
      ? "Record then transcribe"
      : mode === "live"
        ? "Dictate live"
        : "Auto dictation";
  const micTitle = disabled
    ? disabledReason ||
      "Voice input unavailable while sending, transcribing, or when speech-to-text is disabled in Voice settings."
    : error
      ? error
      : active
        ? "Stop dictation"
        : modeTitle;

  return (
    <div
      className={cn(
        "voice-message-input-container",
        compact && "voice-message-input-container--compact",
      )}
      data-hww-voice-instance={voiceInstanceId.current}
      data-hww-voice-state={active ? (isLiveListening ? "live" : "recording") : "idle"}
    >
      {!compact && error ? (
        <div className="recording-error recording-error--stacked">{error}</div>
      ) : null}

      {audioBlob && !hidePreview ? (
        <div className="audio-preview">
          <audio controls src={URL.createObjectURL(audioBlob)} />
          <button type="button" onClick={handleCancelRecording} className="audio-retake-button">
            Retake
          </button>
        </div>
      ) : (
        <div className={isRecording ? "recording-active" : "recording-idle"}>
          <button
            ref={micButtonRef}
            type="button"
            disabled={disabled}
            title={micTitle}
            onPointerDownCapture={(e) => {
              if (!active) return;
              requestStop("pointerdown", e);
            }}
            onMouseDownCapture={(e) => {
              if (!active) return;
              requestStop("pointerdown", e);
            }}
            onClick={(e) => {
              pushVoiceDebug({
                event: "voice.button.click",
                source: "mic-toggle",
                component: "WorkspaceVoiceMessageInput",
                voiceInstanceId: voiceInstanceId.current,
                isRecording: active,
                disabled,
              });
              if (active) {
                requestStop("click", e);
              } else {
                e.preventDefault();
                e.stopPropagation();
                if (resolvedMode === "live") {
                  startLiveDictation({ allowFallbackToRecord: mode === "auto" });
                  return;
                }
                onStartRequested?.();
                void startRecording();
              }
            }}
            onContextMenu={(e) => {
              e.preventDefault();
              setMenu({ x: e.clientX, y: e.clientY });
            }}
            onKeyDown={(e) => {
              if (e.key !== "ContextMenu" && !(e.shiftKey && e.key === "F10")) return;
              e.preventDefault();
              const r = micButtonRef.current?.getBoundingClientRect();
              setMenu({
                x: Math.round((r?.left ?? 0) + (r?.width ?? 0) / 2),
                y: Math.round((r?.bottom ?? 0) + 8),
              });
            }}
            className={cn("mic-button", error && !isRecording && "mic-button--had-error")}
            aria-label={active ? "Stop voice dictation" : modeTitle}
            data-hww-voice-button="mic-toggle"
            data-hww-voice-instance={voiceInstanceId.current}
            data-hww-voice-state={active ? (isLiveListening ? "live" : "recording") : "idle"}
            data-hww-stop-primary={active ? "true" : "false"}
            data-hww-composer-toolbar-icon="mic"
          >
            {active ? (
              <svg width="24" height="24" viewBox="0 0 24 24" fill="currentColor">
                <rect x="6" y="6" width="12" height="12" rx="2" />
              </svg>
            ) : (
              <svg width="24" height="24" viewBox="0 0 24 24" fill="currentColor">
                <path d="M12 14c1.66 0 3-1.34 3-3V5c0-1.66-1.34-3-3-3S9 3.34 9 5v6c0 1.66 1.34 3 3 3z" />
                <path d="M17 11c0 2.76-2.24 5-5 5s-5-2.24-5-5H5c0 3.53 2.61 6.43 6 6.92V21h2v-3.08c3.39-.49 6-3.39 6-6.92h-2z" />
              </svg>
            )}
          </button>

          {isRecording && (
            <div className="recording-indicator">
              <div className="pulse-animation" />
              <span className="duration-text">{formatDuration(duration)}</span>
              <button
                type="button"
                disabled={disabled}
                onPointerDownCapture={(e) => requestStop("pointerdown", e)}
                onMouseDownCapture={(e) => requestStop("pointerdown", e)}
                onClick={(e) => requestStop("click", e)}
                className="stop-recording"
                aria-label="Stop voice recording"
                data-hww-voice-button="stop-pill"
                data-hww-voice-instance={voiceInstanceId.current}
                data-hww-voice-state={isRecording ? "recording" : "idle"}
              >
                Stop
              </button>
            </div>
          )}
        </div>
      )}
      {menu ? (
        <div
          className="fixed z-50 min-w-[220px] rounded-lg border border-white/10 bg-[#0b151c] p-1 text-[12px] text-white/90 shadow-xl"
          style={{ top: menu.y, left: menu.x }}
          role="menu"
          aria-label="Dictation mode"
        >
          <button
            type="button"
            role="menuitemradio"
            aria-checked={mode === "record"}
            className="flex w-full items-center justify-between rounded px-2 py-1.5 text-left hover:bg-white/[0.08]"
            onClick={() => {
              onModeChange?.("record");
              setMenu(null);
            }}
          >
            <span>Record then transcribe</span>
            {mode === "record" ? <span>✓</span> : null}
          </button>
          <button
            type="button"
            role="menuitemradio"
            aria-checked={mode === "live"}
            className="flex w-full items-center justify-between rounded px-2 py-1.5 text-left hover:bg-white/[0.08]"
            onClick={() => {
              onModeChange?.("live");
              setMenu(null);
            }}
          >
            <span>Dictate live</span>
            {mode === "live" ? <span>✓</span> : null}
          </button>
          <button
            type="button"
            role="menuitemradio"
            aria-checked={mode === "auto"}
            className="flex w-full items-center justify-between rounded px-2 py-1.5 text-left hover:bg-white/[0.08]"
            onClick={() => {
              onModeChange?.("auto");
              setMenu(null);
            }}
          >
            <span>Auto dictation</span>
            {mode === "auto" ? <span>✓</span> : null}
          </button>
        </div>
      ) : null}
    </div>
  );
}
