import { describe, expect, it } from "vitest";
import { ADVISORY_LABELS, ERROR_LABELS, labelForError } from "../policyCopy";
import {
  APPLY_CONFIRMATION_PHRASE,
  RESTORE_CONFIRMATION_PHRASE,
  LIVE_AUTONOMY_CONFIRMATION_PHRASE,
} from "../policyConstants";

describe("policy copy / constants", () => {
  it("APPLY_CONFIRMATION_PHRASE is exactly the server constant", () => {
    expect(APPLY_CONFIRMATION_PHRASE).toBe("SAVE SOCIAL POLICY");
  });

  it("Other server confirmation phrases are pinned (defensive)", () => {
    expect(RESTORE_CONFIRMATION_PHRASE).toBe("RESTORE SOCIAL POLICY");
    expect(LIVE_AUTONOMY_CONFIRMATION_PHRASE).toBe("ARM SOCIAL AUTONOMY");
  });

  it("All 7 D.2 advisory codes have non-empty labels", () => {
    const codes = [
      "policy_document_missing",
      "policy_provider_unmapped",
      "policy_posting_mode_off",
      "policy_reply_mode_off",
      "policy_target_label_disabled",
      "policy_live_autonomy_not_armed",
      "policy_action_not_allowed",
    ] as const;
    for (const code of codes) {
      expect(typeof ADVISORY_LABELS[code]).toBe("string");
      expect(ADVISORY_LABELS[code].trim().length).toBeGreaterThan(0);
    }
  });

  it("All server error codes have non-empty labels", () => {
    const codes = [
      "SOCIAL_POLICY_AUTH_REQUIRED",
      "SOCIAL_POLICY_AUTH_INVALID",
      "SOCIAL_POLICY_WRITES_DISABLED",
      "SOCIAL_POLICY_PHRASE_INVALID",
      "SOCIAL_POLICY_LIVE_AUTONOMY_DISABLED",
      "SOCIAL_POLICY_LIVE_AUTONOMY_PHRASE_INVALID",
      "SOCIAL_POLICY_REVISION_CONFLICT",
      "SOCIAL_POLICY_APPLY_INVALID",
      "SOCIAL_POLICY_PREVIEW_INVALID",
      "SOCIAL_POLICY_DOCUMENT_INVALID",
      "SOCIAL_POLICY_BACKUP_NOT_FOUND",
      "SOCIAL_POLICY_ROLLBACK_INVALID",
      "SOCIAL_POLICY_ROLLBACK_PHRASE_INVALID",
      "UNKNOWN",
    ] as const;
    for (const code of codes) {
      expect(typeof ERROR_LABELS[code]).toBe("string");
      expect(ERROR_LABELS[code].trim().length).toBeGreaterThan(0);
    }
  });

  it("labelForError maps codes to human strings", () => {
    expect(
      labelForError({
        status: 409,
        code: "SOCIAL_POLICY_REVISION_CONFLICT",
        message: "x",
      }),
    ).toMatch(/changed elsewhere/i);
  });
});
