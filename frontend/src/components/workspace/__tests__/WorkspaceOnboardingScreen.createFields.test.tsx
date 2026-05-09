import { render, screen, fireEvent } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";

import { WorkspaceOnboardingScreen } from "../WorkspaceOnboardingScreen";

describe("WorkspaceOnboardingScreen extended create fields", () => {
  it("disables Create when workspace name is empty", () => {
    const onCreate = vi.fn();
    render(
      <MemoryRouter>
        <WorkspaceOnboardingScreen
          user={{
            user_id: "u1",
            email: "a@b.com",
            display_name: null,
            photo_url: null,
            primary_org_id: null,
          }}
          orgs={[]}
          onCreate={onCreate}
          variant="dialog"
          allowDismiss
          onDismiss={() => {}}
          showInstructionsField
          showConnectedToolsHint
        />
        ,
      </MemoryRouter>,
    );

    const submit = screen.getByRole("button", { name: /create workspace/i });
    expect(submit).toBeDisabled();

    fireEvent.change(screen.getByLabelText(/workspace name/i), { target: { value: "Acme" } });
    expect(submit).not.toBeDisabled();
    expect(screen.getByTestId("ham-workspace-connected-tools-hint")).toBeInTheDocument();
  });
});
