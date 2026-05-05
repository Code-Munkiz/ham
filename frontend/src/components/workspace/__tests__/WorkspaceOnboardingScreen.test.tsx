/**
 * Phase 1c: WorkspaceOnboardingScreen smoke tests.
 *
 * Validates field handling, submit gating, and error surfacing.
 */
import { afterEach, describe, expect, it, vi } from "vitest";
import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";

import { WorkspaceOnboardingScreen } from "@/components/workspace/WorkspaceOnboardingScreen";
import {
  HamWorkspaceApiError,
  type HamMeOrg,
  type HamMeUser,
  type HamWorkspaceSummary,
} from "@/lib/ham/workspaceApi";

const baseUser: HamMeUser = {
  user_id: "u_alice",
  email: "alice@example.com",
  display_name: null,
  photo_url: null,
  primary_org_id: null,
};

const adminOrg: HamMeOrg = {
  org_id: "org_a",
  name: "Org A",
  clerk_slug: "org-a",
  org_role: "org:admin",
};

function summary(): HamWorkspaceSummary {
  return {
    workspace_id: "ws_new",
    org_id: null,
    name: "New",
    slug: "new",
    description: "",
    status: "active",
    role: "owner",
    perms: [],
    is_default: false,
    created_at: "x",
    updated_at: "x",
  };
}

afterEach(() => {
  vi.restoreAllMocks();
});

describe("WorkspaceOnboardingScreen", () => {
  it("disables submit until the name is non-empty", () => {
    const onCreate = vi.fn();
    render(
      <WorkspaceOnboardingScreen
        user={baseUser}
        orgs={[]}
        onCreate={onCreate as never}
      />,
    );
    const submit = screen.getByRole("button", { name: /create workspace/i });
    expect(submit).toBeDisabled();
    fireEvent.change(screen.getByLabelText(/name/i), { target: { value: "Hi" } });
    expect(submit).not.toBeDisabled();
  });

  it("calls onCreate with trimmed name", async () => {
    const onCreate = vi.fn().mockResolvedValue(summary());
    render(
      <WorkspaceOnboardingScreen
        user={baseUser}
        orgs={[]}
        onCreate={onCreate}
      />,
    );
    fireEvent.change(screen.getByLabelText(/name/i), { target: { value: "  Solo  " } });
    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: /create workspace/i }));
    });
    expect(onCreate).toHaveBeenCalledWith({ name: "Solo" });
  });

  it("includes org_id when org-scoped toggle is on (admin org present)", async () => {
    const onCreate = vi.fn().mockResolvedValue(summary());
    render(
      <WorkspaceOnboardingScreen
        user={{ ...baseUser, primary_org_id: "org_a" }}
        orgs={[adminOrg]}
        onCreate={onCreate}
      />,
    );
    fireEvent.change(screen.getByLabelText(/name/i), { target: { value: "Atlas" } });
    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: /create workspace/i }));
    });
    expect(onCreate).toHaveBeenCalledWith({ name: "Atlas", org_id: "org_a" });
  });

  it("renders structured API errors inline", async () => {
    const err = new HamWorkspaceApiError(
      409,
      "HAM_WORKSPACE_SLUG_CONFLICT",
      "slug 'solo' is already taken in this scope.",
    );
    const onCreate = vi.fn().mockRejectedValue(err);
    render(
      <WorkspaceOnboardingScreen
        user={baseUser}
        orgs={[]}
        onCreate={onCreate}
      />,
    );
    fireEvent.change(screen.getByLabelText(/name/i), { target: { value: "Solo" } });
    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: /create workspace/i }));
    });
    await waitFor(() => {
      expect(screen.getByRole("alert")).toHaveTextContent(/already taken/i);
    });
  });

  it("offers cancel only when allowDismiss is set", () => {
    const onDismiss = vi.fn();
    const { rerender } = render(
      <WorkspaceOnboardingScreen
        user={baseUser}
        orgs={[]}
        onCreate={vi.fn() as never}
      />,
    );
    expect(screen.queryByRole("button", { name: /cancel/i })).toBeNull();
    rerender(
      <WorkspaceOnboardingScreen
        user={baseUser}
        orgs={[]}
        onCreate={vi.fn() as never}
        onDismiss={onDismiss}
        allowDismiss
      />,
    );
    fireEvent.click(screen.getByRole("button", { name: /cancel/i }));
    expect(onDismiss).toHaveBeenCalled();
  });
});
