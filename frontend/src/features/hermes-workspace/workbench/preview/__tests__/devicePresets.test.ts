/**
 * Tests for devicePresets.ts — Phase 1 #4 (Tier 1 #16).
 */

import { describe, expect, it } from "vitest";
import {
  DEFAULT_DEVICE_PRESET,
  DEVICE_PRESETS,
  getOrientedDimensions,
} from "../devicePresets";

describe("DEVICE_PRESETS", () => {
  it("contains at least iPhone 14, Pixel 7, iPad Mini", () => {
    const ids = DEVICE_PRESETS.map((p) => p.id);
    expect(ids).toContain("iphone-14");
    expect(ids).toContain("pixel-7");
    expect(ids).toContain("ipad-mini");
  });

  it("each preset has positive width and height", () => {
    for (const p of DEVICE_PRESETS) {
      expect(p.width).toBeGreaterThan(0);
      expect(p.height).toBeGreaterThan(0);
    }
  });

  it("each preset has a devicePixelRatio > 0", () => {
    for (const p of DEVICE_PRESETS) {
      expect(p.devicePixelRatio).toBeGreaterThan(0);
    }
  });

  it("each preset has a non-empty userAgent", () => {
    for (const p of DEVICE_PRESETS) {
      expect(p.userAgent.trim().length).toBeGreaterThan(0);
    }
  });

  it("DEFAULT_DEVICE_PRESET is the first preset", () => {
    expect(DEFAULT_DEVICE_PRESET).toBe(DEVICE_PRESETS[0]);
  });
});

describe("getOrientedDimensions", () => {
  const preset = DEFAULT_DEVICE_PRESET; // iPhone 14: 390 x 844

  it("portrait returns original width × height", () => {
    const { width, height } = getOrientedDimensions(preset, "portrait");
    expect(width).toBe(preset.width);
    expect(height).toBe(preset.height);
  });

  it("landscape swaps width and height", () => {
    const { width, height } = getOrientedDimensions(preset, "landscape");
    expect(width).toBe(preset.height);
    expect(height).toBe(preset.width);
  });

  it("landscape width is larger than landscape height for phone presets", () => {
    const phonePreset = DEVICE_PRESETS.find((p) => p.id === "iphone-14")!;
    const { width, height } = getOrientedDimensions(phonePreset, "landscape");
    expect(width).toBeGreaterThan(height);
  });
});
