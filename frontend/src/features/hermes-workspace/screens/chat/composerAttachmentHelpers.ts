/**
 * Workspace composer: PNG / JPEG / WebP screenshots only. Sent as `ham_chat_user_v1` JSON
 * to `/api/chat/stream` (see `hamChatUserPayload.ts` + `src/ham/chat_user_content.py`).
 */
export type WorkspaceComposerAttachment = {
  id: string;
  name: string;
  size: number;
  kind: "image" | "file";
  /** data: URL or `blob:` URL for preview. */
  payload: string;
  /** Set after `POST /api/chat/attachments` — chat uses v2, not data URLs in Firestore. */
  serverId?: string;
  /** From upload response (required for v2). */
  mime?: string;
  /** Shown in preview when the file is rejected or unreadable. */
  error?: string;
};

export const MAX_WORKSPACE_ATTACHMENT_BYTES = 500 * 1024;

export const MAX_WORKSPACE_ATTACHMENT_COUNT = 8;

export const WORKSPACE_ATTACHMENT_ACCEPT =
  "image/png,image/jpeg,image/jpg,image/webp,text/plain,text/markdown,.txt,.md";

const EXT_OK = new Set([".png", ".jpg", ".jpeg", ".webp"]);

const MAX_IMAGE_DIMENSION = 1280;
const TARGET_JPEG_QUALITY = 0.75;

const UNSUPPORTED = "Use PNG, JPEG, WebP, plain text, or markdown (.txt, .md).";

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

function mimeForFile(file: File): string {
  const t = (file.type || "").trim().toLowerCase();
  if (t) return t;
  const ext = fileExtensionLower(file.name);
  if (ext === ".png") return "image/png";
  if (ext === ".jpg" || ext === ".jpeg") return "image/jpeg";
  if (ext === ".webp") return "image/webp";
  return "";
}

function isAllowedTextFile(file: File): boolean {
  const ext = fileExtensionLower(file.name);
  const m = mimeForFile(file);
  if (m === "text/plain" || m === "text/markdown") return true;
  if (ext === ".txt" || ext === ".md" || ext === ".markdown") return true;
  return false;
}

/** Returns true if this file is one of the allowed screenshot types. */
function isAllowedScreenshotFile(file: File): boolean {
  const ext = fileExtensionLower(file.name);
  const m = mimeForFile(file);
  if (m === "image/png" || m === "image/jpeg" || m === "image/jpg" || m === "image/webp") {
    if (ext && !EXT_OK.has(ext)) {
      return false;
    }
    return true;
  }
  if (m.startsWith("image/") && !EXT_OK.has(ext) && !m.match(/^image\/(png|jpe?g|webp)$/i)) {
    return false;
  }
  // Browsers often use application/octet-stream for picked files; trust .png/.jpg/.webp extension.
  if (EXT_OK.has(ext)) {
    return (
      !m ||
      m === "application/octet-stream" ||
      /^image\/(png|jpe?g|webp)$/i.test(m)
    );
  }
  return false;
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
 * Resizes and compresses to stay under the HAM 500KB inline cap (best-effort).
 * Output is PNG for PNG sources, else JPEG.
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
        const wantPng = mimeForFile(file) === "image/png";
        const mime = wantPng ? "image/png" : "image/jpeg";
        let quality = TARGET_JPEG_QUALITY;
        let dataUrl = canvas.toDataURL(mime, wantPng ? undefined : quality);
        if (!wantPng) {
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

/**
 * Read an allowed screenshot; returns a chip with error text if the file is not supported.
 */
export async function fileToWorkspaceAttachment(
  file: File,
): Promise<WorkspaceComposerAttachment | null> {
  const id = `hww-att-${Date.now()}-${Math.random().toString(36).slice(2, 9)}`;
  const name = file.name || "attachment";
  if (isAllowedTextFile(file)) {
    if (file.size > MAX_WORKSPACE_ATTACHMENT_BYTES) {
      return null;
    }
    return { id, name, size: file.size, kind: "file", payload: "" };
  }
  if (!isAllowedScreenshotFile(file)) {
    return {
      id,
      name,
      size: file.size,
      kind: "image",
      payload: "",
      error: UNSUPPORTED,
    };
  }
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

/**
 * Reconstruct a `File` for `POST /api/chat/attachments` from the local preview
 * (uses the original `File` when size matches; otherwise the compressed data URL as a `File`).
 */
export async function buildFileForServerUpload(
  original: File,
  local: WorkspaceComposerAttachment,
): Promise<File> {
  if (local.kind === "file") return original;
  if (local.size === original.size) return original;
  const r = await fetch(local.payload);
  const blob = await r.blob();
  return new File([blob], local.name, { type: blob.type || "image/png" });
}
