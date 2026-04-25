/**
 * VoiceMessageInput.tsx

 * Mic-enabled chat input component with recording UI.
 * 
 * Features:
 * - Mic button to start recording
 * - CSS-only pulsing animation (no canvas)
 * - Recording duration display
 * - Stop/cancel controls
 * - Audio preview after recording
 */

import React, { useState } from 'react';
import { cn } from '@/lib/utils';
import { useVoiceRecorder } from '../../hooks/useVoiceRecorder';
import './VoiceMessageInput.css';

interface VoiceMessageInputProps {
  onVoiceMessage?: (audioBlob: Blob, duration: number) => void;
  onVoiceError?: (error: string) => void;
  /** Smaller, borderless treatment for the chat composer strip (no standalone card). */
  compact?: boolean;
  placeholder?: string;
  /** When true, do not show post-record preview; use for dictation that uploads immediately. */
  hidePreview?: boolean;
  /** Disable mic controls (e.g. while transcribing or sending). */
  disabled?: boolean;
}

export function VoiceMessageInput(props: VoiceMessageInputProps) {
  const { onVoiceMessage, onVoiceError, compact = false, hidePreview = false, disabled = false } = props;
  
  const [audioBlob, setAudioBlob] = useState<Blob | null>(null);
  
  const {
    isRecording,
    isPaused,
    blobUrl,
    error,
    duration,
    startRecording,
    stopRecording,
    cancelRecording,
  } = useVoiceRecorder({
    onRecordingComplete: (blob, duration) => {
      if (!hidePreview) {
        setAudioBlob(blob);
      }
      onVoiceMessage?.(blob, duration);
    },
    onRecordingError: onVoiceError,
  });

  const handleStopRecording = () => {
    stopRecording();
    if (!hidePreview) {
      setAudioBlob(null);
    }
  };

  const handleCancelRecording = () => {
    cancelRecording();
    setAudioBlob(null);
  };

  // Format duration for display (MM:SS)
  const formatDuration = (seconds: number) => {
    const mins = Math.floor(seconds / 60);
    const secs = seconds % 60;
    return `${mins}:${secs.toString().padStart(2, '0')}`;
  };

  return (
    <div
      className={cn(
        'voice-message-input-container',
        compact && 'voice-message-input-container--compact',
      )}
    >
      {error && (
        <div className="recording-error">
          {error}
        </div>
      )}

      {audioBlob && !hidePreview ? (
        <div className="audio-preview">
          <audio controls src={URL.createObjectURL(audioBlob)} />
          <button onClick={handleCancelRecording} className="audio-retake-button">
            Retake
          </button>
        </div>
      ) : (
        <div className={isRecording ? "recording-active" : "recording-idle"}>
          <button
            type="button"
            disabled={disabled}
            onClick={isRecording ? stopRecording : startRecording}
            className="mic-button"
            aria-label={isRecording ? "Stop recording" : "Start voice recording"}
          >
            {isRecording ? (
              <svg width="24" height="24" viewBox="0 0 24 24" fill="currentColor">
                <rect x="6" y="6" width="12" height="12" rx="2" />
              </svg>
            ) : (
              <svg width="24" height="24" viewBox="0 0 24 24" fill="currentColor">
                <path d="M12 14c1.66 0 3-1.34 3-3V5c0-1.66-1.34-3-3-3S9 3.34 9 5v6c0 1.66 1.34 3 3 3z"/>
                <path d="M17 11c0 2.76-2.24 5-5 5s-5-2.24-5-5H5c0 3.53 2.61 6.43 6 6.92V21h2v-3.08c3.39-.49 6-3.39 6-6.92h-2z"/>
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
    </div>
  );
}
