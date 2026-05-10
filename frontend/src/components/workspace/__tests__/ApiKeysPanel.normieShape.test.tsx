/**
 * Privacy regression: the workspace Model & provider settings surface must not leak
 * deployment-global Cursor operator details (env names, file paths, key preview,
 * operator email, internal Ham→Cursor route mapping, rotate/clear buttons) to
 * normal signed-in workspace users.
 *
 * The server-side gate is `src/api/cursor_settings.py` keyed by
 * `HAM_WORKSPACE_OPERATOR_EMAILS`; this test pins the corresponding
 * client-side gate inside `ApiKeysPanel`.
 */
import { describe, expect, it, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";

import type { CursorCredentialsStatus } from "@/lib/ham/types";

const {
  fetchCursorCredentialsStatusMock,
  saveCursorApiKeyMock,
  clearSavedCursorApiKeyMock,
  fetchCursorModelsMock,
  ensureProjectIdMock,
  fetchContextEngineMock,
  fetchProjectContextEngineMock,
  fetchSettingsWriteStatusMock,
  postSettingsApplyMock,
  postSettingsPreviewMock,
} = vi.hoisted(() => ({
  fetchCursorCredentialsStatusMock: vi.fn<() => Promise<CursorCredentialsStatus>>(),
  saveCursorApiKeyMock: vi.fn(),
  clearSavedCursorApiKeyMock: vi.fn(),
  fetchCursorModelsMock: vi.fn(),
  ensureProjectIdMock: vi.fn(),
  fetchContextEngineMock: vi.fn(),
  fetchProjectContextEngineMock: vi.fn(),
  fetchSettingsWriteStatusMock: vi.fn(),
  postSettingsApplyMock: vi.fn(),
  postSettingsPreviewMock: vi.fn(),
}));

vi.mock("@/lib/ham/api", () => ({
  fetchCursorCredentialsStatus: () => fetchCursorCredentialsStatusMock(),
  saveCursorApiKey: (...args: unknown[]) => saveCursorApiKeyMock(...args),
  clearSavedCursorApiKey: () => clearSavedCursorApiKeyMock(),
  fetchCursorModels: () => fetchCursorModelsMock(),
  ensureProjectIdForWorkspaceRoot: () => ensureProjectIdMock(),
  fetchContextEngine: () => fetchContextEngineMock(),
  fetchProjectContextEngine: () => fetchProjectContextEngineMock(),
  fetchSettingsWriteStatus: () => fetchSettingsWriteStatusMock(),
  postSettingsApply: (...args: unknown[]) => postSettingsApplyMock(...args),
  postSettingsPreview: (...args: unknown[]) => postSettingsPreviewMock(...args),
}));

vi.mock("@/components/settings/DesktopBundlePanel", () => ({
  DesktopBundlePanel: () => null,
}));

vi.mock("@/features/hermes-workspace/adapters/localRuntime", () => ({
  fetchLocalWorkspaceContextSnapshot: vi.fn(),
  fetchLocalWorkspaceHealth: vi.fn(),
  isLocalRuntimeConfigured: () => false,
}));

vi.mock("@/features/hermes-workspace/lib/contextMemorySnapshotLoadPlan", () => ({
  loadContextMemorySnapshot: vi.fn(),
  shouldGateContextMemorySettingsMutations: () => false,
}));

vi.mock("@/features/hermes-workspace/WorkspaceHamProjectContext", () => ({
  useOptionalWorkspaceHamProject: () => null,
}));

import { ApiKeysPanel } from "@/components/workspace/UnifiedSettings";

const FORBIDDEN_NORMIE_SUBSTRINGS = [
  "CURSOR_API_KEY",
  "HAM_CURSOR_CREDENTIALS_FILE",
  "cursor_credentials.json",
  "/root/.ham",
  "/api/cursor/",
  "Server environment",
  "Key source",
  "What this key is used for",
  "OPENROUTER_API_KEY",
  "HERMES_GATEWAY_MODE",
  "Issued:",
  "crsr_",
  "operator-only-leaked@example.test",
];

function normieResponse(configured: boolean): CursorCredentialsStatus {
  return {
    configured,
    status: configured ? "connected" : "needs_setup",
    account_label: configured ? "Connected" : null,
    diagnostics_visible: false,
  };
}

function operatorResponse(): CursorCredentialsStatus {
  return {
    configured: true,
    diagnostics_visible: true,
    source: "ui",
    masked_preview: "crsr_aaa…zzzz",
    api_key_name: "team-key",
    user_email: "operator-only-leaked@example.test",
    key_created_at: "fake-fixture-timestamp",
    error: null,
    storage_path: "/root/.ham/cursor_credentials.json",
    storage_override_env: null,
    wired_for: {
      models_list: true,
      cloud_agents_launch: true,
      missions_cloud_agent: true,
      ci_hooks: true,
      ci_hooks_note: "ci-hook-note",
      dashboard_chat_uses_cursor: false,
      dashboard_chat_note: "dashboard-chat-note",
    },
  };
}

describe("ApiKeysPanel normie shape", () => {
  beforeEach(() => {
    fetchCursorCredentialsStatusMock.mockReset();
    saveCursorApiKeyMock.mockReset();
    clearSavedCursorApiKeyMock.mockReset();
    fetchCursorModelsMock.mockReset();
  });

  it("does not leak operator details for a connected normie response", async () => {
    fetchCursorCredentialsStatusMock.mockResolvedValue(normieResponse(true));
    render(<ApiKeysPanel variant="workspace" />);

    await waitFor(() => expect(screen.getByText("Cursor Cloud Agent")).toBeInTheDocument());
    expect(
      screen.getByText(/Connected \(managed by your workspace operator\)/i),
    ).toBeInTheDocument();

    const html = document.body.innerHTML;
    for (const needle of FORBIDDEN_NORMIE_SUBSTRINGS) {
      expect(html).not.toContain(needle);
    }
  });

  it("does not leak operator details for an unconfigured normie response", async () => {
    fetchCursorCredentialsStatusMock.mockResolvedValue(normieResponse(false));
    render(<ApiKeysPanel variant="workspace" />);

    await waitFor(() => expect(screen.getByText("Needs setup")).toBeInTheDocument());
    expect(
      screen.getByText(/Contact your workspace operator to connect Cursor\./i),
    ).toBeInTheDocument();

    const html = document.body.innerHTML;
    for (const needle of FORBIDDEN_NORMIE_SUBSTRINGS) {
      expect(html).not.toContain(needle);
    }
  });

  it("does not render Save / Remove / Rotate controls in normie response", async () => {
    fetchCursorCredentialsStatusMock.mockResolvedValue(normieResponse(true));
    render(<ApiKeysPanel variant="workspace" />);

    await waitFor(() => expect(screen.getByText("Cursor Cloud Agent")).toBeInTheDocument());
    expect(screen.queryByRole("button", { name: /save/i })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /remove saved key/i })).not.toBeInTheDocument();
    expect(screen.queryByPlaceholderText(/crsr_/i)).not.toBeInTheDocument();
  });

  it("renders the operator diagnostics drawer collapsed by default", async () => {
    fetchCursorCredentialsStatusMock.mockResolvedValue(operatorResponse());
    render(<ApiKeysPanel variant="workspace" />);

    const summary = await waitFor(() => screen.getByText(/Advanced diagnostics \(operator\)/i));
    expect(summary).toBeInTheDocument();

    const details = summary.closest("details");
    expect(details).not.toBeNull();
    expect(details?.hasAttribute("open")).toBe(false);
  });

  it("does not render diagnostics drawer for normie response", async () => {
    fetchCursorCredentialsStatusMock.mockResolvedValue(normieResponse(true));
    render(<ApiKeysPanel variant="workspace" />);

    await waitFor(() => expect(screen.getByText("Cursor Cloud Agent")).toBeInTheDocument());
    expect(screen.queryByText(/Advanced diagnostics \(operator\)/i)).not.toBeInTheDocument();
  });
});
