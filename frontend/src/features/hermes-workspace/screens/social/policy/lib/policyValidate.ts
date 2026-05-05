/**
 * Pure client-side validator for SocialPolicy edits.
 *
 * Mirrors server bounds from src/ham/social_policy/schema.py so the editor
 * can give immediate feedback. The server is still authoritative; preview/apply
 * will surface any mismatch as a 422.
 *
 * Hard rule: this validator REJECTS any edited document with
 * `live_autonomy_armed === true`. The editor cannot flip that flag.
 */
import {
  AUTOPILOT_MODE_VALUES,
  CONTENT_STYLE_BOUNDS,
  EMOJI_VALUES,
  LENGTH_VALUES,
  POSTING_CAP_BOUNDS,
  PROVIDER_MODE_VALUES,
  RAW_NUMERIC_ID_RE,
  REPLY_CAP_BOUNDS,
  SAFETY_BOUNDS,
  SUPPORTED_POSTING_ACTIONS,
  SUPPORTED_PROVIDER_IDS,
  SUPPORTED_TARGET_LABELS,
  TAG_SLUG_RE,
  TONE_VALUES,
  TOKEN_SHAPE_RE,
} from "./policyConstants";
import type {
  PostingCaps,
  ReplyCaps,
  SocialPolicyDoc,
} from "./policyTypes";

export interface PolicyValidationIssue {
  /** Dot-path to the offending field. */
  path: string;
  /** Human-readable reason. */
  reason: string;
}

export interface PolicyValidationResult {
  ok: boolean;
  issues: PolicyValidationIssue[];
}

function checkInt(
  value: unknown,
  path: string,
  bounds: { min: number; max: number },
  issues: PolicyValidationIssue[],
): void {
  if (typeof value !== "number" || !Number.isFinite(value) || !Number.isInteger(value)) {
    issues.push({ path, reason: "must be an integer" });
    return;
  }
  if (value < bounds.min || value > bounds.max) {
    issues.push({
      path,
      reason: `must be between ${bounds.min} and ${bounds.max}`,
    });
  }
}

function checkPostingCaps(prefix: string, caps: PostingCaps, issues: PolicyValidationIssue[]): void {
  checkInt(caps.max_per_day, `${prefix}.max_per_day`, POSTING_CAP_BOUNDS.max_per_day, issues);
  checkInt(caps.max_per_run, `${prefix}.max_per_run`, POSTING_CAP_BOUNDS.max_per_run, issues);
  checkInt(
    caps.min_spacing_minutes,
    `${prefix}.min_spacing_minutes`,
    POSTING_CAP_BOUNDS.min_spacing_minutes,
    issues,
  );
}

function checkReplyCaps(prefix: string, caps: ReplyCaps, issues: PolicyValidationIssue[]): void {
  checkInt(caps.max_per_15m, `${prefix}.max_per_15m`, REPLY_CAP_BOUNDS.max_per_15m, issues);
  checkInt(caps.max_per_hour, `${prefix}.max_per_hour`, REPLY_CAP_BOUNDS.max_per_hour, issues);
  checkInt(
    caps.max_per_user_per_day,
    `${prefix}.max_per_user_per_day`,
    REPLY_CAP_BOUNDS.max_per_user_per_day,
    issues,
  );
  checkInt(
    caps.max_per_thread_per_day,
    `${prefix}.max_per_thread_per_day`,
    REPLY_CAP_BOUNDS.max_per_thread_per_day,
    issues,
  );
  checkInt(
    caps.min_seconds_between,
    `${prefix}.min_seconds_between`,
    REPLY_CAP_BOUNDS.min_seconds_between,
    issues,
  );
  checkInt(
    caps.batch_max_per_run,
    `${prefix}.batch_max_per_run`,
    REPLY_CAP_BOUNDS.batch_max_per_run,
    issues,
  );
}

