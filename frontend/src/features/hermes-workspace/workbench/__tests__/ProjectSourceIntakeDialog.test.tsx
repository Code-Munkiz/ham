import { describe, expect, it, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";

const fetchWorkspaceToolsMock = vi.fn();
const postChatUploadAttachmentMock = vi.fn();

vi.mock("@/lib/ham/api", async (importOriginal) => {
  const mod = await importOriginal<typeof import("@/lib/ham/api")>();
  return {
    ...mod,
    fetchWorkspaceTools: (...args: unknown[]) => fetchWorkspaceToolsMock(...args),
    postChatUploadAttachment: (...args: unknown[]) => postChatUploadAttachmentMock(...args),
  };
});

vi.mock("../../adapters/localRuntime", () => ({
  isLocalRuntimeConfigured: () => false,
}));

vi.mock("../../adapters/filesAdapter", () => ({
  workspaceFileAdapter: {
    postFormData: vi.fn(),
  },
}));

import {
  ProjectSourceIntakeDialog,
  WORKBENCH_CONNECTED_TOOLS_HREF,
} from "../ProjectSourceIntakeDialog";

function toolsResponse(body: unknown, ok = true) {
  return new Response(JSON.stringify(body), {
    status: ok ? 200 : 500,
    headers: { "Content-Type": "application/json" },
  });
}

describe("ProjectSourceIntakeDialog", () => {
  beforeEach(() => {
    fetchWorkspaceToolsMock.mockResolvedValue(
      toolsResponse({
        tools: [{ id: "github", connection: "off" }],
        scan_available: true,
        scan_hint: null,
      }),
    );
    postChatUploadAttachmentMock.mockReset();
  });

  it("renders when open and links Connected Tools to the real settings route", async () => {
    render(
      <MemoryRouter>
        <ProjectSourceIntakeDialog open onOpenChange={() => {}} />
      </MemoryRouter>,
    );
    expect(screen.getByTestId("hww-project-source-dialog")).toBeInTheDocument();
    const link = await waitFor(() => screen.getByTestId("hww-project-source-connected-tools-link"));
    expect(link).toHaveAttribute("href", WORKBENCH_CONNECTED_TOOLS_HREF);
  });

  it("disables workspace file upload when local runtime is not configured", async () => {
    render(
      <MemoryRouter>
        <ProjectSourceIntakeDialog open onOpenChange={() => {}} />
      </MemoryRouter>,
    );
    expect(await screen.findByTestId("hww-project-source-workspace-upload-btn")).toBeDisabled();
    expect(screen.getByTestId("hww-project-source-connection-link")).toHaveAttribute(
      "href",
      "/workspace/settings?section=connection",
    );
  });

  it("enables chat attachment upload (separate API) when dialog is open", async () => {
    render(
      <MemoryRouter>
        <ProjectSourceIntakeDialog open onOpenChange={() => {}} />
      </MemoryRouter>,
    );
    expect(await screen.findByTestId("hww-project-source-chat-upload-btn")).not.toBeDisabled();
  });

  it("ZIP and repo URL fields are not presented as functional import", async () => {
    render(
      <MemoryRouter>
        <ProjectSourceIntakeDialog open onOpenChange={() => {}} />
      </MemoryRouter>,
    );
    expect(await screen.findByText(/Upload ZIP — Coming soon/i)).toBeInTheDocument();
    expect(screen.getByTestId("hww-project-source-repo-url-input")).toBeDisabled();
  });
});
