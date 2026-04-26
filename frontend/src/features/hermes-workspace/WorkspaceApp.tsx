import * as React from "react";
import { Navigate, Route, Routes } from "react-router-dom";
import { isHermesWorkspaceEnabled } from "./workspaceFlags";
import { WorkspaceShell } from "./WorkspaceShell";
import { WorkspaceHome } from "./WorkspaceHome";
import { WorkspaceChat } from "./WorkspaceChat";
import "./hermesWorkspace.css";

/**
 * Feature-flagged namespaced app for the Hermes Workspace UI lift.
 * @see docs/WHOLE_HERMES_WORKSPACE_LIFT_PLAN.md
 */
export function WorkspaceApp() {
  if (!isHermesWorkspaceEnabled()) {
    return <Navigate to="/chat" replace />;
  }

  return (
    <div className="hww-outer h-full min-h-0 w-full min-w-0">
      <WorkspaceShell>
        <Routes>
          <Route index element={<WorkspaceHome />} />
          <Route path="chat" element={<WorkspaceChat />} />
        </Routes>
      </WorkspaceShell>
    </div>
  );
}
