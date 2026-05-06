/**
 * useTTSResponse.ts

 * Hook for playing TTS responses in the browser.
 * 
 * Uses Edge TTS via backend API call.
 * Safe for Vercel deployment.
 * 
 * Usage:
 *   const { playing, speak, stop } = useTTSResponse();
 */

import { useState, useCallback, useRef } from "react";
import { hamApiFetch } from "@/lib/ham/api";

interface UseTTSResponseOptions {
  onError?: (error: string) => void;
}

export function useTTSResponse(options: UseTTSResponseOptions = {}) {
  const { onError } = options;

  const [playing, setPlaying] = useState(false);
  const [currentText, setCurrentText] = useState<string | null>(null);

  const audioRef = useRef<HTMLAudioElement | null>(null);

  const speak = useCallback(
    async (text: string) => {
      if (!text || playing) return;

      try {
        // Call backend TTS endpoint
        const response = await hamApiFetch("/api/tts/generate", {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
          },
          body: JSON.stringify({ text, voice: "en-US-JennyNeural" }),
        });

        if (!response.ok) {
          throw new Error(`TTS request failed: ${response.status}`);
        }

        // Get audio blob
        const audioBlob = await response.blob();
        const audioUrl = URL.createObjectURL(audioBlob);

        // Create and play audio
        const audio = new Audio(audioUrl);
        audioRef.current = audio;

        audio.play();
        setPlaying(true);
        setCurrentText(text);

        audio.onended = () => {
          setPlaying(false);
          setCurrentText(null);
          URL.revokeObjectURL(audioUrl);
        };

        audio.onerror = () => {
          setPlaying(false);
          onError?.("Failed to play audio");
        };
      } catch (err) {
        const errorMessage = (err as Error)?.message || "TTS generation failed";
        onError?.(errorMessage);
        setPlaying(false);
      }
    },
    [playing, onError],
  );

  const stop = useCallback(() => {
    if (audioRef.current && playing) {
      audioRef.current.pause();
      audioRef.current.currentTime = 0;
      setPlaying(false);
    }
  }, [playing]);

  return {
    playing,
    currentText,
    speak,
    stop,
  };
}
