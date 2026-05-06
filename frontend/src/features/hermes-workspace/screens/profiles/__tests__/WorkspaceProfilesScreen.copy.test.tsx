import { render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { WorkspaceProfilesScreen } from "../WorkspaceProfilesScreen";
import { workspaceProfilesAdapter } from "../../../adapters/profilesAdapter";

afterEach(() => {
  vi.restoreAllMocks();
});

function mockEmptyList() {
  vi.spyOn(workspaceProfilesAdapter, "list").mockResolvedValue({
    profiles: [],
    defaultProfileId: null,
    bridge: { status: "ready" },
  });
}

describe("WorkspaceProfilesScreen copy", () => {
  it("renders crisp present-tense lead description for the Profiles surface", async () => {
    mockEmptyList();
    render(<WorkspaceProfilesScreen />);
    await waitFor(() => {
      expect(
        screen.getByText(/Save model and system-prompt presets per agent persona\./i),
      ).toBeInTheDocument();
    });
  });

  it("does not render a Monitoring tab", async () => {
    mockEmptyList();
    render(<WorkspaceProfilesScreen />);
    await waitFor(() => {
      expect(screen.getByRole("heading", { name: "Profiles" })).toBeInTheDocument();
    });
    expect(screen.queryByRole("button", { name: /^Monitoring$/i })).toBeNull();
  });

  it("does not regress to internal-jargon or version-leaking phrasing", async () => {
    mockEmptyList();
    const { container } = render(<WorkspaceProfilesScreen />);
    await waitFor(() => {
      expect(screen.getByRole("heading", { name: "Profiles" })).toBeInTheDocument();
    });
    const text = container.textContent ?? "";
    const banned = [
      "HAM v0",
      "crew-screen.tsx",
      "layout placeholder",
      "~/.hermes/profiles",
      "/api/workspace/profiles",
      "Hermes agent pool",
    ];
    for (const phrase of banned) {
      expect(text).not.toContain(phrase);
    }
  });
});
