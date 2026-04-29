/**
 * UI-only human labels for Hermes Workspace inspector and file tree (no path/API changes).
 */

/** Last segment slug → display label for common Hermes bundled skills */
const SKILL_SLUG_LABELS: Record<string, string> = {
  "apple-notes": "Apple Notes",
  "apple-reminders": "Apple Reminders",
  findmy: "Find My",
  imessage: "iMessage",
  "claude-code": "Claude Code",
  codex: "Codex",
  "hermes-agent": "Hermes Agent",
  opencode: "OpenCode",
};

const DISPLAY_TOKEN_REPLACEMENTS: Array<{ re: RegExp; to: string }> = [
  { re: /\bimessage\b/gi, to: "iMessage" },
  { re: /\bopencode\b/gi, to: "OpenCode" },
  { re: /\bcodex\b/gi, to: "Codex" },
  { re: /\bascii\b/gi, to: "ASCII" },
  { re: /\bmcp\b/gi, to: "MCP" },
  { re: /\bapi\b/gi, to: "API" },
  { re: /\bcli\b/gi, to: "CLI" },
  { re: /\bpr\b/gi, to: "PR" },
  { re: /\bclaude code\b/gi, to: "Claude Code" },
  { re: /\bhermes agent\b/gi, to: "Hermes Agent" },
];

function titleCaseKebabSegment(segment: string): string {
  return segment
    .split(/[-_]+/)
    .filter(Boolean)
    .map((w) => w.charAt(0).toUpperCase() + w.slice(1).toLowerCase())
    .join(" ");
}

function looksLikeRawCatalogToken(s: string): boolean {
  const t = s.trim();
  if (!t) return true;
  if (t.startsWith("bundled.") && t.includes(".")) return true;
  if (/^[a-z0-9]+(?:[.-][a-z0-9]+)+$/i.test(t) && t === t.toLowerCase()) return true;
  return false;
}

/**
 * Human-readable primary line for a Hermes static catalog row.
 * Prefers API `display_name` when it is clearly not a duplicate of the raw id.
 */
export function primaryHermesCatalogLabel(entry: { catalog_id: string; display_name?: string }): string {
  const id = entry.catalog_id?.trim() ?? "";
  const fromId = humanizeHermesCatalogId(id);
  const dn = entry.display_name?.trim() ?? "";
  if (!dn || dn === id) return fromId;
  if (dn.toLowerCase() === id.toLowerCase()) return fromId;
  if (looksLikeRawCatalogToken(dn)) return fromId;
  return applyDisplayNameTokens(dn);
}

export function humanizeHermesCatalogId(catalogId: string): string {
  const id = catalogId.trim();
  if (!id) return "";
  let rest = id.startsWith("bundled.") ? id.slice("bundled.".length) : id;
  const parts = rest.split(".").filter(Boolean);
  const last = parts.length ? parts[parts.length - 1] : rest;
  const slugKey = last.toLowerCase();
  if (SKILL_SLUG_LABELS[slugKey]) return SKILL_SLUG_LABELS[slugKey];
  return titleCaseKebabSegment(last);
}

function applyDisplayNameTokens(displayName: string): string {
  let s = displayName;
  for (const { re, to } of DISPLAY_TOKEN_REPLACEMENTS) {
    s = s.replace(re, to);
  }
  return s;
}

/** Windows / system folder leaf names → friendly label (exact name match; case-insensitive). */
const FILE_NAME_FRIENDLY: Record<string, string> = {
  "$recycle.bin": "Recycle Bin",
  "$windows.~bt": "Windows Setup / Upgrade Files",
  "$windows.~ws": "Windows Setup Workspace",
};

export type WorkspaceFileRowLabels = {
  /** Primary row title */
  label: string;
  /** Muted technical name when it differs from `label` */
  technical: string | null;
};

export function workspaceFileEntryLabels(rawName: string): WorkspaceFileRowLabels {
  const name = rawName.trim() || rawName;
  const key = name.toLowerCase();
  const friendly = FILE_NAME_FRIENDLY[key];
  if (friendly && friendly !== name) {
    return { label: friendly, technical: name };
  }
  return { label: name, technical: null };
}
