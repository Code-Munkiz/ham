import { describe, expect, it } from "vitest";

import { isLikelyCodingIntent, looksLikeBuilderAppPrompt } from "../codingIntent";
import {
  BUILD_GENERATION_GENERATING_POINTER,
  BUILD_GENERATION_INTERRUPTED_POINTER,
  BUILD_GENERATION_INTERRUPTED_TOAST,
  BUILD_GENERATION_PREPARING_POINTER,
  BUILD_GENERATION_READY_POINTER,
  buildGenerationChatPointer,
  type BuildGenerationPhase,
} from "../codingPlanCardCopy";

const SALES_OPS_PROMPT =
  "Build a sales ops dashboard with an executive summary KPI row, agent performance, " +
  "commission earned and pending, and date/team filters. Use static local sample data — no backend.";

// Internals that must never appear in any user-facing lifecycle pointer.
const FORBIDDEN_TOKENS = [
  "registry_v2",
  "proposal_digest",
  "base_revision",
  "gate report",
  "recipe id",
  "pack id",
  "scaffold_quality",
  "builder studio",
  "playbook context",
  ".yaml",
];

describe("looksLikeBuilderAppPrompt", () => {
  it("matches builder-style app/site/game/dashboard prompts", () => {
    expect(looksLikeBuilderAppPrompt(SALES_OPS_PROMPT)).toBe(true);
    expect(looksLikeBuilderAppPrompt("make me a landing page for my startup")).toBe(true);
    expect(looksLikeBuilderAppPrompt("create a tetris game")).toBe(true);
    expect(looksLikeBuilderAppPrompt("generate a saas dashboard")).toBe(true);
  });

  it("does not match conversational or repo-edit prompts", () => {
    expect(looksLikeBuilderAppPrompt("")).toBe(false);
    expect(looksLikeBuilderAppPrompt("hi")).toBe(false);
    expect(looksLikeBuilderAppPrompt("what is a dashboard?")).toBe(false);
    expect(looksLikeBuilderAppPrompt("explain how the build app works")).toBe(false);
    // Repo coding task (handled by the conductor preview path, not Builder Happy Path).
    expect(looksLikeBuilderAppPrompt("refactor the persistence layer")).toBe(false);
  });

  it("is mutually exclusive with the conductor coding-intent gate for builder prompts", () => {
    // Builder app prompts are intentionally excluded from isLikelyCodingIntent so
    // they route to the Builder Happy Path scaffold (not the conductor preview).
    expect(looksLikeBuilderAppPrompt(SALES_OPS_PROMPT)).toBe(true);
    expect(isLikelyCodingIntent(SALES_OPS_PROMPT)).toBe(false);
  });
});

describe("buildGenerationChatPointer", () => {
  it("returns concise plain-language copy per lifecycle phase", () => {
    expect(buildGenerationChatPointer("preparing")).toBe(BUILD_GENERATION_PREPARING_POINTER);
    expect(buildGenerationChatPointer("generating")).toBe(BUILD_GENERATION_GENERATING_POINTER);
    expect(buildGenerationChatPointer("ready")).toBe(BUILD_GENERATION_READY_POINTER);
    expect(buildGenerationChatPointer("interrupted")).toBe(BUILD_GENERATION_INTERRUPTED_POINTER);
  });

  it("returns null for idle (no pointer shown)", () => {
    expect(buildGenerationChatPointer("idle")).toBeNull();
  });

  it("interrupted copy is recoverable, not a dead-end failure", () => {
    const copy = buildGenerationChatPointer("interrupted") ?? "";
    expect(copy.toLowerCase()).toContain("checking the latest build status");
    expect(copy.toLowerCase()).not.toContain("failed");
    expect(copy.toLowerCase()).not.toContain("error");
    expect(copy.toLowerCase()).not.toContain("crashed");
  });

  it("never leaks build-kit internals in any phase", () => {
    const phases: BuildGenerationPhase[] = [
      "idle",
      "preparing",
      "generating",
      "ready",
      "interrupted",
    ];
    for (const phase of phases) {
      const copy = (buildGenerationChatPointer(phase) ?? "").toLowerCase();
      for (const token of FORBIDDEN_TOKENS) {
        expect(copy).not.toContain(token);
      }
      expect(copy).not.toMatch(/https?:\/\//);
    }
  });
});

describe("BUILD_GENERATION_INTERRUPTED_TOAST", () => {
  it("is calm and recoverable — no crash/failed/connection-interrupted framing", () => {
    const t = BUILD_GENERATION_INTERRUPTED_TOAST.toLowerCase();
    expect(t).toContain("still building");
    expect(t).toContain("checking the latest status");
    expect(t).not.toContain("connection interrupted");
    expect(t).not.toContain("failed");
    expect(t).not.toContain("crashed");
    expect(t).not.toContain("error");
  });

  it("never leaks build-kit internals", () => {
    const t = BUILD_GENERATION_INTERRUPTED_TOAST.toLowerCase();
    for (const token of FORBIDDEN_TOKENS) {
      expect(t).not.toContain(token);
    }
    expect(t).not.toMatch(/https?:\/\//);
  });
});
