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
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      
      const mediaRecorder = new MediaRecorder(stream, {
        mimeType: 'audio/webm;codecs=opus',
      });

      const chunks: BlobPart[] = [];

      mediaRecorder.ondataavailable = (event) => {
        if (event.data.size > 0) {
          chunks.push(event.data);
        }
      };

      mediaRecorder.onstop = () => {
        const blob = new Blob(chunks, { type: 'audio/webm' });
        const blobUrl = URL.createObjectURL(blob);
        const started = recordingStartedAtRef.current ?? Date.now();
        recordingStartedAtRef.current = null;
        const durationSecs = Math.max(0, Math.floor((Date.now() - started) / 1000));

        setState((prev) => ({
          ...prev,
          isRecording: false,
          isPaused: false,
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
        const error = (event.error as Error)?.message || 'Unknown media recorder error';
        setState((prev) => ({ ...prev, error }));
        onRecordingError?.(error);
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
      const error = (err as Error)?.message || 'Failed to access microphone';
      setState((prev) => ({ ...prev, error }));
      onRecordingError?.(error);
    }
  }, [onRecordingComplete, onRecordingError]);

  // Stop recording
  const stopRecording = useCallback(() => {
    if (mediaRecorderRef.current && state.isRecording) {
      mediaRecorderRef.current.stop();
      mediaRecorderRef.current = null;
    }
  }, [state.isRecording]);

  // Cancel recording (discard)
  const cancelRecording = useCallback(() => {
    if (mediaRecorderRef.current && state.isRecording) {
      safeAbortMediaRecorder(mediaRecorderRef.current);
      mediaRecorderRef.current = null;
    }

    // Stop timer
    if (timerIntervalRef.current) {
      clearInterval(timerIntervalRef.current);
      timerIntervalRef.current = null;
    }

    // Stop all tracks
    const currentRecorder = state.mediaRecorder;
    if (currentRecorder?.stream) {
      currentRecorder.stream.getTracks().forEach(track => track.stop());
    }

    setState((prev) => ({
      ...prev,
      isRecording: false,
      isPaused: false,
      audioChunks: [],
      blobUrl: null,
      duration: 0,
      error: null,
    }));

    timerIntervalRef.current = null;
    recordingStartedAtRef.current = null;
  }, [state.isRecording, state.mediaRecorder]);

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
