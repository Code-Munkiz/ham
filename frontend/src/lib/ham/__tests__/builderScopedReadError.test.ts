import { describe, expect, it } from "vitest";

import {
  HamBuilderScopedReadError,
  shouldResetHamWorkbenchProjectSelection,
} from "@/lib/ham/api";

describe("shouldResetHamWorkbenchProjectSelection", () => {
  it("fires only for PROJECT_NOT_FOUND on 404", () => {
    expect(
      shouldResetHamWorkbenchProjectSelection(
        new HamBuilderScopedReadError("not found", 404, "PROJECT_NOT_FOUND"),
      ),
    ).toBe(true);

    expect(
      shouldResetHamWorkbenchProjectSelection(
        new HamBuilderScopedReadError("other", 404, "SNAPSHOT_NOT_FOUND"),
      ),
    ).toBe(false);

    expect(
      shouldResetHamWorkbenchProjectSelection(
        new HamBuilderScopedReadError("forbidden", 403, "PROJECT_NOT_FOUND"),
      ),
    ).toBe(false);

    expect(shouldResetHamWorkbenchProjectSelection(new Error("boom"))).toBe(false);
  });
});
