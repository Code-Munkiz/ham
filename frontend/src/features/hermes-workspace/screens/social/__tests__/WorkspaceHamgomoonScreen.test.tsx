import { describe, expect, it, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import * as React from "react";

vi.mock("@/features/hermes-workspace/adapters/socialAdapter", () => {
  return {
    socialAdapter: {
      getReviewQueueSummary: vi.fn(async () => ({
        summary: {
          pending_count: 0,
          approved_recent_count: 0,
          rejected_recent_count: 0,
          items: [],
          generated_at: "2026-05-20T00:00:00Z",
        },
        bridge: { status: "ready" as const },
      })),
      getLearningHints: vi.fn(async () => ({
        hints: {
          hints: "# HAMgomoon learning hints\n(no learning hints yet)\n",
          generated_at: "2026-05-20T00:00:00Z",
        },
        bridge: { status: "ready" as const },
      })),
      loadSnapshot: vi.fn(async () => ({
        snapshot: {
          providers: [],
          xStatus: null,
          xCapabilities: null,
          xSetup: null,
          xSetupSummary: null,
          xJournal: null,
          xAudit: null,
          telegramStatus: null,
          telegramCapabilities: null,
          telegramSetup: null,
          discordStatus: null,
          discordCapabilities: null,
          discordSetup: null,
          persona: null,
        },
        bridge: { status: "ready" as const },
      })),
    },
  };
});

// Import after mock so the screen picks up the mocked adapter.
import { WorkspaceHamgomoonScreen } from "../WorkspaceHamgomoonScreen";

function renderScreen() {
  return render(
    <MemoryRouter>
      <WorkspaceHamgomoonScreen />
    </MemoryRouter>,
  );
}

describe("WorkspaceHamgomoonScreen", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("renders all three cards with expected headings", async () => {
    renderScreen();
    await waitFor(() => {
      expect(screen.getByRole("heading", { name: /Drafts to review/i })).toBeInTheDocument();
    });
    expect(screen.getByRole("heading", { name: /What HAMgomoon learned/i })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: /Channels/i })).toBeInTheDocument();
  });

  it("does not render banned cockpit/legacy copy", async () => {
    const { container } = renderScreen();
    await waitFor(() => {
      expect(screen.getByRole("heading", { name: /Channels/i })).toBeInTheDocument();
    });
    expect(container.textContent ?? "").not.toContain("autonomous social reach");
    expect(container.textContent ?? "").not.toContain("HAM Social");
  });

  it("shows Discord row as Not available", async () => {
    renderScreen();
    await waitFor(() => {
      expect(screen.getByRole("heading", { name: /Channels/i })).toBeInTheDocument();
    });
    const discord = screen.getByText("Discord");
    const row = discord.closest("li");
    expect(row).not.toBeNull();
    expect(row?.textContent ?? "").toContain("Not available");
  });

  it("shows nothing-waiting copy when pending_count is 0", async () => {
    renderScreen();
    await waitFor(() => {
      expect(screen.getByText(/Nothing waiting on you right now/i)).toBeInTheDocument();
    });
  });

  it("shows getting-started copy when no hints", async () => {
    renderScreen();
    await waitFor(() => {
      expect(screen.getByText(/HAMgomoon is just getting started/i)).toBeInTheDocument();
    });
  });
});
