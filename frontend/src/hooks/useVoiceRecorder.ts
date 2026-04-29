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

const VOICE_DEBUG_FLAG = 'ham.voiceDebug';
const VOICE_DEBUG_MAX_EVENTS = 500;

type VoiceDebugPayload = Record<string, unknown> & {
  event: string;
  ts: number;
};

function voiceDebugEnabled(): boolean {
  if (typeof window === 'undefined') return false;
  try {
    return window.localStorage.getItem(VOICE_DEBUG_FLAG) === '1';
  } catch {
    return false;
  }
}

function pushVoiceDebug(payload: Omit<VoiceDebugPayload, 'ts'>): void {
  if (!voiceDebugEnabled() || typeof window === 'undefined') return;
  const event = { ...(payload as Record<string, unknown>), ts: Date.now() } as VoiceDebugPayload;
  const w = window as unknown as { __HAM_VOICE_DEBUG__?: VoiceDebugPayload[] };
  const next = Array.isArray(w.__HAM_VOICE_DEBUG__) ? [...w.__HAM_VOICE_DEBUG__, event] : [event];
  if (next.length > VOICE_DEBUG_MAX_EVENTS) {
    next.splice(0, next.length - VOICE_DEBUG_MAX_EVENTS);
  }
  w.__HAM_VOICE_DEBUG__ = next;
  console.debug('[ham.voice]', event);
}

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
  const hookInstanceId = useRef(`vr-${Math.random().toString(36).slice(2, 9)}`);
  const recorderSeqRef = useRef(0);
  const recorderIdRef = useRef<string | null>(null);
  
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
  const latestBlobUrlRef = useRef<string | null>(null);

  useEffect(() => {
    latestBlobUrlRef.current = state.blobUrl;
  }, [state.blobUrl]);

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
      pushVoiceDebug({
        event: 'voice.finalize.called',
        hookInstanceId: hookInstanceId.current,
        recorderId: recorderIdRef.current,
        hasStream: Boolean(stream),
        fallbackError,
        chunkCount: chunks.length,
      });

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
      pushVoiceDebug({
        event: 'voice.finalize.blob_size',
        hookInstanceId: hookInstanceId.current,
        recorderId: recorderIdRef.current,
        blobSize: blob?.size ?? 0,
      });
      pushVoiceDebug({
        event: 'voice.blob.finalized',
        hookInstanceId: hookInstanceId.current,
        recorderId: recorderIdRef.current,
        blobSize: blob?.size ?? 0,
      });
      if (blob && blob.size > 0) {
        pushVoiceDebug({
          event: 'voice.complete.called',
          hookInstanceId: hookInstanceId.current,
          recorderId: recorderIdRef.current,
          blobSize: blob.size,
        });
        onRecordingComplete?.(blob, durationSecs);
      }
      recorderIdRef.current = null;
    },
    [clearDurationTimer, clearStopWatchdog, onRecordingComplete, onRecordingError],
  );

  // Start recording
  const startRecording = useCallback(async () => {
    pushVoiceDebug({
      event: 'voice.mic.preflight',
      hookInstanceId: hookInstanceId.current,
      hasNavigator: typeof navigator !== 'undefined',
      hasMediaDevices: typeof navigator !== 'undefined' && Boolean(navigator.mediaDevices),
      hasGetUserMedia:
        typeof navigator !== 'undefined' && Boolean(navigator.mediaDevices?.getUserMedia),
    });
    pushVoiceDebug({
      event: 'voice.start.called',
      hookInstanceId: hookInstanceId.current,
      isRecording: state.isRecording,
      refExists: Boolean(mediaRecorderRef.current),
      refState: mediaRecorderRef.current?.state ?? null,
    });
    setState((prev) => ({ ...prev, error: null }));

    if (typeof navigator === 'undefined' || !navigator.mediaDevices?.getUserMedia) {
      const msg =
        'Voice input is not available in this browser. Try a current Chrome or Edge version, or use HTTPS.';
      setState((prev) => ({ ...prev, error: msg }));
      onRecordingError?.(msg);
      return;
    }

    try {
      if (typeof navigator.permissions?.query === 'function') {
        try {
          const permission = await navigator.permissions.query({ name: 'microphone' as PermissionName });
          pushVoiceDebug({
            event: 'voice.mic.permission_state',
            hookInstanceId: hookInstanceId.current,
            state: permission.state,
          });
        } catch (permissionErr) {
          pushVoiceDebug({
            event: 'voice.mic.permission_state',
            hookInstanceId: hookInstanceId.current,
            state: 'unknown',
            error:
              permissionErr instanceof Error
                ? permissionErr.message
                : String(permissionErr ?? 'permission_query_failed'),
          });
        }
      }

      pushVoiceDebug({
        event: 'voice.mic.get_user_media.called',
        hookInstanceId: hookInstanceId.current,
      });
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      pushVoiceDebug({
        event: 'voice.mic.get_user_media.success',
        hookInstanceId: hookInstanceId.current,
        trackCount: stream.getAudioTracks().length,
      });

      try {
        const devices = await navigator.mediaDevices.enumerateDevices();
        const inputs = devices.filter((d) => d.kind === 'audioinput');
        pushVoiceDebug({
          event: 'voice.mic.devices_after_permission',
          hookInstanceId: hookInstanceId.current,
          audioInputCount: inputs.length,
        });
      } catch {
        pushVoiceDebug({
          event: 'voice.mic.devices_after_permission',
          hookInstanceId: hookInstanceId.current,
          audioInputCount: null,
          error: 'enumerate_failed',
        });
      }

      // Avoid orphaning a live MediaRecorder if start runs twice (double-click / Strict Mode churn).
      const existing = mediaRecorderRef.current;
      if (existing && (existing.state === "recording" || existing.state === "paused")) {
        pushVoiceDebug({
          event: 'voice.stop.early_return',
          reason: 'start_blocked_existing_recorder',
          hookInstanceId: hookInstanceId.current,
          recorderId: recorderIdRef.current,
          recState: existing.state,
        });
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
      recorderSeqRef.current += 1;
      recorderIdRef.current = `${hookInstanceId.current}-rec-${recorderSeqRef.current}`;
      activeStreamRef.current = stream;
      audioChunksRef.current = [];
      finalizedRef.current = false;
      clearStopWatchdog();

      mediaRecorder.ondataavailable = (event) => {
        pushVoiceDebug({
          event: 'voice.ondataavailable',
          hookInstanceId: hookInstanceId.current,
          recorderId: recorderIdRef.current,
          dataSize: event.data.size,
          recState: mediaRecorder.state,
        });
        if (event.data.size > 0) {
          audioChunksRef.current.push(event.data);
        }
      };

      mediaRecorder.onstop = () => {
        pushVoiceDebug({
          event: 'voice.onstop',
          hookInstanceId: hookInstanceId.current,
          recorderId: recorderIdRef.current,
          chunkCount: audioChunksRef.current.length,
          recState: mediaRecorder.state,
        });
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
      pushVoiceDebug({
        event: 'voice.start.success',
        hookInstanceId: hookInstanceId.current,
        recorderId: recorderIdRef.current,
        recState: mediaRecorder.state,
      });

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
      pushVoiceDebug({
        event: 'voice.mic.get_user_media.error',
        hookInstanceId: hookInstanceId.current,
        errorName: err instanceof Error ? err.name : null,
        errorMessage: err instanceof Error ? err.message : String(err ?? ''),
      });
      pushVoiceDebug({
        event: 'voice.start.error',
        hookInstanceId: hookInstanceId.current,
        error: msg,
      });
      setState((prev) => ({ ...prev, error: msg }));
      onRecordingError?.(msg);
    }
  }, [clearStopWatchdog, finalizeRecording, onRecordingError, state.isRecording]);

  // Stop recording — use MediaRecorder.state, not React state; `state.isRecording` in the closure
  // can be stale so Stop would no-op after mic UI already shows recording.
  const stopRecording = useCallback(() => {
    const rec = mediaRecorderRef.current;
    pushVoiceDebug({
      event: 'voice.stop.called',
      hookInstanceId: hookInstanceId.current,
      recorderId: recorderIdRef.current,
      refExists: Boolean(rec),
      recState: rec?.state ?? null,
      isRecording: state.isRecording,
    });
    pushVoiceDebug({
      event: 'voice.stop.ref_state',
      hookInstanceId: hookInstanceId.current,
      recorderId: recorderIdRef.current,
      refExists: Boolean(rec),
      recState: rec?.state ?? null,
    });
    if (!rec) {
      setState((prev) => ({
        ...prev,
        isRecording: false,
        isPaused: false,
      }));
      pushVoiceDebug({
        event: 'voice.stop.early_return',
        hookInstanceId: hookInstanceId.current,
        recorderId: recorderIdRef.current,
        reason: 'ref_null',
      });
      finalizeRecording({
        fallbackError: "Recording stopped unexpectedly before audio finalized.",
      });
      return;
    }
    if (rec.state === "inactive") {
      setState((prev) => ({
        ...prev,
        isRecording: false,
        isPaused: false,
      }));
      pushVoiceDebug({
        event: 'voice.stop.early_return',
        hookInstanceId: hookInstanceId.current,
        recorderId: recorderIdRef.current,
        reason: 'rec_inactive',
      });
      mediaRecorderRef.current = null;
      finalizeRecording({
        mimeType: rec.mimeType || 'audio/webm',
        fallbackError: "Recorder became inactive before stop completed.",
      });
      return;
    }
    if (rec.state !== "recording" && rec.state !== "paused") {
      pushVoiceDebug({
        event: 'voice.stop.early_return',
        hookInstanceId: hookInstanceId.current,
        recorderId: recorderIdRef.current,
        reason: 'rec_state_not_stoppable',
        recState: rec.state,
      });
      return;
    }
    // Move UI out of "recording" immediately on stop request; do not wait for onstop.
    setState((prev) => ({
      ...prev,
      isRecording: false,
      isPaused: false,
    }));
    try {
      rec.stop();
      pushVoiceDebug({
        event: 'voice.stop.rec_stop_called',
        hookInstanceId: hookInstanceId.current,
        recorderId: recorderIdRef.current,
        recState: rec.state,
      });
    } catch {
      pushVoiceDebug({
        event: 'voice.stop.rec_stop_error',
        hookInstanceId: hookInstanceId.current,
        recorderId: recorderIdRef.current,
        recState: rec.state,
      });
      mediaRecorderRef.current = null;
      finalizeRecording({
        mimeType: rec.mimeType || 'audio/webm',
        fallbackError: "Recorder stop failed before onstop fired.",
      });
      return;
    }
    clearStopWatchdog();
    pushVoiceDebug({
      event: 'voice.watchdog.started',
      hookInstanceId: hookInstanceId.current,
      recorderId: recorderIdRef.current,
    });
    stopWatchdogRef.current = setTimeout(() => {
      if (!finalizedRef.current) {
        pushVoiceDebug({
          event: 'voice.watchdog.fired',
          hookInstanceId: hookInstanceId.current,
          recorderId: recorderIdRef.current,
          recState: rec.state,
        });
        mediaRecorderRef.current = null;
        finalizeRecording({
          mimeType: rec.mimeType || 'audio/webm',
          fallbackError: "Recorder stop timed out before finalization.",
        });
      }
    }, 2000);
  }, [clearStopWatchdog, finalizeRecording, state.isRecording]);

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
    pushVoiceDebug({
      event: 'voice.render',
      hookInstanceId: hookInstanceId.current,
      isRecording: state.isRecording,
      recState: mediaRecorderRef.current?.state ?? null,
      refExists: Boolean(mediaRecorderRef.current),
    });
  }, [state.isRecording]);

  // Cleanup on unmount only
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

      if (latestBlobUrlRef.current) {
        URL.revokeObjectURL(latestBlobUrlRef.current);
        latestBlobUrlRef.current = null;
      }
    };
  }, [clearDurationTimer, clearStopWatchdog]);

  return {
    ...state,
    startRecording,
    stopRecording,
    cancelRecording,
  };
}
