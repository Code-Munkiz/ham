/**
 * Workspace composer: images + documents + small text. Prefer `ham_chat_user_v2`
 * (uploads via `POST /api/chat/attachments`); v1 inlines `data_url` when used.
 *
 * Image previews use `blob:` URLs; revoke via `revokeWorkspaceComposerAttachmentPreviews`.
 */
export type WorkspaceComposerAttachment = {
  id: string;
  name: string;
  size: number;
  kind: "image" | "file" | "video";
  /** `blob:` URL for image preview or empty for opaque file uploads before send. */
  payload: string;
  /** Set after `POST /api/chat/attachments` — chat uses v2 refs, not local blobs. */
  serverId?: string;
  mime?: string;
  error?: string;
  /** Local upload lifecycle — omit or `"done"` after successful upload */
  uploadPhase?: "uploading" | "done" | "failed";
  /** Retained server-side retry path when `uploadPhase` is `"failed"` (not sent over the wire). */
  pendingSource?: File;
};

/** JPEG/PNG/WebP/GIF — server enforces the same ceiling. */
export const MAX_WORKSPACE_IMAGE_BYTES = 10 * 1024 * 1024;

/** PDF / Office / UTF-8 text — server enforces the larger ceiling. */
export const MAX_WORKSPACE_DOCUMENT_BYTES = 20 * 1024 * 1024;

/** @deprecated Prefer MAX_WORKSPACE_DOCUMENT_BYTES for new code. */
export const MAX_WORKSPACE_ATTACHMENT_BYTES = MAX_WORKSPACE_DOCUMENT_BYTES;

export const MAX_WORKSPACE_ATTACHMENT_COUNT = 5;

export const WORKSPACE_ATTACHMENT_ACCEPT = [
  "image/png",
  "image/jpeg",
  "image/jpg",
  "image/webp",
  "image/gif",
  "application/pdf",
  "application/msword",
  "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
  "text/csv",
  "application/vnd.ms-excel",
  "video/mp4",
  "video/quicktime",
  "video/webm",
  ".jpg",
  ".jpeg",
  ".png",
  ".gif",
  ".webp",
  ".pdf",
  ".txt",
  ".md",
  ".doc",
  ".docx",
  ".xlsx",
  ".csv",
  ".xls",
  ".mp4",
  ".mov",
  ".webm",
].join(",");

const IMG_EXT = new Set([".png", ".jpg", ".jpeg", ".webp", ".gif"]);

const MIME_IMAGE = /^image\/(png|jpe?g|webp|gif)$/i;

const UNSUPPORTED =
  "Use JPG, PNG, GIF, WebP, PDF, TXT, MD, DOC, DOCX, XLSX, CSV, XLS (stored; legacy .xls not extracted), MP4/MOV/WebM videos (stored; no transcript yet), or paste text.";

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

export function revokeWorkspaceComposerAttachmentPreviews(list: WorkspaceComposerAttachment[]): void {
  for (const a of list) {
    const p = a.payload;
    if (p.startsWith("blob:")) {
      try {
        URL.revokeObjectURL(p);
      } catch {
        /* ignore */
      }
    }
  }
}

function mimeForFile(file: File): string {
  const t = (file.type || "").trim().toLowerCase();
  if (t && t !== "application/octet-stream") return t;
  const ext = fileExtensionLower(file.name);
  if (ext === ".png") return "image/png";
  if (ext === ".jpg" || ext === ".jpeg") return "image/jpeg";
  if (ext === ".webp") return "image/webp";
  if (ext === ".gif") return "image/gif";
  if (ext === ".pdf") return "application/pdf";
  if (ext === ".txt") return "text/plain";
  if (ext === ".md" || ext === ".markdown") return "text/markdown";
  if (ext === ".doc") return "application/msword";
  if (ext === ".xls") return "application/vnd.ms-excel";
  if (ext === ".docx") return "application/vnd.openxmlformats-officedocument.wordprocessingml.document";
  if (ext === ".xlsx") return "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet";
  if (ext === ".csv") return "text/csv";
  if (ext === ".mp4") return "video/mp4";
  if (ext === ".mov") return "video/quicktime";
  if (ext === ".webm") return "video/webm";
  return "";
}

