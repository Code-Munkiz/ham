import { describe, expect, it } from "vitest";

import { inspectCodingIntent, isLikelyCodingIntent } from "../codingIntent";

describe("isLikelyCodingIntent", () => {
  describe("positive matches", () => {
    const cases: ReadonlyArray<[string, string]> = [
      ["Build me a Space Tetris game", "build + game"],
      ["Refactor the persistence layer", "refactor + layer"],
      ["Audit the persistence layer", "audit + layer"],
      ["Fix the failing test in the runner", "fix + test"],
      ["Update the README to mention managed snapshots", "update + readme"],
      ["Open a PR with the latest changes", "open + pr"],
      ["Add a new endpoint for workspace tools", "add + endpoint"],
      ["Implement a dark-mode toggle component", "implement + component"],
      ["Create a CLI that lists projects", "create + cli"],
      ["Migrate the chat session store to firestore", "migrate + store/firestore-as-db"],
      ["Fix typos in the docs", "fix + typos/docs"],
      ["Write tests for the conductor router", "write + tests"],
      ["Deploy the staging service", "deploy + service"],
      ["Run a security review of the API", "review + api"],
      ["Rename the conductor module to coding_router", "rename + module"],
      ["Generate a migration to add the workspaces table", "generate + migration"],
      ["Push my branch and open a pull request", "push + branch/pull request"],
      ["Snapshot the managed workspace and commit the change", "snapshot + commit/snapshot"],
    ];
    for (const [text, why] of cases) {
      it(`matches: ${text} (${why})`, () => {
        expect(isLikelyCodingIntent(text)).toBe(true);
        expect(inspectCodingIntent(text).reason).toBe("match");
      });
    }
  });

  describe("negative matches", () => {
    const cases: ReadonlyArray<[string, string, string]> = [
      ["", "empty", "empty"],
      ["   ", "empty whitespace", "empty"],
      ["hi", "greeting", "greeting"],
      ["Hello!", "greeting", "greeting"],
      ["Thanks", "greeting", "greeting"],
      ["good morning", "greeting", "greeting"],
      ["Explain what validators are", "conceptual: explain", "negative_lead"],
      ["What is a context engine?", "conceptual: what is", "negative_lead"],
      ["How does Hermes work?", "conceptual: how does", "negative_lead"],
      ["Tell me about the architecture", "conceptual: tell me about", "negative_lead"],
      ["Describe the chat control plane", "conceptual: describe", "negative_lead"],
      ["Compare Cursor and Droid", "conceptual: compare", "negative_lead"],
      ["Brainstorm product strategy ideas for next quarter", "brainstorm lead", "brainstorm_lead"],
      ["Let's discuss the roadmap", "discussion lead", "brainstorm_lead"],
      ["build trust with the team", "verb but no coding noun", "no_noun"],
      ["create context for the user", "verb but no coding noun", "no_noun"],
      ["app", "noun but no verb", "no_verb"],
      ["the codebase is interesting", "noun but no action verb", "no_verb"],
      ["What happens if we deploy a service?", "deploy keyword but negative lead", "negative_lead"],
    ];
    for (const [text, why, expectedReason] of cases) {
      it(`rejects: ${JSON.stringify(text)} (${why})`, () => {
        expect(isLikelyCodingIntent(text)).toBe(false);
        expect(inspectCodingIntent(text).reason).toBe(expectedReason);
      });
    }
  });

  describe("guard rails", () => {
    it("rejects null / undefined safely", () => {
      expect(isLikelyCodingIntent(null)).toBe(false);
      expect(isLikelyCodingIntent(undefined)).toBe(false);
    });
    it("rejects oversize text without spending regex budget", () => {
      const huge = "Build me an app ".repeat(1_000); // ~16,000 chars
      expect(inspectCodingIntent(huge).reason).toBe("too_long");
      expect(isLikelyCodingIntent(huge)).toBe(false);
    });
  });
});
