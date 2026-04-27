/**
 * useVoiceRecorder.ts
 * 
 * Browser-native voice recording hook using MediaRecorder API.
 * 
 * Features:
 * - Start/stop/cancel recording
 * - Blob URL generation for playback
 * - Permission handling
 * - Recording state management
 * - No external dependencies (uses browser MediaRecorder)
 */

import { useState, useRef, useCallback, useEffect } from 'react';

import { mapMediaStreamErrorToUserMessage } from '@/lib/ham/voiceRecordingErrors';

function pickRecorderMimeType(): string {
  const candidates = ['audio/webm;codecs=opus', 'audio/webm'];
  for (const c of candidates) {
    if (typeof MediaRecorder !== 'undefined' && MediaRecorder.isTypeSupported(c)) {
      return c;
    }
  }
  return '';
}

/**
 * `MediaRecorder.abort()` exists in modern browsers but is missing from some `lib.dom` typings,
 * which breaks `tsc --noEmit` in CI. Prefer abort when present; otherwise stop without surfacing a blob.
 */
function safeAbortMediaRecorder(rec: MediaRecorder | null): void {
  if (!rec) return;
  const extended = rec as MediaRecorder & { abort?: () => void };
  if (typeof extended.abort === 'function') {
    extended.abort();
    return;
  }
  const stream = rec.stream;
  rec.ondataavailable = null;
  rec.onstop = () => {
    stream.getTracks().forEach((track) => track.stop());
  };
  try {
    rec.stop();
  } catch {
    stream.getTracks().forEach((track) => track.stop());
  }
}

interface RecordingState {
  isRecording: boolean;
  isPaused: boolean;
  mediaRecorder: MediaRecorder | null;
  audioChunks: BlobPart[];
  blobUrl: string | null;
  error: string | null;
  duration: number;
  startTimestamp: number | null;
  timerInterval: NodeJS.Timeout | null;
}

interface UseVoiceRecorderProps {
  onRecordingComplete?: (blob: Blob, duration: number) => void;
  onRecordingError?: (error: string) => void;
}

