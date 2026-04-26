/**
 * Local-only composer attachments: inlined into outbound user text (same contract as legacy `Chat.tsx`).
 * No `HamChatRequest` shape change — server receives a single user message string.
 * Supports multiple attachments; optional canvas compression for large images (upstream-style).
 */
export type WorkspaceComposerAttachmentKind = "image" | "text" | "binary";

export type WorkspaceComposerAttachment = {
  id: string;
  name: string;
  size: number;
  kind: WorkspaceComposerAttachmentKind;
  /** Full payload for text/images; empty for binary placeholder. */
  payload: string;
  /** Shown in preview; set when the file could not be fully processed. */
  error?: string;
};

export const MAX_WORKSPACE_ATTACHMENT_BYTES = 500 * 1024;

/** Reasonable cap on simultaneous composer attachments. */
export const MAX_WORKSPACE_ATTACHMENT_COUNT = 8;

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

const MAX_IMAGE_DIMENSION = 1280;
const TARGET_JPEG_QUALITY = 0.75;

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

function isCanvasUsable(): boolean {
  if (typeof document === "undefined") return false;
  try {
    const c = document.createElement("canvas");
    return Boolean(c.getContext("2d"));
  } catch {
    return false;
  }
}

/**
 * Resizes and JPEG-compresses an image to help stay under the HAM 500KB inline cap (best-effort).
 */
function compressImageToDataUrl(file: File): Promise<string | null> {
  if (!isCanvasUsable()) return Promise.resolve(null);
  if (!file.type.startsWith("image/")) return Promise.resolve(null);

  return new Promise((resolve) => {
    const img = new Image();
    const objectUrl = URL.createObjectURL(file);
    const finish = (url: string | null) => {
      URL.revokeObjectURL(objectUrl);
      resolve(url);
    };
    img.onload = () => {
      try {
        let { width, height } = img;
        if (width > MAX_IMAGE_DIMENSION || height > MAX_IMAGE_DIMENSION) {
          if (width > height) {
            height = Math.round((height * MAX_IMAGE_DIMENSION) / width);
            width = MAX_IMAGE_DIMENSION;
          } else {
            width = Math.round((width * MAX_IMAGE_DIMENSION) / height);
            height = MAX_IMAGE_DIMENSION;
          }
        }
        const canvas = document.createElement("canvas");
        canvas.width = width;
        canvas.height = height;
        const ctx = canvas.getContext("2d");
        if (!ctx) {
          finish(null);
          return;
        }
        ctx.drawImage(img, 0, 0, width, height);
        const mime = file.type === "image/png" ? "image/png" : "image/jpeg";
        let quality = TARGET_JPEG_QUALITY;
        let dataUrl = canvas.toDataURL(
          mime === "image/png" ? "image/png" : "image/jpeg",
          mime === "image/png" ? undefined : quality,
        );
        if (mime === "image/jpeg") {
          while (dataUrl.length * 0.75 > MAX_WORKSPACE_ATTACHMENT_BYTES * 1.1 && quality > 0.35) {
            quality -= 0.1;
            dataUrl = canvas.toDataURL("image/jpeg", quality);
          }
        }
        if (dataUrl.length * 0.75 > MAX_WORKSPACE_ATTACHMENT_BYTES) {
          finish(null);
          return;
        }
        finish(dataUrl);
      } catch {
        finish(null);
      }
    };
    img.onerror = () => finish(null);
    img.src = objectUrl;
  });
}

function estimateDataUrlBytes(dataUrl: string): number {
  return Math.floor(dataUrl.length * 0.75);
}

function buildSingleBlock(a: WorkspaceComposerAttachment): string {
  if (a.error) return "";
  if (a.kind === "binary") {
    return binaryAttachmentPlaceholder(a.name, a.size);
  }
  const header =
    a.kind === "image"
      ? `[Attached image: ${a.name} (${formatAttachmentByteSize(a.size)})]`
      : `[Attached file: ${a.name} (${formatAttachmentByteSize(a.size)})]`;
  const body = a.payload.trimEnd();
  return `${header}\n${body}`;
}

export function buildOutboundMessageWithAttachment(
  trimmedText: string,
  attachment: WorkspaceComposerAttachment | null,
): string {
  if (!attachment) return trimmedText;
  return buildOutboundMessageWithAttachments(trimmedText, [attachment]);
}

/**
 * Packs all attachment blocks, then the user's text, mirroring a multi-attach send.
 */
export function buildOutboundMessageWithAttachments(
  trimmedText: string,
  attachments: WorkspaceComposerAttachment[],
): string {
  const usable = attachments.filter((a) => !a.error);
  const blocks: string[] = [];
  for (const a of usable) {
    const b = buildSingleBlock(a);
    if (b.trim().length) blocks.push(b);
  }
  if (trimmedText.length) {
    if (blocks.length) return `${blocks.join("\n\n")}\n\n${trimmedText}`;
    return trimmedText;
  }
  return blocks.join("\n\n");
}

export async function fileToWorkspaceAttachment(file: File): Promise<WorkspaceComposerAttachment | null> {
  const id = `hww-att-${Date.now()}-${Math.random().toString(36).slice(2, 9)}`;
  const name = file.name || "attachment";
  const kind = classifyAttachment(file);

  if (kind === "image") {
    if (file.size > MAX_WORKSPACE_ATTACHMENT_BYTES) {
      const compressed = await compressImageToDataUrl(file);
      if (compressed && estimateDataUrlBytes(compressed) <= MAX_WORKSPACE_ATTACHMENT_BYTES) {
        const sz = estimateDataUrlBytes(compressed);
        return { id, name, size: sz, kind: "image", payload: compressed };
      }
      return null;
    }
    const dataUrl = await readFileAsDataURL(file);
    if (estimateDataUrlBytes(dataUrl) > MAX_WORKSPACE_ATTACHMENT_BYTES) {
      const compressed = await compressImageToDataUrl(file);
      if (compressed && estimateDataUrlBytes(compressed) <= MAX_WORKSPACE_ATTACHMENT_BYTES) {
        const sz = estimateDataUrlBytes(compressed);
        return { id, name, size: sz, kind: "image", payload: compressed };
      }
      return null;
    }
    return { id, name, size: file.size, kind: "image", payload: dataUrl };
  }

  if (file.size > MAX_WORKSPACE_ATTACHMENT_BYTES) {
    return null;
  }
  if (kind === "text") {
    try {
      const t = await readFileAsText(file);
      return { id, name, size: file.size, kind: "text", payload: t };
    } catch {
      return {
        id,
        name,
        size: file.size,
        kind: "text",
        payload: "",
        error: "Could not read this file.",
      };
    }
  }
  return { id, name, size: file.size, kind: "binary", payload: "" };
}
