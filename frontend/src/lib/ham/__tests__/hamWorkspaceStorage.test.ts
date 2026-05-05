/**
 * Phase 1c: per-user localStorage helpers for active workspace selection.
 *
 * Pure helpers; jsdom provides a real `window.localStorage` here.
 */
import { afterEach, beforeEach, describe, expect, it } from "vitest";

import {
  __TEST__,
  activeWorkspaceStorageKey,
  clearActiveWorkspaceId,
  readActiveWorkspaceId,
  writeActiveWorkspaceId,
} from "@/lib/ham/hamWorkspaceStorage";

beforeEach(() => {
  window.localStorage.clear();
});

afterEach(() => {
  window.localStorage.clear();
});

describe("activeWorkspaceStorageKey", () => {
  it("namespaces by user id", () => {
    expect(activeWorkspaceStorageKey("u_1")).toBe(`${__TEST__.PREFIX}u_1`);
    expect(activeWorkspaceStorageKey("u_2")).toBe(`${__TEST__.PREFIX}u_2`);
  });
});

describe("read/write", () => {
  it("round-trips a workspace id", () => {
    writeActiveWorkspaceId("u_1", "ws_a");
    expect(readActiveWorkspaceId("u_1")).toBe("ws_a");
  });

  it("returns null when nothing is stored", () => {
    expect(readActiveWorkspaceId("nobody")).toBeNull();
  });

  it("ignores empty/whitespace values", () => {
    window.localStorage.setItem(activeWorkspaceStorageKey("u_1"), "   ");
    expect(readActiveWorkspaceId("u_1")).toBeNull();
  });

  it("clears via writeActiveWorkspaceId(null)", () => {
    writeActiveWorkspaceId("u_1", "ws_a");
    writeActiveWorkspaceId("u_1", null);
    expect(readActiveWorkspaceId("u_1")).toBeNull();
  });

  it("clearActiveWorkspaceId removes the entry", () => {
    writeActiveWorkspaceId("u_2", "ws_b");
    clearActiveWorkspaceId("u_2");
    expect(readActiveWorkspaceId("u_2")).toBeNull();
  });

  it("does not leak across users", () => {
    writeActiveWorkspaceId("u_1", "ws_a");
    writeActiveWorkspaceId("u_2", "ws_b");
    expect(readActiveWorkspaceId("u_1")).toBe("ws_a");
    expect(readActiveWorkspaceId("u_2")).toBe("ws_b");
    clearActiveWorkspaceId("u_1");
    expect(readActiveWorkspaceId("u_2")).toBe("ws_b");
  });

  it("ignores empty user id", () => {
    writeActiveWorkspaceId("", "ws_x");
    expect(readActiveWorkspaceId("")).toBeNull();
  });
});
