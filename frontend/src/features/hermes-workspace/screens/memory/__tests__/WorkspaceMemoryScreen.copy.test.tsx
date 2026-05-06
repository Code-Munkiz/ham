import { render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { WorkspaceMemoryScreen } from "../WorkspaceMemoryScreen";
import { workspaceMemoryAdapter } from "../../../adapters/memoryAdapter";

afterEach(() => {
  vi.restoreAllMocks();
});

function mockReadyEmpty() {
  vi.spyOn(workspaceMemoryAdapter, "list").mockResolvedValue({
    items: [],
    bridge: { status: "ready" },
  });
}

function mockBridgePending(detail: string) {
  vi.spyOn(workspaceMemoryAdapter, "list").mockResolvedValue({
    items: [],
    bridge: { status: "pending", detail },
  });
}

const BANNED_PHRASES = [
  "HAM Memory API",
  "Memory Heist sync",
  "JSON v0",
  "API host",
  "/api/workspace/memory",
  "/api/knowledge",
  "knowledge-browser-screen",
  "wiki tree or graph",
  "not the local Files/Terminal connection",
];

describe("WorkspaceMemoryScreen copy", () => {
  it("renders crisp present-tense Memory subtitle", async () => {
    mockReadyEmpty();
    render(<WorkspaceMemoryScreen />);
    await waitFor(() => {
      expect(
        screen.getByText(
          /Search and edit notes and preferences your agents remember between sessions\./i,
        ),
      ).toBeInTheDocument();
    });
  });

  it("does not render a Knowledge tab", async () => {
    mockReadyEmpty();
    render(<WorkspaceMemoryScreen />);
    await waitFor(() => {
      expect(screen.getByRole("heading", { name: "Memory browser" })).toBeInTheDocument();
    });
    expect(screen.queryByRole("tab", { name: /^Knowledge$/i })).toBeNull();
    expect(screen.queryByRole("button", { name: /^Knowledge$/i })).toBeNull();
  });

  it("renders crisp empty-state copy when the Memory bridge is pending", async () => {
    mockBridgePending("Bridge offline.");
    render(<WorkspaceMemoryScreen />);
    await waitFor(() => {
      expect(screen.getByText(/Memory is unavailable right now\./i)).toBeInTheDocument();
    });
    expect(
      screen.getByText(/Other workspace surfaces still work\. Retry to reconnect\./i),
    ).toBeInTheDocument();
  });

  it("does not regress to internal-jargon or version-leaking phrasing on the ready surface", async () => {
    mockReadyEmpty();
    const { container } = render(<WorkspaceMemoryScreen />);
    await waitFor(() => {
      expect(screen.getByRole("heading", { name: "Memory browser" })).toBeInTheDocument();
    });
    const text = container.textContent ?? "";
    for (const phrase of BANNED_PHRASES) {
      expect(text).not.toContain(phrase);
    }
  });

  it("does not regress to internal-jargon or version-leaking phrasing on the pending bridge surface", async () => {
    mockBridgePending("Bridge offline.");
    const { container } = render(<WorkspaceMemoryScreen />);
    await waitFor(() => {
      expect(screen.getByText(/Memory is unavailable right now\./i)).toBeInTheDocument();
    });
    const text = container.textContent ?? "";
    for (const phrase of BANNED_PHRASES) {
      expect(text).not.toContain(phrase);
    }
  });
});
