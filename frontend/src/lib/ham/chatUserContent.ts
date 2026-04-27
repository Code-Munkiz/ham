/**
 * HAM `ham_chat_user_v1` — must match `src/ham/chat_user_content.py` and
 * `buildHamChatUserPayloadV1` in the workspace composer.
 */
export const HAM_CHAT_USER_V1 = "ham_chat_user_v1" as const;

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

const RE_STRICT = /^data:(image\/(?:png|jpeg|webp));base64,/i;

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
  return m === "image/png" || m === "image/jpeg" || m === "image/jpg" || m === "image/webp";
}

export function buildHamChatUserPayloadV1(
  trimmedText: string,
  images: { name: string; mime: string; dataUrl: string; size: number }[],
): HamChatUserContentV1 {
  const out: HamChatUserImage[] = [];
  for (const im of images) {
    const mime = im.mime.toLowerCase() === "image/jpg" ? "image/jpeg" : (im.mime.toLowerCase() as string);
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

export function userTranscriptPreview(raw: string): string {
  const v = tryParseHamChatUserV1String(raw);
  if (!v) return raw.trim();
  const t = v.text?.trim() ?? "";
  if (t) return t;
  if (v.images?.length) return `[${v.images.length} screenshot${v.images.length === 1 ? "" : "s"}]`;
  return "";
}
