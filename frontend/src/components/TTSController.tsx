/**
 * TTSController.tsx

 * TTS enable/disable toggle for chat responses.
 * 
 * Features:
 * - Toggle TTS on/off
 * - Visual feedback when speaking
 * - Stop button when playing
 */

import React from "react";
import { useTTSResponse } from "../hooks/useTTSResponse";
import "./TTSController.css";

interface TTSControllerProps {
  enabled: boolean;
  onToggle: (enabled: boolean) => void;
  autoSpeak?: boolean;
}

export function TTSController(props: TTSControllerProps) {
  const { enabled, onToggle, autoSpeak = false } = props;

  const { playing, currentText, speak, stop } = useTTSResponse({
    onError: (error) => console.error("TTS Error:", error),
  });

  const handleToggle = () => {
    const newState = !enabled;
    onToggle(newState);

    // Auto-speak first message if enabled
    if (newState && autoSpeak && currentText) {
      speak(currentText);
    }
  };

  const handleSpeakCurrent = () => {
    if (currentText && !playing) {
      speak(currentText);
    } else if (playing) {
      stop();
    }
  };

  return (
    <div className="tts-controller">
      <button
        onClick={handleToggle}
        className={`tts-toggle ${enabled ? "enabled" : ""}`}
        aria-label={enabled ? "Disable text-to-speech" : "Enable text-to-speech"}
      >
        <svg width="18" height="18" viewBox="0 0 24 24" fill="currentColor">
          <path d="M3 9v6h4l5 5V4L7 9H3zm13.5 3c0-1.77-1.02-3.29-2.5-4.03v8.05c1.48-.73 2.5-2.25 2.5-4.02zM14 3.23v2.06c2.89.86 5 3.54 5 6.71s-2.11 5.85-5 6.71v2.06c4.01-.91 7-4.49 7-8.77s-2.99-7.86-7-8.77z" />
        </svg>
        <span className="tts-label">{enabled ? "TTS On" : "TTS Off"}</span>
      </button>

      {playing && (
        <button
          onClick={handleSpeakCurrent}
          className="tts-playback-button"
          aria-label="Stop playback"
        >
          <svg width="18" height="18" viewBox="0 0 24 24" fill="currentColor">
            <rect x="6" y="4" width="4" height="16" rx="1" />
            <rect x="14" y="4" width="4" height="16" rx="1" />
          </svg>
          <span>Stop</span>
        </button>
      )}
    </div>
  );
}
