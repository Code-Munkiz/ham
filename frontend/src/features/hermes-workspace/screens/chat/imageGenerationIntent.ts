/**
 * Deterministic NL routing for workspace creative image flows (Phase 2G.2 text-to-image, 2G.3 reference).
 * Avoids accidental generation when the user wants image understanding / OCR.
 */

const ANALYSIS_BLOCKED = [
  /\bwhat(?:'| i)s\s+in\s+(?:this|the)\s+(?:image|picture|photo|screenshot)\b/i,
  /\bdescribe\s+(?:this|the)\s+(?:image|picture|photo|screenshot|ui)\b/i,
  /\bdescribe\s+the\s+attached\s+(?:image|picture|photo|screenshot)\b/i,
  /\banalyze\s+(?:the\s+|this\s+)?(?:screenshot|ui|interface|mockup)\b/i,
  /\banalyze\s+this\b/i,
  /\b(?:look|see)\s+at\s+(?:this|the)\s+(?:image|picture|photo|screenshot)\b/i,
  /\bsummarize\s+(?:this|the)\s+(?:image|picture|photo|screenshot)\b/i,
  /\b(?:read|parse)\s+this\s+(?:screenshot|image|picture)\b/i,
  /\bcan\s+you\s+read\s+this\b/i,
  /\b(?:extract|grab)\s+text\s+from\b/i,
  /\bocr\b/i,
  /\b(?:this|the)\s+(?:attached\s+)?(?:image|picture|screenshot)\s+shows\b/i,
  /\b(?:tell\s+me|explain)\s+what\b.+?\b(?:in|about)\s+(?:this|that|the)\s+(?:image|picture|screenshot)\b/i,
  /\bdraw\s+.+\bconclusions?\b/i,
];

/**
 * Strip safe leading wake-words / polite prefixes so anchors like `^show me` still match.
 * Does not remove words from the middle of the prompt.
 */
export function normalizeImageIntentProbe(raw: string): string {
  let s = raw.replace(/\s+/g, " ").trim();
  const steps: RegExp[] = [
    /^(?:hey\s*,?\s*)ham\s*[,:\s]+\s*/i,
    /^ham\s*[,:\s]+\s*/i,
    /^ham\s+/i,
    /^please\s+/i,
    /^could you\s+/i,
    /^can you\s+/i,
    /^would you\s+/i,
    /^i want you to\s+/i,
    /^i need you to\s+/i,
  ];
  for (let n = 0; n < 6; n++) {
    const before = s;
    for (const rx of steps) {
      s = s.replace(rx, "").trim();
    }
    if (s === before) break;
  }
  return s;
}

function analysisBlockedForAny(s: string): boolean {
  return ANALYSIS_BLOCKED.some((rx) => rx.test(s));
}

/** After stripping a verb phrase, refuse if remainder looks like deictic analysis-only. */
function remainderLooksReferential(prompt: string): boolean {
  const t = prompt.trim().toLowerCase();
  if (!t) return true;
  if (/\b(this|that|these|those|attached|uploaded)\s+(image|screenshot|picture|file)\b/.test(t)) return true;
  if (/\b(from|above|below)\s+the\s+(image|screenshot|picture)\b/.test(t)) return true;
  return false;
}

function normalizePrompt(prompt: string): string {
  return prompt.replace(/\s+/g, " ").trim().replace(/^["'"\u201c]+|["'"\u201d]+$/g, "").trim();
}

function drawRemainderLooksVisualArtistic(raw: string): boolean {
  const t = raw.trim().toLowerCase();
  if (/\sof\s+[a-z0-9_-]/i.test(t)) return true;
  const tokens =
    /\b(icon|icons|logo|logos|banner|banners|diagram|diagrams|poster|posters|mascot|character|characters|monster|fantasy|cyber|futuristic|neon|minimal|architecture|planet|universe|galaxy|creature|wizard|dragon|sprite|splash screen|splash|thumbnail|dashboard|landing page|landing|sketch|concept art)\b/;
  return tokens.test(t);
}

/** True when "draw …" is clearly a visual request, not analysis (e.g. draw conclusions). */
function drawRemainderAcceptableForGeneration(raw: string): boolean {
  const t = raw.trim().toLowerCase();
  if (/\bconclusions?\b/.test(t)) return false;
  if (drawRemainderLooksVisualArtistic(raw)) return true;
  // Scenes, animals, people, food, etc. — avoid wiring "draw" to chat/ASCII fallbacks for obvious subjects.
  const sceneish =
    /\b(monkey|banana|cat|dog|bird|fish|horse|lion|tiger|bear|robot|car|house|landscape|portrait|sunset|forest|beach|city|food|fruit|plant|tree|flower|person|man|woman|child|face|hand|mountain|ocean|space|castle|dragon)\b/i;
  if (sceneish.test(t)) return true;
  return t.length >= 8;
}

type Matcher = {
  re: RegExp;
  promptGroup: number;
  /** Optional gate on the extracted capture group (before whitespace normalization). */
  extra?: (rawCapture: string) => boolean;
};

const TEXT_TO_IMAGE_MATCHERS: Matcher[] = [
  /** Adjectives allowed between verb/article and noun: "generate a realistic photo of …", "make a realistic image of …". */
  {
    re: /^\s*(?:please\s+)?(?:create|generate|make)\s+(?:a|an|the\s+)?(?:[\w'-]+\s+)*(?:image|picture|photo|logo|banner|graphic|icon|illustration|poster|diagram)\s+of\s*(.*)$/is,
    promptGroup: 1,
  },
  {
    re: /^\s*(?:please\s+)?(?:show|give)\s+me\s+(?:a|an|the\s+)?(?:[\w'-]+\s+)*(?:picture|image|photo|logo|banner|graphic|icon|illustration|poster|diagram)\s+of\s*(.*)$/is,
    promptGroup: 1,
  },
  {
    re: /^\s*(?:please\s+)?draw\s+([\s\S]+)$/is,
    promptGroup: 1,
    extra: (remainder: string) => drawRemainderAcceptableForGeneration(remainder),
  },
  {
    re: /^\s*(?:please\s+)?generate\s+(?:some\s+)?art\s+of\s+(.*)$/is,
    promptGroup: 1,
  },
  {
    re: /^\s*(?:please\s+)?make\s+a\s+banner\b\s*(.*)$/is,
    promptGroup: 1,
  },
];

/**
 * Prompt-level triggers for reference / edit-style generations when at least one image is attached.
 * Ambiguous conversational turns intentionally return null → normal chat / vision.
 */
const IMAGE_TO_IMAGE_TRIGGERS: RegExp[] = [
  /\b(?:edit|re-?draw|restyle|remix|modernize)\s+(?:this|it|that|my|the\s+(?:attached\s+)?(?:screenshot|image|picture|photo))\b/i,
  /\bmake\s+(?:this|it)\s+(?:more\b|modern|minimal|dramatic)\b/i,
  /\bmake\s+(?:this|it)\s+(?:into\b|(?:look\s+like))\b/i,
  /\bmake\s+(?:the\s+)?(?:attached\s+)?(?:image|picture|photo|screenshot)\s+/i,
  /\bturn\s+(?:this|it)\s+into\b/i,
  /\bcreate\s+(?:a\s+)?variation\s+of\s+(?:this|it|the\s+(?:attached\s+)?(?:image|picture|photo))\b/i,
  /\buse\s+(?:this|it)\s+as\s+(?:a\s+)?reference\b/i,
  /\bchange\s+(?:the\s+)?(?:background|style)\b(?:\s+of\s+(?:this|it|that|my))?\s*(?:to\b|\s+)/i,
  /\b(?:re)?design\s+(?:this|it|the\s+(?:attached\s+)?(?:ui|screenshot))\b/i,
  /\b(?:replace|swap)\s+(?:the\s+)?(?:background|sky)\b/i,
];

export type WorkspaceCreativeImageIntent =
  /** New image from text only — no uploaded reference blob. */
  | { kind: "text_to_image"; prompt: string }
  /** Use attached image bytes as model input plus the instruction. */
  | { kind: "image_to_image"; prompt: string };

function parseTextToImagePrompt(raw: string): string | null {
  const trimmed = raw.trim();
  if (trimmed.length < 8) return null;

  const logoStandalone = trimmed.match(/^\s*(?:please\s+)?(?:generate|create|make)\s+(?:an?\s+)?logo\s+/i);
  if (logoStandalone) {
    const prompt = normalizePrompt(trimmed.replace(/^\s*(?:please\s+)?(?:generate|create|make)\s+(?:an?\s+)?logo\s+/i, ""));
    if (prompt.length >= 2 && !remainderLooksReferential(prompt)) {
      return prompt.slice(0, 8000);
    }
  }

  for (const m of TEXT_TO_IMAGE_MATCHERS) {
    const exec = m.re.exec(trimmed);
    if (!exec) continue;
    const rawPrompt = (exec[m.promptGroup] ?? "").trim();
    if (m.extra && !m.extra(rawPrompt)) continue;
    const prompt = normalizePrompt(rawPrompt);
    if (prompt.length < 2) continue;
    if (remainderLooksReferential(prompt)) continue;
    return prompt.slice(0, 8000);
  }

  return null;
}

/** NL classification for routed creative-media actions (generation vs fall through to chat/vision). */
export function parseWorkspaceCreativeImageIntent(
  raw: string,
  ctx: { hasImageAttachment: boolean },
): WorkspaceCreativeImageIntent | null {
  const trimmed = raw.trim();
  if (trimmed.length < 2) return null;

  const probe = normalizeImageIntentProbe(trimmed);

  if (analysisBlockedForAny(trimmed) || analysisBlockedForAny(probe)) return null;

  if (ctx.hasImageAttachment) {
    if (IMAGE_TO_IMAGE_TRIGGERS.some((rx) => rx.test(probe) || rx.test(trimmed))) {
      return { kind: "image_to_image", prompt: trimmed.slice(0, 8000) };
    }
    // Composer may still have unrelated attachments; NL text-to-image must not be suppressed.
  }

  const p = parseTextToImagePrompt(probe);
  return p ? { kind: "text_to_image", prompt: p } : null;
}

/**
 * Conservative text-only image generation cueing (backward compatible helper).
 */
export function parseWorkspaceImageGenerationIntent(raw: string): string | null {
  const parsed = parseWorkspaceCreativeImageIntent(raw, { hasImageAttachment: false });
  return parsed?.kind === "text_to_image" ? parsed.prompt : null;
}
