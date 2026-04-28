/**
 * Mic-enabled control for Hermes Workspace chat composer (migrated from pre-workspace chat).
 */

import React, { useState } from "react";
import { cn } from "@/lib/utils";
import { useVoiceRecorder } from "@/hooks/useVoiceRecorder";
import "./WorkspaceVoiceMessageInput.css";

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
  } = props;

  const [audioBlob, setAudioBlob] = useState<Blob | null>(null);
  const voiceInstanceId = React.useRef(`voice-ui-${Math.random().toString(36).slice(2, 9)}`);
  const lastStopRequestAtRef = React.useRef(0);

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

  const requestStop = React.useCallback(
    (
      source: "pointerdown" | "click" | "banner_click" | "escape",
      ev?: React.SyntheticEvent | KeyboardEvent,
      opts: { force?: boolean } = {},
    ) => {
      ev?.preventDefault?.();
      ev?.stopPropagation?.();
      if (!isRecording && !opts.force) {
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
        event: source === "pointerdown" ? "voice.stop.pointerdown" : source === "escape" ? "voice.stop.escape" : source === "banner_click" ? "voice.stop.banner_click" : "voice.stop.click",
        source,
        component: "WorkspaceVoiceMessageInput",
        voiceInstanceId: voiceInstanceId.current,
        isRecording,
        disabled,
      });
      onStopRequested?.();
      stopRecording();
    },
    [disabled, isRecording, onStopRequested, stopRecording],
  );

  React.useEffect(() => {
    onStopRecorderReady?.(() => requestStop("banner_click", undefined, { force: true }));
    return () => onStopRecorderReady?.(null);
  }, [onStopRecorderReady, requestStop]);

  React.useEffect(() => {
    if (!isRecording) return;
    const onKeyDown = (ev: KeyboardEvent) => {
      if (ev.key !== "Escape") return;
      requestStop("escape", ev, { force: true });
    };
    window.addEventListener("keydown", onKeyDown, true);
    return () => window.removeEventListener("keydown", onKeyDown, true);
  }, [isRecording, requestStop]);

  const handleCancelRecording = () => {
    cancelRecording();
    setAudioBlob(null);
  };

  const formatDuration = (seconds: number) => {
    const mins = Math.floor(seconds / 60);
    const secs = seconds % 60;
    return `${mins}:${secs.toString().padStart(2, "0")}`;
  };

  const micTitle = disabled
    ? disabledReason ||
      "Voice input unavailable while sending, transcribing, or when speech-to-text is disabled in Voice settings."
    : error
      ? error
      : isRecording
        ? "Stop recording"
        : "Record voice — requires a microphone";

  return (
    <div
      className={cn(
        "voice-message-input-container",
        compact && "voice-message-input-container--compact",
      )}
      data-hww-voice-instance={voiceInstanceId.current}
      data-hww-voice-state={isRecording ? "recording" : "idle"}
    >
      {!compact && error ? <div className="recording-error recording-error--stacked">{error}</div> : null}

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
            type="button"
            disabled={disabled}
            title={micTitle}
            onPointerDownCapture={(e) => {
              if (!isRecording) return;
              requestStop("pointerdown", e);
            }}
            onMouseDownCapture={(e) => {
              if (!isRecording) return;
              requestStop("pointerdown", e);
            }}
            onClick={(e) => {
              pushVoiceDebug({
                event: "voice.button.click",
                source: "mic-toggle",
                component: "WorkspaceVoiceMessageInput",
                voiceInstanceId: voiceInstanceId.current,
                isRecording,
                disabled,
              });
              if (isRecording) {
                requestStop("click", e);
              } else {
                e.preventDefault();
                e.stopPropagation();
                void startRecording();
              }
            }}
            className={cn("mic-button", error && !isRecording && "mic-button--had-error")}
            aria-label={isRecording ? "Stop voice recording" : "Start voice recording"}
            data-hww-voice-button="mic-toggle"
            data-hww-voice-instance={voiceInstanceId.current}
            data-hww-voice-state={isRecording ? "recording" : "idle"}
            data-hww-stop-primary={isRecording ? "true" : "false"}
          >
            {isRecording ? (
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
    </div>
  );
}
