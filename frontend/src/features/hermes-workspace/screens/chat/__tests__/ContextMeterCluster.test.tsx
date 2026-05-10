/**
 * Context meter cluster — compact pulse + diagnostics HUD (no native diagnostics tooltips).
 */
import { describe, expect, it, vi, beforeEach } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { ContextMeterCluster } from "../ContextMeterCluster";
import type { ChatContextMetersPayload } from "@/lib/ham/types";

vi.mock("@/lib/ham/api", () => ({
  hamApiFetch: vi.fn(),
}));

describe("ContextMeterCluster", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  const sample: ChatContextMetersPayload = {
    enabled: true,
    this_turn: {
      fill_ratio: 0.5,
      color: "green",
      unit: "estimate_tokens",
      used: 100,
      limit: 32000,
      model_id: "openrouter:default",
    },
    workspace: {
      fill_ratio: 0.72,
      color: "green",
      bottleneck_role: "commander",
      source: "local",
      used: 7200,
      limit: 10000,
      unit: "chars",
    },
    thread: {
      fill_ratio: 0.95,
      color: "red",
      approx_transcript_chars: 95000,
      thread_budget_chars: 100000,
      unit: "chars_estimate",
    },
  };

  function renderPulse(payload: ChatContextMetersPayload | null = sample) {
    render(
      <MemoryRouter>
        <ContextMeterCluster payload={payload} enabled />
      </MemoryRouter>,
    );
  }

  it("pulse trigger does not expose SYS labelling text", () => {
    renderPulse();
    expect(screen.queryByText(/^SYS\b/i)).toBeNull();
  });

  it("does not show standalone 100% readout when no critical meter", () => {
    renderPulse({
      enabled: true,
      this_turn: {
        fill_ratio: 1,
        color: "green",
        unit: "estimate_tokens",
        used: 32000,
        limit: 32000,
        model_id: "openrouter:default",
      },
      workspace: {
        fill_ratio: 0.5,
        color: "green",
        bottleneck_role: "builder",
        source: "local",
        used: 4000,
        limit: 10000,
        unit: "chars",
      },
      thread: {
        fill_ratio: 0.5,
        color: "green",
        approx_transcript_chars: 50000,
        thread_budget_chars: 100000,
        unit: "chars_estimate",
      },
    });
    expect(screen.queryByText("100%")).toBeNull();
  });

  it("shows critical pulse percent when a meter is red or ≥90%", () => {
    renderPulse();
    expect(screen.getByText("95%")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /system diagnostics/i }));
    expect(screen.getByRole("dialog")).toBeInTheDocument();
    expect(screen.getByText("System Diagnostics")).toBeInTheDocument();
  });

  it("diagnostics HUD exposes rows and progress bar tracks for context", () => {
    renderPulse();
    fireEvent.click(screen.getByRole("button", { name: /system diagnostics/i }));
    expect(screen.getByText("This turn")).toBeInTheDocument();
    expect(screen.getByText("Workspace")).toBeInTheDocument();
    expect(screen.getByText("Thread")).toBeInTheDocument();
    expect(document.querySelector('[data-hww-diagnostics-bar="turn"]')).toBeTruthy();
    expect(document.querySelector('[data-hww-diagnostics-bar="workspace"]')).toBeTruthy();
    expect(document.querySelector('[data-hww-diagnostics-bar="thread"]')).toBeTruthy();
    const threadFill = document.querySelector(
      '[data-hww-diagnostics-bar="thread"] > div[class*="rounded-full"]',
    );
    expect(threadFill).toBeTruthy();
    const w = threadFill as HTMLElement | null;
    expect(w?.style.width).toBe("95%");
  });

  it("workspace bar at 72% is not full width", () => {
    renderPulse();
    fireEvent.click(screen.getByRole("button", { name: /system diagnostics/i }));
    const wsFill = document.querySelector(
      '[data-hww-diagnostics-bar="workspace"] > div[class*="rounded-full"]',
    ) as HTMLElement | null;
    expect(wsFill?.style.width).toBe("72%");
  });

  it("pulse trigger omits native title attribute (diagnostics use HUD)", () => {
    renderPulse();
    expect(screen.getByRole("button", { name: /system diagnostics/i }).getAttribute("title")).toBeNull();
  });
});
