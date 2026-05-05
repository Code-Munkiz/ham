/**
 * Pure leaf-level diff for instant UI feedback. The server diff (returned by
 * /api/social/policy/preview) is authoritative for the apply UI. This local
 * diff only powers the "N changes pending" badge while editing.
 */
import type { SocialPolicyDiffEntry, SocialPolicyDoc } from "./policyTypes";

function isPlainObject(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function valuesEqual(a: unknown, b: unknown): boolean {
  if (Object.is(a, b)) return true;
  if (typeof a !== typeof b) return false;
  if (Array.isArray(a) && Array.isArray(b)) {
    if (a.length !== b.length) return false;
    for (let i = 0; i < a.length; i += 1) {
      if (!valuesEqual(a[i], b[i])) return false;
    }
    return true;
  }
  if (isPlainObject(a) && isPlainObject(b)) {
    const ak = Object.keys(a).sort();
    const bk = Object.keys(b).sort();
    if (ak.length !== bk.length) return false;
    for (let i = 0; i < ak.length; i += 1) {
      if (ak[i] !== bk[i]) return false;
      if (!valuesEqual(a[ak[i]], b[bk[i]])) return false;
    }
    return true;
  }
  return false;
}

function walk(
  before: unknown,
  after: unknown,
  path: string,
  out: SocialPolicyDiffEntry[],
): void {
  if (valuesEqual(before, after)) return;
  if (Array.isArray(before) || Array.isArray(after) || !isPlainObject(before) || !isPlainObject(after)) {
    out.push({ path, before, after });
    return;
  }
  const keys = new Set<string>([...Object.keys(before), ...Object.keys(after)]);
  for (const key of Array.from(keys).sort()) {
    walk(before[key], after[key], path ? `${path}.${key}` : key, out);
  }
}

/**
 * Compute leaf-level diff between two policy documents. Order-independent
 * for object keys; arrays are treated as opaque values (length / order
 * counts as a change).
 */
export function diffPolicy(
  before: SocialPolicyDoc | null | undefined,
  after: SocialPolicyDoc | null | undefined,
): SocialPolicyDiffEntry[] {
  const out: SocialPolicyDiffEntry[] = [];
  if (!before && !after) return out;
  if (!before || !after) {
    out.push({ path: "$", before, after });
    return out;
  }
  walk(before, after, "", out);
  return out;
}

/** Is anything pending? */
export function hasPolicyChanges(
  before: SocialPolicyDoc | null | undefined,
  after: SocialPolicyDoc | null | undefined,
): boolean {
  if (!before && !after) return false;
  if (!before || !after) return true;
  return diffPolicy(before, after).length > 0;
}