function isAllowedSpreadsheetFile(file: File): boolean {
  const ext = fileExtensionLower(file.name);
  const m = mimeForFile(file).toLowerCase();
  if (ext === ".xlsx" || m === "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet") {
    return true;
  }
  if (ext === ".csv" || m === "text/csv" || m === "application/csv") {
    return true;
  }
  return false;
}

function isAllowedVideoFile(file: File): boolean {
  const ext = fileExtensionLower(file.name);
  const m = mimeForFile(file).toLowerCase();
  if (ext === ".mp4" || m === "video/mp4") return true;
  if (ext === ".mov" || m === "video/quicktime") return true;
  if (ext === ".webm" || m === "video/webm") return true;
  return false;
}

function isAllowedTextFile(file: File): boolean {
  const ext = fileExtensionLower(file.name);
  const m = mimeForFile(file);
  if (ext === ".txt" || ext === ".md" || ext === ".markdown") return true;
  if (m === "text/plain" || m === "text/markdown") return true;
  return false;
}

function isAllowedBinaryOfficeOrPdf(file: File): boolean {
  const ext = fileExtensionLower(file.name);
  const m = mimeForFile(file).toLowerCase();
  if (isAllowedSpreadsheetFile(file)) return true;
  if (ext === ".pdf" || m === "application/pdf") return true;
  if (ext === ".doc" || m === "application/msword") return true;
  if (ext === ".xls" || m === "application/vnd.ms-excel") return true;
  if (
    ext === ".docx" ||
    m === "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
  ) {
    return true;
  }
  return false;
}

function isAllowedRasterImageFile(file: File): boolean {
  const ext = fileExtensionLower(file.name);
  const m = mimeForFile(file);
  if (MIME_IMAGE.test(m)) {
    if (ext && !IMG_EXT.has(ext)) {
      return false;
    }
    return true;
  }
  if (m.startsWith("image/") && !MIME_IMAGE.test(m)) {
    return false;
  }
  if (IMG_EXT.has(ext)) {
    return !m || m === "application/octet-stream" || MIME_IMAGE.test(m);
  }
  return false;
}

export async function fileToWorkspaceAttachment(
  file: File,
): Promise<WorkspaceComposerAttachment | null> {
  const id = `hww-att-${Date.now()}-${Math.random().toString(36).slice(2, 9)}`;
  const name = file.name || "attachment";

  if (isAllowedTextFile(file)) {
    if (file.size > MAX_WORKSPACE_DOCUMENT_BYTES) {
      return null;
    }
    return { id, name, size: file.size, kind: "file", payload: "" };
  }

  if (isAllowedBinaryOfficeOrPdf(file)) {
    if (file.size > MAX_WORKSPACE_DOCUMENT_BYTES) {
      return null;
    }
    return { id, name, size: file.size, kind: "file", payload: "" };
  }

  if (isAllowedVideoFile(file)) {
    if (file.size > MAX_WORKSPACE_DOCUMENT_BYTES) {
      return null;
    }
    return { id, name, size: file.size, kind: "video", payload: "" };
  }

  if (!isAllowedRasterImageFile(file)) {
    return {
      id,
      name,
      size: file.size,
      kind: "image",
      payload: "",
      error: UNSUPPORTED,
    };
  }

  if (file.size > MAX_WORKSPACE_IMAGE_BYTES) {
    return null;
  }

  if (typeof URL === "undefined" || !URL.createObjectURL) {
    return {
      id,
      name,
      size: file.size,
      kind: "image",
      payload: "",
      error: "File preview unavailable in this environment.",
    };
  }

  const payload = URL.createObjectURL(file);
  return {
    id,
    name,
    size: file.size,
    kind: "image",
    payload,
  };
}

export async function buildFileForServerUpload(
  original: File,
  _local: WorkspaceComposerAttachment,
): Promise<File> {
  void _local;
  return original;
}
