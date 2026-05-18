/**
 * MobilePreviewFrame — Phase 1 #4 (Tier 1 #16).
 *
 * Renders the preview iframe with simulated mobile viewport dimensions from
 * a DevicePreset. Supports portrait/landscape orientation toggle.
 *
 * Props:
 *   preset      — device preset from devicePresets.ts
 *   previewUrl  — URL to load in the iframe
 *   iframeKey   — optional key prop to force iframe reload on change
 */

import React from "react";
import { DEFAULT_DEVICE_PRESET, DevicePreset, getOrientedDimensions } from "./devicePresets";

interface MobilePreviewFrameProps {
  preset?: DevicePreset;
  previewUrl: string;
  iframeKey?: string;
}

export function MobilePreviewFrame({
  preset = DEFAULT_DEVICE_PRESET,
  previewUrl,
  iframeKey,
}: MobilePreviewFrameProps) {
  const [orientation, setOrientation] = React.useState<"portrait" | "landscape">("portrait");
  const { width, height } = getOrientedDimensions(preset, orientation);

  return (
    <div className="flex flex-col items-center gap-2">
      <div className="flex items-center gap-2">
        <span className="text-[10px] uppercase tracking-wide text-white/50">{preset.name}</span>
        <button
          type="button"
          onClick={() => setOrientation((o) => (o === "portrait" ? "landscape" : "portrait"))}
          className="rounded px-2 py-0.5 text-[10px] font-medium uppercase tracking-wide text-white/50 hover:bg-white/[0.06] outline-none focus-visible:ring-2 focus-visible:ring-emerald-400/30"
          data-testid="mobile-preview-orientation-toggle"
          aria-label={`Switch to ${orientation === "portrait" ? "landscape" : "portrait"}`}
        >
          {orientation === "portrait" ? "⟳ Landscape" : "⟲ Portrait"}
        </button>
      </div>
      <div
        style={{ width, maxWidth: "100%", height }}
        className="overflow-hidden rounded-lg border border-white/[0.12] bg-black/20"
        data-testid="mobile-preview-frame-container"
        data-preset-id={preset.id}
        data-orientation={orientation}
        data-width={width}
        data-height={height}
      >
        <iframe
          key={iframeKey ?? `${previewUrl}|${preset.id}|${orientation}`}
          title={`Mobile preview — ${preset.name} ${orientation}`}
          src={previewUrl}
          style={{ width, height, border: "none" }}
          sandbox="allow-same-origin allow-scripts allow-forms allow-popups"
          data-testid="mobile-preview-iframe"
        />
      </div>
      <span className="text-[9px] text-white/30">
        {width}&thinsp;&times;&thinsp;{height}&thinsp;px&nbsp;@&nbsp;{preset.devicePixelRatio}x
      </span>
    </div>
  );
}