export function useVoiceRecorder(props: UseVoiceRecorderProps = {}) {
  const { onRecordingComplete, onRecordingError } = props;
  
  const [state, setState] = useState<RecordingState>({
    isRecording: false,
    isPaused: false,
    mediaRecorder: null,
    audioChunks: [],
    blobUrl: null,
    error: null,
    duration: 0,
    startTimestamp: null,
    timerInterval: null,
  });
  
  const mediaRecorderRef = useRef<MediaRecorder | null>(null);
  const timerIntervalRef = useRef<NodeJS.Timeout | null>(null);
  /** Wall-clock start for accurate duration in `onRecordingComplete` (avoids stale React state in `onstop`). */
  const recordingStartedAtRef = useRef<number | null>(null);

  // Start recording
  const startRecording = useCallback(async () => {
    setState((prev) => ({ ...prev, error: null }));

    if (typeof navigator === 'undefined' || !navigator.mediaDevices?.getUserMedia) {
      const msg =
        'Voice input is not available in this browser. Try a current Chrome or Edge version, or use HTTPS.';
      setState((prev) => ({ ...prev, error: msg }));
      onRecordingError?.(msg);
      return;
    }

    try {
      try {
        const devices = await navigator.mediaDevices.enumerateDevices();
        const inputs = devices.filter((d) => d.kind === 'audioinput');
        if (inputs.length === 0) {
          const msg = mapMediaStreamErrorToUserMessage(
            Object.assign(new Error('No audio input devices'), { name: 'NotFoundError' }),
          );
          setState((prev) => ({ ...prev, error: msg }));
          onRecordingError?.(msg);
          return;
        }
      } catch {
        /* enumerate can fail pre-permission; fall through to getUserMedia */
      }

      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });

      const mime = pickRecorderMimeType();
      const mediaRecorder = mime
        ? new MediaRecorder(stream, { mimeType: mime })
        : new MediaRecorder(stream);

      const chunks: BlobPart[] = [];

      mediaRecorder.ondataavailable = (event) => {
        if (event.data.size > 0) {
          chunks.push(event.data);
        }
      };

      mediaRecorder.onstop = () => {
        const blob = new Blob(chunks, { type: mediaRecorder.mimeType || mime || 'audio/webm' });
        const blobUrl = URL.createObjectURL(blob);
        const started = recordingStartedAtRef.current ?? Date.now();
        recordingStartedAtRef.current = null;
        const durationSecs = Math.max(0, Math.floor((Date.now() - started) / 1000));

        setState((prev) => ({
          ...prev,
          isRecording: false,
          isPaused: false,
          mediaRecorder: null,
          blobUrl,
          audioChunks: [blob],
          duration: durationSecs,
        }));

        // Stop all tracks
        stream.getTracks().forEach(track => track.stop());

        if (timerIntervalRef.current) {
          clearInterval(timerIntervalRef.current);
        }

        onRecordingComplete?.(blob, durationSecs);
      };

      mediaRecorder.onerror = (event) => {
        const raw = event.error ?? new Error('Unknown media recorder error');
        const msg = mapMediaStreamErrorToUserMessage(raw);
        setState((prev) => ({ ...prev, error: msg }));
        onRecordingError?.(msg);
      };

      mediaRecorder.start(1000); // Data interval in ms

      mediaRecorderRef.current = mediaRecorder;
      recordingStartedAtRef.current = Date.now();

      setState((prev) => ({
        ...prev,
        isRecording: true,
        isPaused: false,
        mediaRecorder,
        audioChunks: chunks,
        blobUrl: null,
        error: null,
        startTimestamp: Date.now(),
        duration: 0,
      }));

      // Timer for duration tracking
      timerIntervalRef.current = setInterval(() => {
        setState((prev) => ({
          ...prev,
          duration: Math.floor((Date.now() - (prev.startTimestamp || Date.now())) / 1000),
        }));
      }, 1000);

    } catch (err) {
      const msg = mapMediaStreamErrorToUserMessage(err);
      setState((prev) => ({ ...prev, error: msg }));
      onRecordingError?.(msg);
    }
  }, [onRecordingComplete, onRecordingError]);

  // Stop recording — use MediaRecorder.state, not React state; `state.isRecording` in the closure
  // can be stale so Stop would no-op after mic UI already shows recording.
  const stopRecording = useCallback(() => {
    const rec = mediaRecorderRef.current;
    if (!rec) return;
    if (rec.state !== "recording" && rec.state !== "paused") return;
    try {
      if (typeof rec.requestData === "function") {
        rec.requestData();
      }
      rec.stop();
    } finally {
      mediaRecorderRef.current = null;
    }
  }, []);

  // Cancel recording (discard)
  const cancelRecording = useCallback(() => {
    const rec = mediaRecorderRef.current;
    if (rec && (rec.state === "recording" || rec.state === "paused")) {
      safeAbortMediaRecorder(rec);
      mediaRecorderRef.current = null;
    }

    // Stop timer
    if (timerIntervalRef.current) {
      clearInterval(timerIntervalRef.current);
      timerIntervalRef.current = null;
    }

    setState((prev) => {
      const mr = prev.mediaRecorder;
      if (mr?.stream) {
        mr.stream.getTracks().forEach((track) => track.stop());
      }
      return {
        ...prev,
        isRecording: false,
        isPaused: false,
        mediaRecorder: null,
        audioChunks: [],
        blobUrl: null,
        duration: 0,
        error: null,
      };
    });

    timerIntervalRef.current = null;
    recordingStartedAtRef.current = null;
  }, []);

  // Cleanup on unmount
  useEffect(() => {
    return () => {
      if (mediaRecorderRef.current) {
        safeAbortMediaRecorder(mediaRecorderRef.current);
        mediaRecorderRef.current = null;
      }

      if (timerIntervalRef.current) {
        clearInterval(timerIntervalRef.current);
        timerIntervalRef.current = null;
      }

      // Stop all tracks
      if (state.mediaRecorder?.stream) {
        state.mediaRecorder.stream.getTracks().forEach(track => track.stop());
      }

      if (state.blobUrl) {
        URL.revokeObjectURL(state.blobUrl);
      }
    };
  }, [state.mediaRecorder, state.blobUrl]);

  return {
    ...state,
    startRecording,
    stopRecording,
    cancelRecording,
  };
}