function checkSlugList(
  prefix: string,
  values: string[] | undefined,
  maxCount: number,
  issues: PolicyValidationIssue[],
): void {
  if (!Array.isArray(values)) return;
  if (values.length > maxCount) {
    issues.push({ path: prefix, reason: `at most ${maxCount} entries` });
  }
  const seen = new Set<string>();
  values.forEach((raw, idx) => {
    const path = `${prefix}[${idx}]`;
    if (typeof raw !== "string" || raw.trim().length === 0) {
      issues.push({ path, reason: "must be a non-empty string" });
      return;
    }
    const text = raw.trim();
    if (text.length > 64) {
      issues.push({ path, reason: "must be at most 64 characters" });
      return;
    }
    if (!TAG_SLUG_RE.test(text)) {
      issues.push({
        path,
        reason: "must match lower-case slug [a-z0-9][a-z0-9._-]{0,63}",
      });
      return;
    }
    if (TOKEN_SHAPE_RE.test(text)) {
      issues.push({ path, reason: "must not contain a token-shaped string" });
      return;
    }
    if (RAW_NUMERIC_ID_RE.test(text)) {
      issues.push({ path, reason: "must not contain a raw numeric ID" });
      return;
    }
    if (seen.has(text)) {
      issues.push({ path, reason: "duplicate entry" });
      return;
    }
    seen.add(text);
  });
}

/**
 * Validate the edited SocialPolicy document. Returns ok=false with a list of
 * issues; never throws.
 */
