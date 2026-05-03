/**
 * Connected Tools UI — grouping, toggles, Connect panel (no real secrets).
 */
import { describe, expect, it, vi, beforeEach, afterEach } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import * as HamApi from "@/lib/ham/api";
import { WorkspaceConnectedToolsSection } from "../WorkspaceConnectedToolsSection";

const BASE_IDS = [
  "openrouter",
  "cursor",
  "factory_droid",
  "claude_code",
  "openclaw",
  "ai_studio",
  "antigravity",
  "github",
  "git",
  "node",
  "python",
  "docker",
  "vercel",
  "google_cloud",
  "comfyui",
] as const;

function mockTool(
  id: string,
  overrides: Partial<{
    label: string;
    category: string;
    status: string;
    enabled: boolean;
    connect_kind: string;
    credential_preview: string | null;
  }> = {},
) {
  return {
    id,
    label: overrides.label ?? id,
    category: overrides.category ?? "coding",
    status: overrides.status ?? "unknown",
    enabled: overrides.enabled ?? false,
    source: "cloud",
    capabilities: [],
    setup_hint: null,
    connect_kind: overrides.connect_kind ?? "none",
    connected_account_label: null,
    credential_preview: overrides.credential_preview ?? null,
    last_checked_at: "2026-01-01T00:00:00+00:00",
    safe_actions: [],
  };
}

const TOOL_LABELS: Record<string, string> = {
  openrouter: "OpenRouter",
  cursor: "Cursor",
  factory_droid: "Factory Droid",
  claude_code: "Claude Code",
  openclaw: "OpenClaw",
  ai_studio: "AI Studio",
  antigravity: "Antigravity",
  github: "GitHub",
  git: "Git",
  node: "Node",
  python: "Python",
  docker: "Docker",
  vercel: "Vercel",
  google_cloud: "Google Cloud",
  comfyui: "ComfyUI",
};

function buildDefaultPayload() {
  const tools = BASE_IDS.map((id) => {
    const label = TOOL_LABELS[id] ?? id;
    if (id === "ai_studio" || id === "antigravity") {
      return mockTool(id, { label, status: "unknown", connect_kind: "coming_soon" });
    }
    if (id === "openrouter") {
      return mockTool(id, {
        label,
        category: "model",
        status: "ready",
        enabled: true,
        connect_kind: "api_key",
        credential_preview: "sk-or-v…abcd",
      });
    }
    if (id === "git") {
      return mockTool(id, {
        label,
        category: "repo",
        status: "not_found",
        connect_kind: "local_scan",
      });
    }
    return mockTool(id, { label, status: "unknown" });
  });
  return { tools, scan_available: true, scan_hint: null };
}

