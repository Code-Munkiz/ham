/**
 * Persistence for interim coding-plan + prompt state across chat navigation/reload (sessionStorage).
 */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { CodingConductorPreviewPayload } from "@/lib/ham/api";

import {
  clearCodingPlanDraft,
  clearCodingPlanDraftsForWorkspace,
  persistCodingPlanDraft,
  readCodingPlanDraft,
} from "../codingPlanDraftSessionStorage";

function previewFixture(): CodingConductorPreviewPayload {
  return {
    kind: "coding_conductor_preview",
    preview_id: "draft-prev-1",
    task_kind: "doc_fix",
    task_confidence: 0.9,
    chosen: null,
    candidates: [],
    blockers: [],
    recommendation_reason: "fixture",
    requires_approval: true,
    approval_kind: "confirm",
    project: {
      found: true,
      project_id: "proj_draft",
      build_lane_enabled: true,
      has_github_repo: false,
    },
    is_operator: false,
  };
}

describe("codingPlanDraftSessionStorage", () => {
  beforeEach(() => {
    window.sessionStorage.clear();
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it("persists and reads back prompt + preview for workspace+session keys", () => {
    const p = previewFixture();
    persistCodingPlanDraft("ws_1", "sid_a", "  tidy readme  ", p);
    const got = readCodingPlanDraft("ws_1", "sid_a");
    expect(got).not.toBeNull();
    expect(got!.prompt).toBe("  tidy readme  ");
    expect(got!.preview.preview_id).toBe("draft-prev-1");
  });

  it("clearCodingPlanDraft removes one key", () => {
    persistCodingPlanDraft("ws_1", "sid_a", "x", previewFixture());
    clearCodingPlanDraft("ws_1", "sid_a");
    expect(readCodingPlanDraft("ws_1", "sid_a")).toBeNull();
  });

  it("clearCodingPlanDraftsForWorkspace removes every session bucket for that workspace", () => {
    persistCodingPlanDraft("ws_1", "sid_a", "a", previewFixture());
    persistCodingPlanDraft("ws_1", "sid_b", "b", previewFixture());
    persistCodingPlanDraft("ws_other", "sid_x", "c", previewFixture());
    clearCodingPlanDraftsForWorkspace("ws_1");
    expect(readCodingPlanDraft("ws_1", "sid_a")).toBeNull();
    expect(readCodingPlanDraft("ws_1", "sid_b")).toBeNull();
    expect(readCodingPlanDraft("ws_other", "sid_x")).not.toBeNull();
  });

  it("returns null for drafts older than the TTL", () => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date("2026-01-01T00:00:00Z"));
    persistCodingPlanDraft("ws_1", "sid_old", "p", previewFixture());

    vi.setSystemTime(new Date("2026-01-03T01:00:00Z"));
    expect(readCodingPlanDraft("ws_1", "sid_old")).toBeNull();
  });

  it("does nothing without workspace or session ids", () => {
    persistCodingPlanDraft("", "sid_a", "p", previewFixture());
    persistCodingPlanDraft("ws_1", "", "p", previewFixture());
    expect(window.sessionStorage.length).toBe(0);
  });
});
