/**
 * Conversational coding-intent classifier (frontend, pure).
 *
 * Used by `WorkspaceChatScreen.send()` to decide whether to fire
 * `previewCodingConductor` as a background side-effect when the user sends a
 * normal chat message. The server-side classifier
 * (`src/ham/coding_router/classify.py::classify_task`) is the source of
 * truth — this client gate just avoids unnecessary calls for clearly
 * conversational prompts (greetings, "what is X", "tell me about Y").
 *
 * Rules of thumb:
 * - Conservative on the negative side (always keep "explain", "what is",
 *   "tell me about", greetings, brainstorms out).
 * - Require BOTH a coding/repo verb AND a coding/repo noun to fire.
 *   This avoids false positives like "build trust" or "create context"
 *   while still catching "Refactor the persistence layer" (refactor + layer).
 * - Builder-style prompts ("build me a game/app/site/dashboard") are excluded
 *   so they can route to the chat-native Builder Happy Path instead.
 *
 * NOTE: this classifier never decides routing or execution. It only
 * gates a preview HTTP call. The user must still approve any launch in
 * the CodingPlanCard / ManagedBuildApprovalPanel.
 */

const MIN_LEN = 3;
const MAX_LEN = 4_000;

// Leading verbs that signal an explanation/conceptual prompt. These take
// precedence: a prompt that starts with one of these is never a coding intent
// regardless of what nouns follow.
const NEGATIVE_LEAD =
  /^\s*(explain|describe|define|compare|summari[sz]e|summary of|what (is|are|does|do|was|were|happens)|how (does|do|did|would|should|can|could)|why (is|are|does|do|did|would)|walk me through|tell me about|what's the difference|where (is|are|does)|when (do|does|did|should))\b/i;

// Pure conversational / greeting prompts.
const GREETING_ONLY =
  /^\s*(hi|hello|hey|hiya|yo|sup|thanks|thank you|thx|ty|good (morning|afternoon|evening|night)|what's up|wassup|how are you|how's it going|nice to meet you)\s*[!.?]*\s*$/i;

// Brainstorm / strategy / general discussion verbs (negative).
const BRAINSTORM_LEAD =
  /^\s*(brainstorm|let's discuss|let's talk|discuss|chat about|think about|reflect on|consider|imagine|envision)\b/i;

// Coding/repo verbs.
const POSITIVE_VERBS =
  /\b(build|create|make|implement|add|generate|scaffold|bootstrap|fix|debug|patch|resolve|repair|refactor|rename|restructure|reorganize|extract|migrate|sweep|modernize|cleanup|clean[\s-]up|audit|review|inspect|analy[sz]e|update|edit|modify|change|tweak|adjust|polish|tidy|write|deploy|ship|release|push|commit|snapshot|stage|open|file|submit|format|wire|hook up|set up|setup)\b/i;

// Coding/repo nouns. Includes file/build/scm artefacts and common product
// surfaces ("page", "endpoint", "component"). The list is intentionally broad
// so the backend classifier remains the final word on routing.
const POSITIVE_NOUNS =
  /\b(app|application|game|component|endpoint|route|api|feature|page|screen|service|module|script|tool|cli|website|site|bot|integration|workflow|pipeline|bug|issue|error|crash|regression|failure|test|tests|spec|fixture|repo|repository|code|codebase|file|files|class|method|function|hook|handler|layer|system|architecture|persistence|database|db|backend|frontend|stack|infra|infrastructure|pr|prs|pull request|merge request|branch|main|patch|commit|snapshot|comment|comments|docstring|docstrings|jsdoc|documentation|readme|docs|typo|typos|spelling|prettier|black|ruff|migration|seeder|config|env|secret|deploy|deployment|release|store|firestore|cache|queue|table|index|cluster|bucket)\b/i;

// Workspace builder prompts (new app/site/game/dashboard/tracker) should
// route to builder happy-path, not conversational coding-plan preview.
const BUILDER_PROMPT =
  /\b(build|create|make|generate|scaffold|turn)\b.{0,80}\b(app|application|website|site|game|dashboard|landing page|tracker|portal|saas)\b/i;

/** Iterating the hosted Builder app UX (distinct from repo / Hermes codebase edits). */
const WORKBENCH_HOSTED_APP_SURFACE =
  /\b(buttons?|digits?|numbers?|keyboard|controls?|calculator|spacing|equation|formula|tape|typing|styled|layouts?|padding|margins|apps?|preview|current\s+app|them|those|these|outline|border|yellow|readable|readability)\b/i;
const WORKBENCH_HOSTED_APP_VERB_OR_COLOR =
  /\b(make|change|update|adjust|improve|tweak|larger|smaller|bigger|better|preserve|yeah|nice job|looks great|keep\s+working|deep|again|give|have|blue|green|rounded|tailwind|yellow|outline|border)\b/i;
const REPO_CODING_HARD_SIGNAL =
  /\b(pull request|open a pr\b|@\w+\/\w+|jest|vitest|cypress|ruff\b|flake8|migrate the schema|postgresql|sequelize|prisma|opentelemetry|graphql|openapi|kubernetes|dockerfile\b|pnpm-lock|Cargo\.toml)\b/i;

/** True when firing `previewCodingConductor` side-by-side chat would distract from Builder iteration. */
export function looksLikeWorkbenchHostedAppIteration(rawText: string | null | undefined): boolean {
  const text = String(rawText || "").trim();
  if (!text) return false;
  if (REPO_CODING_HARD_SIGNAL.test(text) && !WORKBENCH_HOSTED_APP_SURFACE.test(text)) {
    return false;
  }
  return WORKBENCH_HOSTED_APP_SURFACE.test(text) && WORKBENCH_HOSTED_APP_VERB_OR_COLOR.test(text);
}

export interface CodingIntentDetail {
  matches: boolean;
  reason:
    | "empty"
    | "too_short"
    | "too_long"
    | "greeting"
    | "negative_lead"
    | "brainstorm_lead"
    | "no_verb"
    | "no_noun"
    | "match";
}

/**
 * Inspect a user prompt and return a verbose decision. Use this for tests
 * and debug logging; production callers should prefer `isLikelyCodingIntent`.
 */
export function inspectCodingIntent(rawText: string | null | undefined): CodingIntentDetail {
  if (rawText === null || rawText === undefined) return { matches: false, reason: "empty" };
  const text = String(rawText).trim();
  if (!text) return { matches: false, reason: "empty" };
  if (text.length > MAX_LEN) return { matches: false, reason: "too_long" };
  // Order matters: greeting > negative-lead > brainstorm-lead > too-short > verb/noun.
  // Conversational short-circuits ("hi", "what is", "brainstorm…") win before any
  // length-based or surface filtering — that matches user-perceived intent.
  if (GREETING_ONLY.test(text)) return { matches: false, reason: "greeting" };
  if (NEGATIVE_LEAD.test(text)) return { matches: false, reason: "negative_lead" };
  if (BRAINSTORM_LEAD.test(text)) return { matches: false, reason: "brainstorm_lead" };
  if (text.length < MIN_LEN) return { matches: false, reason: "too_short" };
  if (!POSITIVE_VERBS.test(text)) return { matches: false, reason: "no_verb" };
  if (!POSITIVE_NOUNS.test(text)) return { matches: false, reason: "no_noun" };
  return { matches: true, reason: "match" };
}

/**
 * Return `true` when the message looks like a coding / build / repo task that
 * warrants a server-side conductor preview call.
 */
export function isLikelyCodingIntent(rawText: string | null | undefined): boolean {
  const text = String(rawText || "").trim();
  if (looksLikeWorkbenchHostedAppIteration(text)) return false;
  if (BUILDER_PROMPT.test(text)) return false;
  return inspectCodingIntent(rawText).matches;
}
