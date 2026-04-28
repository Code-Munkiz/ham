/**
 * GoHAM research start strategy: construct a safe search-results URL without
 * typing into a search box or submitting a form.
 */

import { redactUrlForTrail } from "./extractGohamUrl";
import { shouldUseResearchLoop } from "./gohamResearchLoop";

const SEARCH_PROVIDER_URL = "https://duckduckgo.com/";
const MAX_SEARCH_QUERY_CHARS = 160;

const QUERY_STOPWORDS = new Set([
  "goham",
  "find",
  "finding",
  "research",
  "information",
  "info",
  "about",
  "look",
  "lookup",
  "learn",
  "up",
  "tell",
  "whether",
  "what",
  "start",
  "at",
  "the",
  "and",
  "for",
  "with",
  "from",
  "page",
  "pages",
  "shown",
  "show",
  "has",
  "have",
  "does",
  "is",
  "are",
  "it",
  "me",
  "whats",
  "what's",
  "on",
]);

const DOMAIN_STOPWORDS = new Set(["www", "com", "org", "net", "ai", "io", "app", "dev"]);

function splitQueryTokens(text: string): string[] {
  return text
    .split(/[^\p{L}\p{N}._-]+/u)
    .map((w) => w.trim().replace(/^[._-]+|[._-]+$/gu, ""))
    .filter((w) => w.length > 1);
}

function uniquePush(out: string[], token: string) {
  const t = token.trim();
  if (!t) return;
  const key = t.toLowerCase();
  if (!out.some((x) => x.toLowerCase() === key)) out.push(t);
}

function domainTokens(url: string | null): string[] {
  if (!url) return [];
  try {
    const u = new URL(url);
    return u.hostname
      .toLowerCase()
      .split(".")
      .filter((part) => part.length > 1 && !DOMAIN_STOPWORDS.has(part));
  } catch {
    return [];
  }
}

function stripUrls(text: string): string {
  return text.replace(/\bhttps?:\/\/[^\s<>"'`)}\]]+/giu, " ");
}

export type GohamSearchStart = {
  kind: "safe_search";
  provider: "duckduckgo";
  query: string;
  url: string;
  displayQuery: string;
};

export function buildGohamSearchQuery(taskText: string, directUrl: string | null): string {
  const tokens: string[] = [];
  for (const part of domainTokens(directUrl)) uniquePush(tokens, part);

  const withoutUrls = stripUrls(taskText)
    .replace(/\bgo\s*ham\b/giu, " ")
    .replace(/\bstart\s+at\b/giu, " ")
    .replace(/\bfind\s+(information|info)\s+about\b/giu, " ")
    .replace(/\btell\s+me\s+(whether|what|about)?\b/giu, " ")
    .replace(/\blook\s+up\b/giu, " ")
    .replace(/\bwhat'?s\s+on\b/giu, " ");

  for (const raw of splitQueryTokens(withoutUrls)) {
    const lower = raw.toLowerCase();
    if (QUERY_STOPWORDS.has(lower)) continue;
    uniquePush(tokens, raw);
  }

  const query = tokens.join(" ").replace(/\s+/gu, " ").trim();
  return query.length > MAX_SEARCH_QUERY_CHARS ? query.slice(0, MAX_SEARCH_QUERY_CHARS).trim() : query;
}

export function buildSafeSearchUrl(query: string): string | null {
  const q = query.trim();
  if (!q) return null;
  try {
    const u = new URL(SEARCH_PROVIDER_URL);
    u.searchParams.set("q", q);
    if (u.protocol !== "https:" && u.protocol !== "http:") return null;
    return u.toString();
  } catch {
    return null;
  }
}

export function shouldStartResearchFromSearch(taskText: string, directUrl: string | null): boolean {
  if (!shouldUseResearchLoop(taskText)) return false;
  const query = buildGohamSearchQuery(taskText, directUrl);
  if (!query) return false;
  if (!directUrl) return true;

  const queryTokens = splitQueryTokens(query).map((t) => t.toLowerCase());
  const hostTokens = new Set(domainTokens(directUrl));
  const targetTokens = queryTokens.filter((t) => !hostTokens.has(t) && !QUERY_STOPWORDS.has(t));
  const hasVersionLike = targetTokens.some((t) => /\d/.test(t) && /[a-z]/i.test(t));
  return hasVersionLike || targetTokens.length >= 3;
}

export function planGohamResearchStart(taskText: string, directUrl: string | null): {
  url: string | null;
  search: GohamSearchStart | null;
} {
  if (!shouldStartResearchFromSearch(taskText, directUrl)) {
    return { url: directUrl, search: null };
  }

  const query = buildGohamSearchQuery(taskText, directUrl);
  const searchUrl = buildSafeSearchUrl(query);
  if (!searchUrl) return { url: directUrl, search: null };

  return {
    url: searchUrl,
    search: {
      kind: "safe_search",
      provider: "duckduckgo",
      query,
      displayQuery: query.length > 84 ? `${query.slice(0, 84)}...` : query,
      url: searchUrl,
    },
  };
}

export function redactSearchUrlForTrail(url: string): string {
  return redactUrlForTrail(url);
}
