/**
 * Tests for MobilePreviewFrame.tsx — Phase 1 #4 (Tier 1 #16).
 */

import { render, screen, fireEvent } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { MobilePreviewFrame } from "../MobilePreviewFrame";
import { DEVICE_PRESETS } from "../devicePresets";

const IPHONE = DEVICE_PRESETS.find((p) => p.id === "iphone-14")!;

describe("MobilePreviewFrame", () => {
  it("renders with default preset when none provided", () => {
    render(<MobilePreviewFrame previewUrl="http://localhost:3000" />);
    const container = screen.getByTestId("mobile-preview-frame-container");
    expect(container).toBeDefined();
  });

  it("renders correct viewport width for given preset", () => {
    render(<MobilePreviewFrame preset={IPHONE} previewUrl="http://localhost:3000" />);
    const container = screen.getByTestId("mobile-preview-frame-container");
    expect(Number(container.getAttribute("data-width"))).toBe(IPHONE.width);
  });

  it("renders correct viewport height for given preset", () => {
    render(<MobilePreviewFrame preset={IPHONE} previewUrl="http://localhost:3000" />);
    const container = screen.getByTestId("mobile-preview-frame-container");
    expect(Number(container.getAttribute("data-height"))).toBe(IPHONE.height);
  });

  it("starts in portrait orientation", () => {
    render(<MobilePreviewFrame preset={IPHONE} previewUrl="http://localhost:3000" />);
    const container = screen.getByTestId("mobile-preview-frame-container");
    expect(container.getAttribute("data-orientation")).toBe("portrait");
  });

  it("toggles to landscape on button click", () => {
    render(<MobilePreviewFrame preset={IPHONE} previewUrl="http://localhost:3000" />);
    const toggle = screen.getByTestId("mobile-preview-orientation-toggle");
    fireEvent.click(toggle);
    const container = screen.getByTestId("mobile-preview-frame-container");
    expect(container.getAttribute("data-orientation")).toBe("landscape");
  });

  it("swaps width/height in landscape mode", () => {
    render(<MobilePreviewFrame preset={IPHONE} previewUrl="http://localhost:3000" />);
    fireEvent.click(screen.getByTestId("mobile-preview-orientation-toggle"));
    const container = screen.getByTestId("mobile-preview-frame-container");
    expect(Number(container.getAttribute("data-width"))).toBe(IPHONE.height);
    expect(Number(container.getAttribute("data-height"))).toBe(IPHONE.width);
  });

  it("toggles back to portrait on second click", () => {
    render(<MobilePreviewFrame preset={IPHONE} previewUrl="http://localhost:3000" />);
    const toggle = screen.getByTestId("mobile-preview-orientation-toggle");
    fireEvent.click(toggle);
    fireEvent.click(toggle);
    const container = screen.getByTestId("mobile-preview-frame-container");
    expect(container.getAttribute("data-orientation")).toBe("portrait");
  });

  it("displays the preset name", () => {
    render(<MobilePreviewFrame preset={IPHONE} previewUrl="http://localhost:3000" />);
    expect(screen.getByText(IPHONE.name)).toBeDefined();
  });

  it("renders an iframe with the provided previewUrl", () => {
    render(<MobilePreviewFrame preset={IPHONE} previewUrl="http://localhost:9999" />);
    const iframe = screen.getByTestId("mobile-preview-iframe") as HTMLIFrameElement;
    expect(iframe.src).toContain("localhost:9999");
  });
});
