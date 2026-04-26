import * as React from "react";

type UseWorkspaceVoiceOptions = {
  onDictationText: (text: string) => void;
  onVoiceBlob: (blob: Blob) => void;
  onError: (message: string) => void;
};

type SpeechRecognitionLike = {
  continuous: boolean;
  interimResults: boolean;
  lang: string;
  start: () => void;
  stop: () => void;
  onresult: ((event: any) => void) | null;
  onerror: ((event: any) => void) | null;
  onend: (() => void) | null;
};

type SpeechRecognitionCtor = new () => SpeechRecognitionLike;

function getSpeechRecognitionCtor(): SpeechRecognitionCtor | null {
  if (typeof window === "undefined") return null;
  const win = window as unknown as {
    SpeechRecognition?: SpeechRecognitionCtor;
    webkitSpeechRecognition?: SpeechRecognitionCtor;
  };
  return win.SpeechRecognition ?? win.webkitSpeechRecognition ?? null;
}

export function useWorkspaceVoice({
  onDictationText,
  onVoiceBlob,
  onError,
}: UseWorkspaceVoiceOptions) {
  const speechCtor = getSpeechRecognitionCtor();
  const dictationSupported = Boolean(speechCtor);
  const recordingSupported =
    typeof navigator !== "undefined" &&
    Boolean(navigator.mediaDevices?.getUserMedia) &&
    typeof MediaRecorder !== "undefined";

  const [isListening, setIsListening] = React.useState(false);
  const [isRecording, setIsRecording] = React.useState(false);
  const [recordingSeconds, setRecordingSeconds] = React.useState(0);
  const [forceServerDictation, setForceServerDictation] = React.useState(!dictationSupported);

  const recognitionRef = React.useRef<SpeechRecognitionLike | null>(null);
  const recorderRef = React.useRef<MediaRecorder | null>(null);
  const streamRef = React.useRef<MediaStream | null>(null);
  const chunksRef = React.useRef<BlobPart[]>([]);
  const longPressTimerRef = React.useRef<number | null>(null);
  const longPressArmedRef = React.useRef(false);
  const ignoreClickRef = React.useRef(false);
  const durationTimerRef = React.useRef<number | null>(null);

  const stopRecordingTimer = React.useCallback(() => {
    if (durationTimerRef.current) {
      window.clearInterval(durationTimerRef.current);
      durationTimerRef.current = null;
    }
  }, []);

  const stopRecording = React.useCallback(() => {
    const rec = recorderRef.current;
    if (!rec || rec.state === "inactive") return;
    rec.stop();
    stopRecordingTimer();
    setIsRecording(false);
  }, [stopRecordingTimer]);

  const startRecording = React.useCallback(async () => {
    if (!recordingSupported || isRecording) return;
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      streamRef.current = stream;
      chunksRef.current = [];
      const mimeType = MediaRecorder.isTypeSupported("audio/webm;codecs=opus")
        ? "audio/webm;codecs=opus"
        : "audio/webm";
      const recorder = new MediaRecorder(stream, { mimeType });
      recorderRef.current = recorder;
      recorder.ondataavailable = (event) => {
        if (event.data.size > 0) chunksRef.current.push(event.data);
      };
      recorder.onstop = () => {
        const blob = new Blob(chunksRef.current, { type: recorder.mimeType || "audio/webm" });
        if (blob.size > 0) onVoiceBlob(blob);
        stream.getTracks().forEach((track) => track.stop());
        streamRef.current = null;
        recorderRef.current = null;
        chunksRef.current = [];
        setRecordingSeconds(0);
      };
      recorder.start();
      setRecordingSeconds(0);
      setIsRecording(true);
      durationTimerRef.current = window.setInterval(() => {
        setRecordingSeconds((value) => value + 1);
      }, 1000);
    } catch {
      onError("Microphone access denied or unavailable.");
    }
  }, [isRecording, onError, onVoiceBlob, recordingSupported]);

  const toggleDictation = React.useCallback(() => {
    if (forceServerDictation) {
      if (!recordingSupported) {
        onError("Microphone recording is unavailable in this browser.");
        return;
      }
      if (isRecording) {
        stopRecording();
      } else {
        void startRecording();
      }
      return;
    }
    if (!dictationSupported || !speechCtor) {
      if (!recordingSupported) {
        onError("Speech recognition is unavailable in this browser.");
        return;
      }
      setForceServerDictation(true);
      void startRecording();
      return;
    }
    if (isListening) {
      recognitionRef.current?.stop();
      return;
    }

    const recognition = new speechCtor();
    recognitionRef.current = recognition;
    recognition.continuous = false;
    recognition.interimResults = true;
    recognition.lang = "en-US";

    recognition.onresult = (event) => {
      let finalText = "";
      for (let i = event.resultIndex; i < event.results.length; i += 1) {
        const result = event.results[i];
        if (result.isFinal) {
          finalText += result[0]?.transcript ?? "";
        }
      }
      const next = finalText.trim();
      if (next) onDictationText(next);
    };
    recognition.onerror = (event) => {
      const errorCode =
        event && typeof event === "object" && "error" in event ? String(event.error || "") : "";
      setIsListening(false);
      recognitionRef.current = null;
      if (recordingSupported) {
        setForceServerDictation(true);
        onError("Browser dictation failed. Switched to HAM transcription recording.");
        void startRecording();
        return;
      }
      if (errorCode === "not-allowed" || errorCode === "service-not-allowed") {
        onError("Microphone permission denied for dictation.");
        return;
      }
      onError("Voice dictation failed. Try again.");
    };
    recognition.onend = () => {
      setIsListening(false);
      recognitionRef.current = null;
    };

    try {
      recognition.start();
      setIsListening(true);
    } catch {
      onError("Could not start voice dictation.");
      setIsListening(false);
    }
  }, [
    dictationSupported,
    forceServerDictation,
    isListening,
    isRecording,
    onDictationText,
    onError,
    recordingSupported,
    speechCtor,
    startRecording,
    stopRecording,
  ]);

  const onVoicePointerDown = React.useCallback(() => {
    if (!recordingSupported) return;
    longPressArmedRef.current = false;
    ignoreClickRef.current = false;
    if (longPressTimerRef.current) window.clearTimeout(longPressTimerRef.current);
    longPressTimerRef.current = window.setTimeout(() => {
      longPressArmedRef.current = true;
      ignoreClickRef.current = true;
      void startRecording();
    }, 280);
  }, [recordingSupported, startRecording]);

  const clearLongPress = React.useCallback(() => {
    if (longPressTimerRef.current) {
      window.clearTimeout(longPressTimerRef.current);
      longPressTimerRef.current = null;
    }
  }, []);

  const onVoicePointerUp = React.useCallback(() => {
    clearLongPress();
    if (longPressArmedRef.current) {
      longPressArmedRef.current = false;
      stopRecording();
    }
  }, [clearLongPress, stopRecording]);

  const onVoiceClick = React.useCallback(() => {
    if (ignoreClickRef.current) {
      ignoreClickRef.current = false;
      return;
    }
    toggleDictation();
  }, [toggleDictation]);

  React.useEffect(
    () => () => {
      recognitionRef.current?.stop();
      if (recorderRef.current?.state !== "inactive") recorderRef.current?.stop();
      streamRef.current?.getTracks().forEach((track) => track.stop());
      stopRecordingTimer();
      clearLongPress();
    },
    [clearLongPress, stopRecordingTimer],
  );

  return {
    dictationSupported,
    recordingSupported,
    isServerDictationMode: forceServerDictation,
    isListening,
    isRecording,
    recordingSeconds,
    toggleDictation,
    onVoicePointerDown,
    onVoicePointerUp,
    onVoiceClick,
  };
}

