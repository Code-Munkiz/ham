/**
 * Conservative, deterministic NL routing for Phase 2G.2 workspace image generation.
 * Avoids accidental generation when the user is requesting image understanding / OCR.
 */

const ANALYSIS_BLOCKED = [
  /\bwhat(?:'| i)s\s+in\s+(?:this|the)\s+(?:image|picture|photo|screenshot)\b/i,
  /\bdescribe\s+(?:this|the)\s+(?:image|picture|photo|screenshot|ui)\b/i,
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

/** After stripping a verb phrase, refuse if remainder looks like deictic analysis. */
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

type Matcher = {
  re: RegExp;
  promptGroup: number;
  /** Optional gate on the extracted capture group (before whitespace normalization). */
  extra?: (rawCapture: string) => boolean;
};

const GENERATION_MATCHERS: Matcher[] = [
  {
    re: /^\s*(?:please\s+)?(?:create|generate|make)\s+(?:an?\s+)?(image|picture|photo|logo|banner|graphic|icon|illustration|poster|diagram)\s+of\s*(.*)$/is,
    promptGroup: 2,
  },
  {
    re: /^\s*(?:please\s+)?(?:show|give)\s+me\s+(?:an?\s+)?(picture|image|photo|logo|banner|graphic|icon|illustration)\s+of\s*(.*)$/is,
    promptGroup: 2,
  },
  {
    re: /^\s*(?:please\s+)?draw\s+([\s\S]+)$/is,
    promptGroup: 1,
    extra: (remainder: string) => drawRemainderLooksVisualArtistic(remainder),
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
 * Returns a cleaned prompt when the utterance clearly requests creation of new imagery,
 * otherwise `null` (fall back to normal chat).
 */
export function parseWorkspaceImageGenerationIntent(raw: string): string | null {
  const trimmed = raw.trim();
  if (trimmed.length < 8) return null;

  for (const rx of ANALYSIS_BLOCKED) {
    if (rx.test(trimmed)) return null;
  }

  const logoStandalone = trimmed.match(/^\s*(?:please\s+)?(?:generate|create|make)\s+(?:an?\s+)?logo\s+/i);
  if (logoStandalone) {
    const prompt = normalizePrompt(trimmed.replace(/^\s*(?:please\s+)?(?:generate|create|make)\s+(?:an?\s+)?logo\s+/i, ""));
    if (prompt.length >= 2 && !remainderLooksReferential(prompt)) {
      return prompt.slice(0, 8000);
    }
  }

  for (const m of GENERATION_MATCHERS) {
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
