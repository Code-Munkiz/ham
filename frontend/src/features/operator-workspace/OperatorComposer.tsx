import type * as React from "react";
import { Loader2, Mic, Paperclip, SendHorizontal, X } from "lucide-react";
import type { OperatorAttachment } from "./types";
import { useWorkspaceAttachments } from "./useWorkspaceAttachments";
import { useWorkspaceVoice } from "./useWorkspaceVoice";

type OperatorComposerProps = {
  input: string;
  sending: boolean;
  voiceTranscribing: boolean;
  pipelineStatus: string;
  chatError: string | null;
  attachment: OperatorAttachment | null;
  attachmentAccept: string;
  onInputChange: (value: string) => void;
  onAttachmentSelect: (file: File) => void;
  onAttachmentClear: () => void;
  onDictationText: (text: string) => void;
  onVoiceBlob: (blob: Blob) => void;
  onVoiceError: (message: string) => void;
  onSend: (event: React.FormEvent<HTMLFormElement>) => void;
};

export function OperatorComposer({
  input,
  sending,
  voiceTranscribing,
  pipelineStatus,
  chatError,
  attachment,
  attachmentAccept,
  onInputChange,
  onAttachmentSelect,
  onAttachmentClear,
  onDictationText,
  onVoiceBlob,
  onVoiceError,
  onSend,
}: OperatorComposerProps) {
  const attachments = useWorkspaceAttachments({ onSelectFile: onAttachmentSelect });
  const voice = useWorkspaceVoice({
    onDictationText,
    onVoiceBlob,
    onError: onVoiceError,
  });

  const sendDisabled = sending || voiceTranscribing || (!input.trim() && !attachment);

  return (
    <div
      className="ow-composer-wrap shrink-0 px-3 pb-3 pt-2"
      onDragEnter={attachments.onDragEnter}
      onDragLeave={attachments.onDragLeave}
      onDragOver={attachments.onDragOver}
      onDrop={attachments.onDrop}
    >
      <div className="ow-pipeline-line mb-2" title="Chat gateway status">
        <span className="ow-pipeline-pill">{pipelineStatus}</span>
      </div>
      {chatError ? (
        <div className="mb-2 rounded-xl border border-destructive/45 bg-destructive/12 px-3 py-2 text-xs text-destructive">
          {chatError}
        </div>
      ) : null}
      {attachment ? (
        <div className="mb-2 flex items-center justify-between gap-3 rounded-xl border border-white/10 bg-[#0b1118]/65 px-3 py-2 text-xs text-white/80">
          <div className="min-w-0">
            <p className="truncate font-semibold">{attachment.name}</p>
            <p className="text-[11px] text-white/45 uppercase">
              {attachment.kind} attached
            </p>
          </div>
          <button
            type="button"
            onClick={onAttachmentClear}
            className="inline-flex h-7 w-7 items-center justify-center rounded-full border border-white/15 bg-black/30 text-white/70"
            aria-label="Remove attachment"
          >
            <X className="h-3.5 w-3.5" />
          </button>
        </div>
      ) : null}
      {attachments.isDraggingOver ? (
        <div className="mb-2 rounded-xl border border-dashed border-[#ff9a4a]/60 bg-[#ff9a4a]/10 px-3 py-2 text-xs text-[#ffcfaa]">
          Drop a file to attach it to this message.
        </div>
      ) : null}
      <form onSubmit={onSend} className="ow-composer-shell space-y-2">
        <input
          ref={attachments.inputRef}
          type="file"
          accept={attachmentAccept}
          className="hidden"
          onChange={attachments.onInputChange}
        />
        <textarea
          value={input}
          onChange={(event) => onInputChange(event.target.value)}
          placeholder="Message the workspace…"
          className="min-h-[88px] w-full resize-y rounded-2xl border border-white/10 bg-[#0a141f]/80 px-3 py-2 text-sm text-white outline-none placeholder:text-white/30 focus-visible:ring-2 focus-visible:ring-[#ff6b00]/45"
          disabled={sending || voiceTranscribing}
        />
        <div className="flex items-center justify-between gap-2">
          <div className="flex items-center gap-2">
            <button
              type="button"
              className="inline-flex items-center gap-1 rounded-full border border-white/15 bg-white/5 px-2.5 py-1 text-xs text-white/70 opacity-95"
              onClick={attachments.openPicker}
              title="Attach file"
            >
              <Paperclip className="h-3.5 w-3.5" />
              Attachment
            </button>
            <button
              type="button"
              title={
                voice.isRecording
                  ? "Release to stop voice note recording"
                  : voice.isListening
                    ? "Stop dictation"
                    : voice.isServerDictationMode
                      ? "Tap to record for HAM transcription, hold for push-to-talk"
                      : "Tap to dictate, hold to record a voice note"
              }
              className="inline-flex items-center gap-1 rounded-full border border-white/15 bg-white/5 px-2.5 py-1 text-xs text-white/70 opacity-95"
              onPointerDown={voice.onVoicePointerDown}
              onPointerUp={voice.onVoicePointerUp}
              onPointerCancel={voice.onVoicePointerUp}
              onClick={voice.onVoiceClick}
            >
              <Mic className="h-3.5 w-3.5" />
              {voice.isRecording
                ? `Recording ${voice.recordingSeconds}s`
                : voice.isListening
                  ? "Listening"
                  : voice.isServerDictationMode
                    ? "Record"
                    : "Voice"}
            </button>
            {voiceTranscribing ? (
              <span className="inline-flex items-center gap-1 text-[11px] text-white/55">
                <Loader2 className="h-3 w-3 animate-spin" />
                Transcribing
              </span>
            ) : null}
          </div>
          <button
            type="submit"
            disabled={sendDisabled}
            className="inline-flex items-center gap-1 rounded-full bg-[#ff9a4a] px-3 py-1.5 text-xs font-semibold text-black disabled:cursor-not-allowed disabled:opacity-60"
          >
            <SendHorizontal className="h-3.5 w-3.5" />
            {sending ? "Sending..." : "Send"}
          </button>
        </div>
      </form>
    </div>
  );
}

