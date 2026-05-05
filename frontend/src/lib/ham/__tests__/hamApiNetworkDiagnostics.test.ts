import { describe, expect, it } from "vitest";

import { isLikelyHamApiFetchNetworkFailure } from "@/lib/ham/api";

describe("isLikelyHamApiFetchNetworkFailure", () => {
  it("detects Chromium-style Failed to fetch", () => {
    expect(isLikelyHamApiFetchNetworkFailure(new TypeError("Failed to fetch"))).toBe(true);
  });

  it("detects Firefox-style network errors", () => {
    expect(
      isLikelyHamApiFetchNetworkFailure(
        new TypeError("NetworkError when attempting to fetch resource."),
      ),
    ).toBe(true);
  });

  it("detects undici-style Fetch failed", () => {
    expect(isLikelyHamApiFetchNetworkFailure(new TypeError("fetch failed"))).toBe(true);
  });

  it("does not classify arbitrary TypeErrors", () => {
    expect(isLikelyHamApiFetchNetworkFailure(new TypeError("cannot read property x"))).toBe(false);
  });

  it("does not classify plain Errors with fetch wording but wrong prototype", () => {
    expect(isLikelyHamApiFetchNetworkFailure(new Error("Failed to fetch"))).toBe(false);
  });

  it("does not classify non-errors", () => {
    expect(isLikelyHamApiFetchNetworkFailure("Failed to fetch")).toBe(false);
  });
});
