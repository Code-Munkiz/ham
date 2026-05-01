/**
 * HAM `ham_chat_user_v1` — must match `src/ham/chat_user_content.py` and
 * `buildHamChatUserPayloadV1` in the workspace composer.
 */
export const HAM_CHAT_USER_V1 = "ham_chat_user_v1" as const;
export const HAM_CHAT_USER_V2 = "ham_chat_user_v2" as const;

export type HamChatUserImage = {
  name: string;
  mime: "image/png" | "image/jpeg" | "image/webp";
  data_url: string;
};

export type HamChatUserContentV1 = {
  h: typeof HAM_CHAT_USER_V1;
  text: string;
  images: HamChatUserImage[];
};

export type HamChatUserAttachmentRef = {
  id: string;
  name: string;
  mime: string;
  kind: "image" | "file" | "video";
};

export type HamChatUserContentV2 = {
  h: typeof HAM_CHAT_USER_V2;
  text: string;
  attachments: HamChatUserAttachmentRef[];
};

/** Browsers may emit `image/jpg` or `image/jpeg` for JPEG; accept both. */
const RE_STRICT = /^data:(image\/(?:png|jpe?g|webp));base64,/i;

export function tryParseHamChatUserV2String(raw: string): HamChatUserContentV2 | null {
  const t = raw.trim();
  if (!t.startsWith("{")) return null;
  try {
    const o = JSON.parse(t) as unknown;
    if (!o || typeof o !== "object" || (o as HamChatUserContentV2).h !== HAM_CHAT_USER_V2) return null;
    return o as HamChatUserContentV2;
  } catch {
    return null;
  }
}

export function tryParseHamChatUserV1String(raw: string): HamChatUserContentV1 | null {
  const t = raw.trim();
  if (!t.startsWith("{")) return null;
  try {
    const o = JSON.parse(t) as unknown;
    if (!o || typeof o !== "object" || (o as HamChatUserContentV1).h !== HAM_CHAT_USER_V1) return null;
    return o as HamChatUserContentV1;
  } catch {
    return null;
  }
}

function isAllowedScreenshotDataUrl(dataUrl: string, declaredMime: string): boolean {
  if (!RE_STRICT.test(dataUrl.trim())) return false;
  const m = declaredMime.toLowerCase();
  const d = m === "image/jpg" ? "image/jpeg" : m;
  return d === "image/png" || d === "image/jpeg" || d === "image/webp";
}

export function buildHamChatUserPayloadV1(
  trimmedText: string,
  images: { name: string; mime: string; dataUrl: string; size: number }[],
): HamChatUserContentV1 {
  const out: HamChatUserImage[] = [];
  for (const im of images) {
    const raw = im.mime.toLowerCase();
    const mime = raw === "image/jpg" || raw === "image/jpeg" ? "image/jpeg" : raw;
    if (mime !== "image/png" && mime !== "image/jpeg" && mime !== "image/webp") {
      continue;
    }
    if (!isAllowedScreenshotDataUrl(im.dataUrl, mime)) continue;
    out.push({
      name: im.name,
      mime: mime as HamChatUserImage["mime"],
      data_url: im.dataUrl,
    });
  }
  return { h: HAM_CHAT_USER_V1, text: trimmedText, images: out };
}

export function buildHamChatUserPayloadV2(
  trimmedText: string,
  attachments: HamChatUserAttachmentRef[],
): HamChatUserContentV2 {
  return { h: HAM_CHAT_USER_V2, text: trimmedText, attachments };
}

export function userTranscriptPreview(raw: string): string {
  const v2 = tryParseHamChatUserV2String(raw);
  if (v2) {
    const t = v2.text?.trim() ?? "";
    if (t) return t;
    const n = v2.attachments?.length ?? 0;
    if (n) return `[${n} attachment${n === 1 ? "" : "s"}]`;
    return "";
  }
  const v = tryParseHamChatUserV1String(raw);
  if (!v) return raw.trim();
  const t = v.text?.trim() ?? "";
  if (t) return t;
  if (v.images?.length) return `[${v.images.length} screenshot${v.images.length === 1 ? "" : "s"}]`;
  return "";
}
