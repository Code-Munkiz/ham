/**
 * Locks the contract from VAL-FE-001..004:
 *   - Default chat send payload omits `workbench_mode: "agent"` (and any builder posture).
 *   - Default chat send payload omits `worker: "builder"`.
 *   - When the user has explicitly chosen an agent workbench mode / builder worker, the outbound
 *     payload still carries those fields so server-side builder routing continues to work.
 *
 * These tests target the pure helper that produces the posture spread used in
 * `WorkspaceChatScreen` when building the `/api/chat/stream` body, so they cover the contract
 * independently of the surrounding render path. A separate render test in
 * `WorkspaceChatScreen.posture.test.tsx` proves the helper is wired into the real send path.
 */
import { describe, expect, it } from "vitest";

import { buildWorkspaceChatPostureFields } from "../workspaceChatPosture";

describe("buildWorkspaceChatPostureFields", () => {
  it("omits workbench_mode and worker when both are null (default chat)", () => {
    const fields = buildWorkspaceChatPostureFields({ workbenchMode: null, worker: null });
    expect(fields).toEqual({});
    expect("workbench_mode" in fields).toBe(false);
    expect("worker" in fields).toBe(false);
  });

  it("omits both when called with no inputs (defensive default)", () => {
    const fields = buildWorkspaceChatPostureFields({});
    expect(fields).toEqual({});
  });

  it("includes workbench_mode and worker when user explicitly chose agent + builder", () => {
    const fields = buildWorkspaceChatPostureFields({
      workbenchMode: "agent",
      worker: "builder",
    });
    expect(fields).toEqual({ workbench_mode: "agent", worker: "builder" });
  });

  it("includes only workbench_mode when worker is left at the default", () => {
    const fields = buildWorkspaceChatPostureFields({ workbenchMode: "plan", worker: null });
    expect(fields).toEqual({ workbench_mode: "plan" });
    expect("worker" in fields).toBe(false);
  });

  it("includes only worker when workbench mode is left at the default", () => {
    const fields = buildWorkspaceChatPostureFields({ workbenchMode: null, worker: "builder" });
    expect(fields).toEqual({ worker: "builder" });
    expect("workbench_mode" in fields).toBe(false);
  });

  it("ignores whitespace-only worker values (treated as default)", () => {
    const fields = buildWorkspaceChatPostureFields({ workbenchMode: null, worker: "   " });
    expect(fields).toEqual({});
  });

  it("ignores unknown workbench mode strings", () => {
    const fields = buildWorkspaceChatPostureFields({
      // @ts-expect-error — guard at runtime for unexpected upstream values.
      workbenchMode: "ship-it",
      worker: null,
    });
    expect(fields).toEqual({});
  });
});
