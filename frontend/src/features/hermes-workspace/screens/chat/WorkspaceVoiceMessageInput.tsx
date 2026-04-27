/**
 * Mic-enabled control for Hermes Workspace chat composer (migrated from legacy `components/chat`).
 */

import React, { useState } from "react";
import { cn } from "@/lib/utils";
import { useVoiceRecorder } from "@/hooks/useVoiceRecorder";
import "./WorkspaceVoiceMessageInput.css";

interface WorkspaceVoiceMessageInputProps {
  onVoiceMessage?: (audioBlob: Blob, duration: number) => void;
  onVoiceError?: (error: string) => void;
  /** Fires when the built-in MediaRecorder is actively recording (for send-block + inline status in composer). */
  onRecordingChange?: (isRecording: boolean) => void;
  /** Smaller, borderless treatment for the chat composer strip (no standalone card). */
  compact?: boolean;
  placeholder?: string;
  /** When true, do not show post-record preview; use for dictation that uploads immediately. */
  hidePreview?: boolean;
  /** Disable mic controls (e.g. while transcribing or sending). */
  disabled?: boolean;
}

export function WorkspaceVoiceMessageInput(props: WorkspaceVoiceMessageInputProps) {
  const {
    onVoiceMessage,
    onVoiceError,
    onRecordingChange,
    compact = false,
    hidePreview = false,
    disabled = false,
  } = props;

  const [audioBlob, setAudioBlob] = useState<Blob | null>(null);

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
  }, [isRecording, onRecordingChange]);

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
    ? "Voice input unavailable while sending or transcribing."
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
            onClick={isRecording ? stopRecording : startRecording}
            className={cn("mic-button", error && !isRecording && "mic-button--had-error")}
            aria-label={isRecording ? "Stop recording" : "Start voice recording"}
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
                onClick={stopRecording}
                className="stop-recording"
                aria-label="Stop recording"
              >
                Stop
              </button>
            </div>
          )}
        </div>
      )}

      {compact && error ? (
        <p className="recording-error-compact" role="status">
          {error}
        </p>
      ) : null}
    </div>
  );
}
