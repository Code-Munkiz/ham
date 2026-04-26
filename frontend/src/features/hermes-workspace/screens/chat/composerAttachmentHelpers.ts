/**
 * Local-only composer attachments: inlined into outbound user text (same contract as legacy `Chat.tsx`).
 * No `HamChatRequest` shape change — server receives a single user message string.
 */
export type WorkspaceComposerAttachmentKind = "image" | "text" | "binary";

export type WorkspaceComposerAttachment = {
  id: string;
  name: string;
  size: number;
  kind: WorkspaceComposerAttachmentKind;
  payload: string;
};

export const MAX_WORKSPACE_ATTACHMENT_BYTES = 500 * 1024;

export const WORKSPACE_ATTACHMENT_ACCEPT =
  "image/*,.txt,.csv,.json,.pdf,.xlsx,text/plain,text/csv,application/json,application/pdf,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet";

const TEXT_FILE_EXTENSIONS = new Set([".txt", ".csv", ".json"]);
const IMAGE_FILE_EXTENSIONS = new Set([
  ".png",
  ".jpg",
  ".jpeg",
  ".gif",
  ".webp",
  ".svg",
  ".bmp",
  ".ico",
]);

function fileExtensionLower(name: string): string {
  const i = name.lastIndexOf(".");
  return i >= 0 ? name.slice(i).toLowerCase() : "";
}

export function formatAttachmentByteSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  const kb = bytes / 1024;
  if (kb < 1024) return `${kb >= 10 ? kb.toFixed(0) : kb.toFixed(1)} KB`;
  return `${(kb / 1024).toFixed(1)} MB`;
}

function classifyAttachment(file: File): WorkspaceComposerAttachmentKind {
  const ext = fileExtensionLower(file.name);
  if (file.type.startsWith("image/") || IMAGE_FILE_EXTENSIONS.has(ext)) return "image";
  if (
    TEXT_FILE_EXTENSIONS.has(ext) ||
    file.type.startsWith("text/") ||
    file.type === "application/json" ||
    file.type === "text/csv"
  ) {
    return "text";
  }
  return "binary";
}

function readFileAsDataURL(file: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const r = new FileReader();
    r.onload = () => {
      const res = r.result;
      if (typeof res === "string") resolve(res);
      else reject(new Error("Could not read file as data URL"));
    };
    r.onerror = () => reject(r.error ?? new Error("File read failed"));
    r.readAsDataURL(file);
  });
}

function readFileAsText(file: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const r = new FileReader();
    r.onload = () => {
      const res = r.result;
      if (typeof res === "string") resolve(res);
      else reject(new Error("Could not read file as text"));
    };
    r.onerror = () => reject(r.error ?? new Error("File read failed"));
    r.readAsText(file);
  });
}

function binaryAttachmentPlaceholder(name: string, size: number): string {
  return `[Attached: ${name} (${formatAttachmentByteSize(size)}) — contents not inlined for this file type.]`;
}

export function buildOutboundMessageWithAttachment(
  trimmedText: string,
  attachment: WorkspaceComposerAttachment | null,
): string {
  if (!attachment) return trimmedText;
  if (attachment.kind === "binary") {
    const block = binaryAttachmentPlaceholder(attachment.name, attachment.size);
    return trimmedText ? `${block}\n\n${trimmedText}` : block;
  }
  const header =
    attachment.kind === "image"
      ? `[Attached image: ${attachment.name} (${formatAttachmentByteSize(attachment.size)})]`
      : `[Attached file: ${attachment.name} (${formatAttachmentByteSize(attachment.size)})]`;
  const body = attachment.payload.trimEnd();
  const combined = `${header}\n${body}`;
  return trimmedText ? `${combined}\n\n${trimmedText}` : combined;
}

export async function fileToWorkspaceAttachment(
  file: File,
): Promise<WorkspaceComposerAttachment | null> {
  if (file.size > MAX_WORKSPACE_ATTACHMENT_BYTES) {
    return null;
  }
  const id = `hww-att-${Date.now()}-${Math.random().toString(36).slice(2, 9)}`;
  const name = file.name || "attachment";
  const size = file.size;
  const kind = classifyAttachment(file);
  if (kind === "image") {
    const dataUrl = await readFileAsDataURL(file);
    return { id, name, size, kind: "image", payload: dataUrl };
  }
  if (kind === "text") {
    const t = await readFileAsText(file);
    return { id, name, size, kind: "text", payload: t };
  }
  return { id, name, size, kind: "binary", payload: "" };
}
