/**
 * Device presets for mobile preview emulation — Phase 1 #4 (Tier 1 #16).
 *
 * Single source of truth for viewport dimensions and device pixel ratios.
 * Adding a new preset is a one-file edit here.
 */

export interface DevicePreset {
  id: string;
  name: string;
  /** Logical CSS pixels — portrait orientation */
  width: number;
  height: number;
  devicePixelRatio: number;
  userAgent: string;
}

export const DEVICE_PRESETS: readonly DevicePreset[] = [
  {
    id: "iphone-14",
    name: "iPhone 14",
    width: 390,
    height: 844,
    devicePixelRatio: 3,
    userAgent:
      "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1",
  },
  {
    id: "pixel-7",
    name: "Pixel 7",
    width: 412,
    height: 915,
    devicePixelRatio: 2.625,
    userAgent:
      "Mozilla/5.0 (Linux; Android 13; Pixel 7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/116.0.0.0 Mobile Safari/537.36",
  },
  {
    id: "ipad-mini",
    name: "iPad Mini",
    width: 744,
    height: 1133,
    devicePixelRatio: 2,
    userAgent:
      "Mozilla/5.0 (iPad; CPU OS 17_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1",
  },
] as const;

export const DEFAULT_DEVICE_PRESET: DevicePreset = DEVICE_PRESETS[0];

/** Return portrait/landscape dimensions for a preset and orientation. */
export function getOrientedDimensions(
  preset: DevicePreset,
  orientation: "portrait" | "landscape",
): { width: number; height: number } {
  if (orientation === "landscape") {
    return { width: preset.height, height: preset.width };
  }
  return { width: preset.width, height: preset.height };
}
