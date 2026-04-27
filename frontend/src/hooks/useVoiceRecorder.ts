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
  const activeStreamRef = useRef<MediaStream | null>(null);
  const audioChunksRef = useRef<BlobPart[]>([]);
  const finalizedRef = useRef<boolean>(true);
  const stopWatchdogRef = useRef<NodeJS.Timeout | null>(null);
  const timerIntervalRef = useRef<NodeJS.Timeout | null>(null);
  /** Wall-clock start for accurate duration in `onRecordingComplete` (avoids stale React state in `onstop`). */
  const recordingStartedAtRef = useRef<number | null>(null);

  const clearStopWatchdog = useCallback(() => {
    if (stopWatchdogRef.current) {
      clearTimeout(stopWatchdogRef.current);
      stopWatchdogRef.current = null;
    }
  }, []);

  const clearDurationTimer = useCallback(() => {
    if (timerIntervalRef.current) {
      clearInterval(timerIntervalRef.current);
      timerIntervalRef.current = null;
    }
  }, []);

  const finalizeRecording = useCallback(
    (opts: { mimeType?: string; fallbackError?: string } = {}) => {
      if (finalizedRef.current) return;
      finalizedRef.current = true;
      clearStopWatchdog();
      clearDurationTimer();

      const stream = activeStreamRef.current;
      activeStreamRef.current = null;
      if (stream) {
        stream.getTracks().forEach((track) => track.stop());
      }

      const chunks = audioChunksRef.current;
      audioChunksRef.current = [];
      const started = recordingStartedAtRef.current ?? Date.now();
      recordingStartedAtRef.current = null;
      const durationSecs = Math.max(0, Math.floor((Date.now() - started) / 1000));

      const blob =
        chunks.length > 0
          ? new Blob(chunks, { type: opts.mimeType || 'audio/webm' })
          : null;
      const blobUrl = blob ? URL.createObjectURL(blob) : null;
      const fallbackError = opts.fallbackError ?? null;

      setState((prev) => ({
        ...prev,
        isRecording: false,
        isPaused: false,
        mediaRecorder: null,
        audioChunks: blob ? [blob] : [],
        blobUrl,
        duration: durationSecs,
        error: fallbackError,
      }));

      if (fallbackError) {
        onRecordingError?.(fallbackError);
      }
      if (blob && blob.size > 0) {
        onRecordingComplete?.(blob, durationSecs);
      }
    },
    [clearDurationTimer, clearStopWatchdog, onRecordingComplete, onRecordingError],
  );

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

      // Avoid orphaning a live MediaRecorder if start runs twice (double-click / Strict Mode churn).
      const existing = mediaRecorderRef.current;
      if (existing && (existing.state === "recording" || existing.state === "paused")) {
        stream.getTracks().forEach((t) => t.stop());
        return;
      }
      if (existing?.state === "inactive") {
        mediaRecorderRef.current = null;
      }

      const mime = pickRecorderMimeType();
      const mediaRecorder = mime
        ? new MediaRecorder(stream, { mimeType: mime })
        : new MediaRecorder(stream);
      activeStreamRef.current = stream;
      audioChunksRef.current = [];
      finalizedRef.current = false;
      clearStopWatchdog();

      mediaRecorder.ondataavailable = (event) => {
        if (event.data.size > 0) {
          audioChunksRef.current.push(event.data);
        }
      };

      mediaRecorder.onstop = () => {
        mediaRecorderRef.current = null;
        finalizeRecording({ mimeType: mediaRecorder.mimeType || mime || 'audio/webm' });
      };

      mediaRecorder.onerror = (event) => {
        const raw = event.error ?? new Error('Unknown media recorder error');
        const msg = mapMediaStreamErrorToUserMessage(raw);
        finalizeRecording({
          mimeType: mediaRecorder.mimeType || mime || 'audio/webm',
          fallbackError: msg,
        });
      };

      mediaRecorder.start(1000); // Data interval in ms

      mediaRecorderRef.current = mediaRecorder;
      recordingStartedAtRef.current = Date.now();

      setState((prev) => ({
        ...prev,
        isRecording: true,
        isPaused: false,
        mediaRecorder,
        audioChunks: [],
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
  }, [clearStopWatchdog, finalizeRecording, onRecordingError]);

  // Stop recording — use MediaRecorder.state, not React state; `state.isRecording` in the closure
  // can be stale so Stop would no-op after mic UI already shows recording.
  const stopRecording = useCallback(() => {
    const rec = mediaRecorderRef.current;
    if (!rec) {
      finalizeRecording({
        fallbackError: "Recording stopped unexpectedly before audio finalized.",
      });
      return;
    }
    if (rec.state === "inactive") {
      mediaRecorderRef.current = null;
      finalizeRecording({
        mimeType: rec.mimeType || 'audio/webm',
        fallbackError: "Recorder became inactive before stop completed.",
      });
      return;
    }
    if (rec.state !== "recording" && rec.state !== "paused") {
      return;
    }
    try {
      rec.stop();
    } catch {
      mediaRecorderRef.current = null;
      finalizeRecording({
        mimeType: rec.mimeType || 'audio/webm',
        fallbackError: "Recorder stop failed before onstop fired.",
      });
      return;
    }
    clearStopWatchdog();
    stopWatchdogRef.current = setTimeout(() => {
      if (!finalizedRef.current) {
        mediaRecorderRef.current = null;
        finalizeRecording({
          mimeType: rec.mimeType || 'audio/webm',
          fallbackError: "Recorder stop timed out before finalization.",
        });
      }
    }, 2000);
  }, [clearStopWatchdog, finalizeRecording]);

  // Cancel recording (discard)
  const cancelRecording = useCallback(() => {
    const rec = mediaRecorderRef.current;
    if (rec) {
      safeAbortMediaRecorder(rec);
      mediaRecorderRef.current = null;
    }
    clearStopWatchdog();
    clearDurationTimer();
    const stream = activeStreamRef.current;
    activeStreamRef.current = null;
    if (stream) {
      stream.getTracks().forEach((track) => track.stop());
    }
    audioChunksRef.current = [];
    finalizedRef.current = true;
    setState((prev) => ({
      ...prev,
      isRecording: false,
      isPaused: false,
      mediaRecorder: null,
      audioChunks: [],
      blobUrl: null,
      duration: 0,
      error: null,
    }));
    recordingStartedAtRef.current = null;
  }, [clearDurationTimer, clearStopWatchdog]);

  // Cleanup on unmount
  useEffect(() => {
    return () => {
      if (mediaRecorderRef.current) {
        safeAbortMediaRecorder(mediaRecorderRef.current);
        mediaRecorderRef.current = null;
      }
      if (activeStreamRef.current) {
        activeStreamRef.current.getTracks().forEach((track) => track.stop());
        activeStreamRef.current = null;
      }

      clearDurationTimer();
      clearStopWatchdog();
      audioChunksRef.current = [];
      finalizedRef.current = true;

      // Stop all tracks
      if (state.mediaRecorder?.stream) {
        state.mediaRecorder.stream.getTracks().forEach(track => track.stop());
      }

      if (state.blobUrl) {
        URL.revokeObjectURL(state.blobUrl);
      }
    };
  }, [clearDurationTimer, clearStopWatchdog, state.mediaRecorder, state.blobUrl]);

  return {
    ...state,
    startRecording,
    stopRecording,
    cancelRecording,
  };
}
