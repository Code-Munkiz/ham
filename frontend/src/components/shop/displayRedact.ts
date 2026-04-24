/** Avoid exposing full filesystem paths in Shop (read-only discovery). */

export function basenameOnly(p: string): string {
  const t = p.trim();
  if (!t) return "";
  const parts = t.split(/[/\\]/).filter(Boolean);
  return parts[parts.length - 1] || t;
}

/** Shorten obvious absolute path tokens inside a single display line. */
export function redactPathLikeLine(s: string): string {
  const t = s.trim();
  if (!t) return t;
  return t
    .split(/\s+/)
    .map((tok) => {
      if (/^(\/|[A-Za-z]:\\)/.test(tok)) return basenameOnly(tok);
      return tok;
    })
    .join(" ");
}
