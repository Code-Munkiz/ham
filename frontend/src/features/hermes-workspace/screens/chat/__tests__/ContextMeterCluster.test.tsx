/**
 * Context meter cluster — rings + diagnostics HUD (no native title tooltips).
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

  it("opens dark diagnostics HUD with workspace numeric detail", async () => {
    render(
      <MemoryRouter>
        <ContextMeterCluster payload={sample} enabled />
      </MemoryRouter>,
    );
    const wsBtn = screen.getByRole("button", { name: "Open system diagnostics — workspace" });
    fireEvent.click(wsBtn);
    expect(await screen.findByText("System diagnostics")).toBeInTheDocument();
    expect(screen.getByText(/9,?000/)).toBeInTheDocument();
  });

  it("thread section in HUD mentions new chat session", async () => {
    render(
      <MemoryRouter>
        <ContextMeterCluster payload={sample} enabled />
      </MemoryRouter>,
    );
    fireEvent.click(screen.getByRole("button", { name: "Open system diagnostics — thread" }));
    expect(await screen.findByText("System diagnostics")).toBeInTheDocument();
    expect(screen.getByText(/new chat session/i)).toBeInTheDocument();
  });
});
