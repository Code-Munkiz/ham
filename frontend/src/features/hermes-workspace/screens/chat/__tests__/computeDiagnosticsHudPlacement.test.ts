import { describe, expect, it } from "vitest";
import { computeDiagnosticsHudPlacement } from "../ContextMeterCluster";

describe("computeDiagnosticsHudPlacement", () => {
  const vw = 800;
  const vh = 900;
  const panelW = 300;
  const panelH = 280;
  /** Anchor near bottom edge of viewport — HUD should anchor above composer (not blindly below trigger). */
  const anchorNearBottom = { top: 820, bottom: 852, left: 120, width: 96 };

  it("prefers above the anchor when fully visible", () => {
    const r = computeDiagnosticsHudPlacement(
      anchorNearBottom,
      panelW,
      panelH,
      { width: vw, height: vh },
      null,
    );
    expect(r.placement).toBe("above");
    expect(r.top).toBeLessThanOrEqual(anchorNearBottom.top - panelH - 8);
    expect(r.top + panelH).toBeLessThanOrEqual(vh - 8);
    expect(r.top).toBeGreaterThanOrEqual(8);
  });

  it("flips below when above would sit off-screen at the top", () => {
    const tightTop = { top: 12, bottom: 44, left: 120, width: 40 };
    const r = computeDiagnosticsHudPlacement(
      tightTop,
      panelW,
      panelH,
      { width: vw, height: vh },
      null,
    );
    expect(r.placement).toBe("below");
    expect(r.top).toBeGreaterThanOrEqual(tightTop.bottom + 8);
    expect(r.top + panelH).toBeLessThanOrEqual(vh - 8);
  });

  it("clamps vertically when neither above nor below fit entirely without scrolling", () => {
    const shortPanelH = 120;
    const smallVh = 160;
    const lowAnchor = { top: 120, bottom: 148, left: 120, width: 40 };
    const r = computeDiagnosticsHudPlacement(
      lowAnchor,
      panelW,
      shortPanelH,
      { width: vw, height: smallVh },
      null,
    );
    expect(r.placement).toBe("clamped");
    expect(r.top).toBeGreaterThanOrEqual(8);
    expect(r.top + shortPanelH).toBeLessThanOrEqual(smallVh - 8);
  });

  it("clamps horizontally to command panel inset", () => {
    const wideEnoughCmd = { left: 340, right: 700 };
    const centeredAnchor = { top: 820, bottom: 852, left: 512, width: 8 };
    const r = computeDiagnosticsHudPlacement(
      centeredAnchor,
      panelW,
      panelH,
      { width: vw, height: vh },
      wideEnoughCmd,
    );
    expect(r.left).toBeGreaterThanOrEqual(wideEnoughCmd.left + 8);
    expect(r.left + panelW).toBeLessThanOrEqual(wideEnoughCmd.right - 8);
  });
});