export function validatePolicy(doc: SocialPolicyDoc | null | undefined): PolicyValidationResult {
  const issues: PolicyValidationIssue[] = [];
  if (!doc || typeof doc !== "object") {
    return { ok: false, issues: [{ path: "$", reason: "policy is missing" }] };
  }

  if (doc.schema_version !== 1) {
    issues.push({ path: "schema_version", reason: "must be 1" });
  }

  if (doc.live_autonomy_armed === true) {
    issues.push({
      path: "live_autonomy_armed",
      reason: "this editor cannot arm live autonomy",
    });
  }

  if (!AUTOPILOT_MODE_VALUES.includes(doc.autopilot_mode)) {
    issues.push({
      path: "autopilot_mode",
      reason: `must be one of ${AUTOPILOT_MODE_VALUES.join("|")}`,
    });
  }

  // persona ref — read-only in editor; still validate shape.
  if (!doc.persona || typeof doc.persona.persona_id !== "string" || doc.persona.persona_id.trim() === "") {
    issues.push({ path: "persona.persona_id", reason: "required" });
  } else if (!TAG_SLUG_RE.test(doc.persona.persona_id.trim())) {
    issues.push({ path: "persona.persona_id", reason: "must be a lower-case slug" });
  }
  if (
    typeof doc.persona?.persona_version !== "number" ||
    !Number.isInteger(doc.persona.persona_version) ||
    doc.persona.persona_version < 1 ||
    doc.persona.persona_version > 10_000
  ) {
    issues.push({ path: "persona.persona_version", reason: "must be 1..10000" });
  }

  // content_style
  const cs = doc.content_style;
  if (!cs || !TONE_VALUES.includes(cs.tone)) {
    issues.push({ path: "content_style.tone", reason: `must be one of ${TONE_VALUES.join("|")}` });
  }
  if (!cs || !LENGTH_VALUES.includes(cs.length_preference)) {
    issues.push({
      path: "content_style.length_preference",
      reason: `must be one of ${LENGTH_VALUES.join("|")}`,
    });
  }
  if (!cs || !EMOJI_VALUES.includes(cs.emoji_policy)) {
    issues.push({
      path: "content_style.emoji_policy",
      reason: `must be one of ${EMOJI_VALUES.join("|")}`,
    });
  }
  if (cs) {
    checkSlugList(
      "content_style.nature_tags",
      cs.nature_tags,
      CONTENT_STYLE_BOUNDS.nature_tags_max_count,
      issues,
    );
  }

  // safety_rules
  const sr = doc.safety_rules;
  if (!sr) {
    issues.push({ path: "safety_rules", reason: "required" });
  } else {
    checkSlugList(
      "safety_rules.blocked_topics",
      sr.blocked_topics,
      SAFETY_BOUNDS.blocked_topics_max_count,
      issues,
    );
    if (typeof sr.block_links !== "boolean") {
      issues.push({ path: "safety_rules.block_links", reason: "must be boolean" });
    }
    if (
      typeof sr.min_relevance !== "number" ||
      !Number.isFinite(sr.min_relevance) ||
      sr.min_relevance < SAFETY_BOUNDS.min_relevance.min ||
      sr.min_relevance > SAFETY_BOUNDS.min_relevance.max
    ) {
      issues.push({ path: "safety_rules.min_relevance", reason: "must be 0..1" });
    }
    checkInt(
      sr.consecutive_failure_stop,
      "safety_rules.consecutive_failure_stop",
      SAFETY_BOUNDS.consecutive_failure_stop,
      issues,
    );
    checkInt(
      sr.policy_rejection_stop,
      "safety_rules.policy_rejection_stop",
      SAFETY_BOUNDS.policy_rejection_stop,
      issues,
    );
  }

  // providers
  if (!doc.providers || typeof doc.providers !== "object") {
    issues.push({ path: "providers", reason: "required" });
  } else {
    for (const id of SUPPORTED_PROVIDER_IDS) {
      const prov = doc.providers[id];
      if (!prov) continue; // server allows missing providers
      const prefix = `providers.${id}`;
      if (prov.provider_id !== id) {
        issues.push({ path: `${prefix}.provider_id`, reason: `must equal "${id}"` });
      }
      if (!PROVIDER_MODE_VALUES.includes(prov.posting_mode)) {
        issues.push({
          path: `${prefix}.posting_mode`,
          reason: `must be one of ${PROVIDER_MODE_VALUES.join("|")}`,
        });
      }
      if (!PROVIDER_MODE_VALUES.includes(prov.reply_mode)) {
        issues.push({
          path: `${prefix}.reply_mode`,
          reason: `must be one of ${PROVIDER_MODE_VALUES.join("|")}`,
        });
      }
      checkPostingCaps(`${prefix}.posting_caps`, prov.posting_caps, issues);
      checkReplyCaps(`${prefix}.reply_caps`, prov.reply_caps, issues);

      if (!Array.isArray(prov.posting_actions_allowed)) {
        issues.push({ path: `${prefix}.posting_actions_allowed`, reason: "must be array" });
      } else {
        if (prov.posting_actions_allowed.length > 3) {
          issues.push({
            path: `${prefix}.posting_actions_allowed`,
            reason: "at most 3 entries",
          });
        }
        const seen = new Set<string>();
        prov.posting_actions_allowed.forEach((act, idx) => {
          if (!SUPPORTED_POSTING_ACTIONS.includes(act)) {
            issues.push({
              path: `${prefix}.posting_actions_allowed[${idx}]`,
              reason: `must be one of ${SUPPORTED_POSTING_ACTIONS.join("|")}`,
            });
            return;
          }
          if (seen.has(act)) {
            issues.push({
              path: `${prefix}.posting_actions_allowed[${idx}]`,
              reason: "duplicate entry",
            });
            return;
          }
          seen.add(act);
        });
      }

      if (!Array.isArray(prov.targets)) {
        issues.push({ path: `${prefix}.targets`, reason: "must be array" });
      } else {
        if (prov.targets.length > 4) {
          issues.push({ path: `${prefix}.targets`, reason: "at most 4 entries" });
        }
        const seen = new Set<string>();
        prov.targets.forEach((t, idx) => {
          if (!t || !SUPPORTED_TARGET_LABELS.includes(t.label)) {
            issues.push({
              path: `${prefix}.targets[${idx}].label`,
              reason: `must be one of ${SUPPORTED_TARGET_LABELS.join("|")}`,
            });
            return;
          }
          if (typeof t.enabled !== "boolean") {
            issues.push({
              path: `${prefix}.targets[${idx}].enabled`,
              reason: "must be boolean",
            });
          }
          if (seen.has(t.label)) {
            issues.push({
              path: `${prefix}.targets[${idx}].label`,
              reason: "duplicate label",
            });
            return;
          }
          seen.add(t.label);
        });
      }
    }
  }

  return { ok: issues.length === 0, issues };
}

/** Cheap predicate for "do we have any local validation problems?". */
export function isPolicyValid(doc: SocialPolicyDoc | null | undefined): boolean {
  return validatePolicy(doc).ok;
}