describe("WorkspaceConnectedToolsSection", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("loads tools via fetchWorkspaceTools (not raw same-origin fetch)", async () => {
    const fetchSpy = vi.spyOn(globalThis, "fetch");
    const spy = vi.spyOn(HamApi, "fetchWorkspaceTools").mockResolvedValue(
      new Response(JSON.stringify(buildDefaultPayload()), { status: 200 }),
    );
    render(<WorkspaceConnectedToolsSection />);
    await waitFor(() => expect(screen.getByText("Connected tools")).toBeInTheDocument());
    expect(spy).toHaveBeenCalledTimes(1);
    const sameOriginToolsOnly = fetchSpy.mock.calls.some(
      (c) => typeof c[0] === "string" && c[0] === "/api/workspace/tools",
    );
    expect(sameOriginToolsOnly).toBe(false);
    fetchSpy.mockRestore();
  });

  it("Scan again uses scanWorkspaceTools helper", async () => {
    const listPayload = buildDefaultPayload();
    vi.spyOn(HamApi, "fetchWorkspaceTools").mockResolvedValue(
      new Response(JSON.stringify(listPayload), { status: 200 }),
    );
    const scanSpy = vi.spyOn(HamApi, "scanWorkspaceTools").mockResolvedValue(
      new Response(JSON.stringify(listPayload), { status: 200 }),
    );
    render(<WorkspaceConnectedToolsSection />);
    await waitFor(() => expect(screen.getByText("Scan again")).toBeInTheDocument());
    fireEvent.click(screen.getByText("Scan again"));
    await waitFor(() => expect(scanSpy).toHaveBeenCalledTimes(1));
  });

  it("renders all expected tools including AI Studio and Antigravity", async () => {
    vi.spyOn(HamApi, "fetchWorkspaceTools").mockResolvedValue(
      new Response(JSON.stringify(buildDefaultPayload()), { status: 200 }),
    );
    render(<WorkspaceConnectedToolsSection />);
    await waitFor(() => expect(screen.getByText("Connected tools")).toBeInTheDocument());
    for (const id of BASE_IDS) {
      expect(screen.getByText(TOOL_LABELS[id])).toBeInTheDocument();
    }
  });

  it("groups Ready vs Not found sections", async () => {
    vi.spyOn(HamApi, "fetchWorkspaceTools").mockResolvedValue(
      new Response(JSON.stringify(buildDefaultPayload()), { status: 200 }),
    );
    render(<WorkspaceConnectedToolsSection />);
    await waitFor(() => expect(screen.getByText("OpenRouter")).toBeInTheDocument());
    const groupHeadings = screen.getAllByRole("heading", { level: 3 });
    const labels = groupHeadings.map((h) => h.textContent);
    expect(labels).toContain("Ready");
    expect(labels).toContain("Not found");
  });

  it("does not render a toggle for Not found rows", async () => {
    vi.spyOn(HamApi, "fetchWorkspaceTools").mockResolvedValue(
      new Response(JSON.stringify(buildDefaultPayload()), { status: 200 }),
    );
    render(<WorkspaceConnectedToolsSection />);
    await waitFor(() => expect(screen.getByText("Git")).toBeInTheDocument());
    const switches = screen.queryAllByRole("switch");
    expect(switches.some((el) => el.getAttribute("aria-label")?.includes("Git"))).toBe(false);
  });

  it("Select all does not enable Not found tools (no switch for Git)", async () => {
    vi.spyOn(HamApi, "fetchWorkspaceTools").mockResolvedValue(
      new Response(JSON.stringify(buildDefaultPayload()), { status: 200 }),
    );
    render(<WorkspaceConnectedToolsSection />);
    await waitFor(() => expect(screen.getByText("Select all")).toBeInTheDocument());
    fireEvent.click(screen.getByText("Select all"));
    await waitFor(() => {
      const gitSwitch = screen.queryByRole("switch", { name: /Git/i });
      expect(gitSwitch).toBeNull();
    });
  });

  it("shows Connect panel and secure-storage message when connect returns 501", async () => {
    const payload = buildDefaultPayload();
    vi.spyOn(HamApi, "fetchWorkspaceTools").mockResolvedValue(
      new Response(JSON.stringify(payload), { status: 200 }),
    );
    const connectSpy = vi.spyOn(HamApi, "connectWorkspaceTool").mockResolvedValue(
      new Response(
        JSON.stringify({
          detail: { code: "SECURE_STORAGE_NOT_READY", message: "Secure key storage is coming next." },
        }),
        { status: 501 },
      ),
    );

    render(<WorkspaceConnectedToolsSection />);
    await waitFor(() => expect(screen.getByText("OpenRouter")).toBeInTheDocument());

    fireEvent.click(screen.getByText("OpenRouter"));
    const input = await screen.findByLabelText(/Paste your API key/i);
    fireEvent.change(input, { target: { value: "sk-or-testtokennotreal" } });
    fireEvent.click(screen.getByRole("button", { name: /^Connect$/i }));

    await waitFor(() => {
      expect(screen.getByText(/Secure key storage is coming next/i)).toBeInTheDocument();
    });
    expect(connectSpy).toHaveBeenCalledWith("openrouter", { api_key: "sk-or-testtokennotreal" });
  });
});
