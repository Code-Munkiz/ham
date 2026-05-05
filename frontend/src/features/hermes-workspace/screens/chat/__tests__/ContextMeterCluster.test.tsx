/**
 * Context meter cluster — rings + tooltips (native title).
 */
import { describe, expect, it, vi, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
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
      fill_ratio: 0.9,
      color: "red",
      bottleneck_role: "commander",
      source: "local",
      used: 9000,
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

  it("renders Turn, Ws, Thr labels", () => {
    render(
      <MemoryRouter>
        <ContextMeterCluster payload={sample} enabled />
      </MemoryRouter>,
    );
    expect(screen.getByText("Turn")).toBeInTheDocument();
    expect(screen.getByText("Ws")).toBeInTheDocument();
    expect(screen.getByText("Thr")).toBeInTheDocument();
  });

  it("includes numeric line and action in workspace tooltip", () => {
    render(
      <MemoryRouter>
        <ContextMeterCluster payload={sample} enabled />
      </MemoryRouter>,
    );
    const ws = screen.getAllByRole("button")[1];
    const title = ws.getAttribute("title") ?? "";
    expect(title).toMatch(/9,?000/);
    expect(title.toLowerCase()).toContain("context");
  });

  it("thread high includes new chat nudge", () => {
    render(
      <MemoryRouter>
        <ContextMeterCluster payload={sample} enabled />
      </MemoryRouter>,
    );
    const thr = screen.getAllByRole("button")[2];
    expect(thr.getAttribute("title") ?? "").toMatch(/new chat session/i);
  });
});
