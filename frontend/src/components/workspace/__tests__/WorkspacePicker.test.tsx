/**
 * Phase 1c: WorkspacePicker dropdown smoke tests.
 *
 * Pure React component — no provider needed since it takes its data via
 * props.
 */
import { afterEach, describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";

import { WorkspacePicker } from "@/components/workspace/WorkspacePicker";
import type { HamWorkspaceSummary } from "@/lib/ham/workspaceApi";

function summary(overrides: Partial<HamWorkspaceSummary> = {}): HamWorkspaceSummary {
  return {
    workspace_id: "ws_a",
    org_id: null,
    name: "Alpha",
    slug: "alpha",
    description: "",
    status: "active",
    role: "owner",
    perms: [],
    is_default: false,
    created_at: "x",
    updated_at: "x",
    ...overrides,
  };
}

afterEach(() => {
  vi.restoreAllMocks();
});

describe("WorkspacePicker", () => {
  it("returns nothing when closed", () => {
    const { queryByTestId } = render(
      <WorkspacePicker
        workspaces={[]}
        activeWorkspaceId={null}
        open={false}
        onSelect={() => {}}
        onCreate={() => {}}
        onClose={() => {}}
      />,
    );
    expect(queryByTestId("workspace-picker")).toBeNull();
  });

  it("shows active workspaces with role badges", () => {
    const ws_a = summary({ workspace_id: "ws_a", name: "Alpha", role: "owner" });
    const ws_b = summary({ workspace_id: "ws_b", name: "Beta", role: "member" });
    render(
      <WorkspacePicker
        workspaces={[ws_a, ws_b]}
        activeWorkspaceId="ws_a"
        open
        onSelect={() => {}}
        onCreate={() => {}}
        onClose={() => {}}
      />,
    );
    expect(screen.getByText("Alpha")).toBeInTheDocument();
    expect(screen.getByText("Beta")).toBeInTheDocument();
    const owner = screen.getByText("owner");
    expect(owner).toBeInTheDocument();
  });

  it("hides archived workspaces", () => {
    const ws_a = summary({ workspace_id: "ws_a", name: "Alpha" });
    const ws_b = summary({ workspace_id: "ws_b", name: "Beta", status: "archived" });
    render(
      <WorkspacePicker
        workspaces={[ws_a, ws_b]}
        activeWorkspaceId="ws_a"
        open
        onSelect={() => {}}
        onCreate={() => {}}
        onClose={() => {}}
      />,
    );
    expect(screen.queryByText("Beta")).toBeNull();
  });

  it("calls onSelect and onClose when an item is clicked", () => {
    const onSelect = vi.fn();
    const onClose = vi.fn();
    const ws_b = summary({ workspace_id: "ws_b", name: "Beta", role: "member" });
    render(
      <WorkspacePicker
        workspaces={[summary(), ws_b]}
        activeWorkspaceId="ws_a"
        open
        onSelect={onSelect}
        onCreate={() => {}}
        onClose={onClose}
      />,
    );
    fireEvent.click(screen.getByText("Beta"));
    expect(onSelect).toHaveBeenCalledWith("ws_b");
    expect(onClose).toHaveBeenCalled();
  });

  it("calls onCreate from the footer item", () => {
    const onCreate = vi.fn();
    const onClose = vi.fn();
    render(
      <WorkspacePicker
        workspaces={[summary()]}
        activeWorkspaceId="ws_a"
        open
        onSelect={() => {}}
        onCreate={onCreate}
        onClose={onClose}
      />,
    );
    fireEvent.click(screen.getByTestId("workspace-picker-create"));
    expect(onCreate).toHaveBeenCalled();
    expect(onClose).toHaveBeenCalled();
  });

  it("closes on Escape", () => {
    const onClose = vi.fn();
    render(
      <WorkspacePicker
        workspaces={[summary()]}
        activeWorkspaceId="ws_a"
        open
        onSelect={() => {}}
        onCreate={() => {}}
        onClose={onClose}
      />,
    );
    fireEvent.keyDown(document, { key: "Escape" });
    expect(onClose).toHaveBeenCalled();
  });
});
