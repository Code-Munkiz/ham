import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { WorkspaceSetupMessage } from "@/components/workspace/WorkspaceSetupMessage";

describe("WorkspaceSetupMessage", () => {
  it("shows hosted-safe workspace unavailable copy by default", () => {
    render(<WorkspaceSetupMessage />);

    expect(screen.getByText("Workspace unavailable")).toBeInTheDocument();
    expect(
      screen.getByText(
        /HAM could not load your workspace\. Sign in again or contact your workspace admin\./i,
      ),
    ).toBeInTheDocument();
    expect(screen.queryByText(/HAM_LOCAL_DEV_WORKSPACE_BYPASS=true/)).not.toBeInTheDocument();
    expect(screen.queryByText(/python3 scripts\/run_local_api\.py/)).not.toBeInTheDocument();
  });

  it("shows sign-in-required copy and actions", () => {
    const onRetry = vi.fn();
    const onSignIn = vi.fn();
    render(
      <WorkspaceSetupMessage
        mode="auth_required"
        onRetry={onRetry}
        onSignIn={onSignIn}
      />,
    );

    expect(screen.getByText("Sign in required")).toBeInTheDocument();
    expect(
      screen.getByText("Please sign in to load your HAM workspace."),
    ).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Sign in" }));
    fireEvent.click(screen.getByRole("button", { name: "Refresh" }));
    expect(onSignIn).toHaveBeenCalledTimes(1);
    expect(onRetry).toHaveBeenCalledTimes(1);
  });

  it("shows auth-not-configured copy without a dead sign-in button", () => {
    const onRetry = vi.fn();
    render(<WorkspaceSetupMessage mode="auth_not_configured" onRetry={onRetry} />);

    expect(screen.getByText("Authentication is not configured")).toBeInTheDocument();
    expect(
      screen.getByText("Set VITE_CLERK_PUBLISHABLE_KEY and redeploy."),
    ).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Sign in" })).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Refresh" }));
    expect(onRetry).toHaveBeenCalledTimes(1);
  });

  it("omits sign-in action when auth is required but no sign-in handler is provided", () => {
    render(<WorkspaceSetupMessage mode="auth_required" />);

    expect(screen.getByText("Sign in required")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Sign in" })).not.toBeInTheDocument();
  });

  it("shows local-only developer hint only when explicitly enabled", () => {
    render(<WorkspaceSetupMessage showDeveloperHint />);

    expect(screen.getByText("Developer setup (local-only)")).toBeInTheDocument();
    expect(screen.getByText(/HAM_LOCAL_DEV_WORKSPACE_BYPASS=true/)).toBeInTheDocument();
  });
});
