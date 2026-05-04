import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { WorkspaceSetupMessage } from "@/components/workspace/WorkspaceSetupMessage";

describe("WorkspaceSetupMessage", () => {
  it("explains local workspace bypass setup", () => {
    render(<WorkspaceSetupMessage />);

    expect(screen.getByText("Workspace setup needed")).toBeInTheDocument();
    expect(
      screen.getByText(
        /HAM could not load a workspace because local workspace bypass is not enabled/i,
      ),
    ).toBeInTheDocument();
    expect(
      screen.getByText(/HAM_LOCAL_DEV_WORKSPACE_BYPASS=true/),
    ).toBeInTheDocument();
  });
});
