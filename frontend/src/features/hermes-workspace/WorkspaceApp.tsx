import * as React from "react";
import { Navigate, Route, Routes } from "react-router-dom";
import { isHermesWorkspaceEnabled } from "./workspaceFlags";
import { WorkspaceShell } from "./WorkspaceShell";
import { WorkspaceHome } from "./WorkspaceHome";
import { WorkspaceChat } from "./WorkspaceChat";
import { WorkspacePlaceholderPage } from "./WorkspacePlaceholder";
import { WorkspaceFilesScreen } from "./screens/files/WorkspaceFilesScreen";
import { WorkspaceTerminalScreen } from "./screens/terminal/WorkspaceTerminalScreen";
import { WorkspaceSettingsScreen } from "./screens/settings/WorkspaceSettingsScreen";
import { WorkspaceJobsScreen } from "./screens/jobs/WorkspaceJobsScreen";
import { WorkspaceTasksScreen } from "./screens/tasks/WorkspaceTasksScreen";
import { WorkspaceConductorScreen } from "./screens/conductor/WorkspaceConductorScreen";
import { WorkspaceOperationsScreen } from "./screens/operations/WorkspaceOperationsScreen";
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
          <Route path="files" element={<WorkspaceFilesScreen />} />
          <Route path="terminal" element={<WorkspaceTerminalScreen />} />
          <Route path="settings" element={<WorkspaceSettingsScreen />} />
          <Route path="jobs" element={<WorkspaceJobsScreen />} />
          <Route path="tasks" element={<WorkspaceTasksScreen />} />
          <Route path="conductor" element={<WorkspaceConductorScreen />} />
          <Route path="operations" element={<WorkspaceOperationsScreen />} />
          <Route
            path="memory"
            element={
              <WorkspacePlaceholderPage
                title="Memory"
                description="Memory Heist and long-lived recall stay on HAM server contracts. This page is a shell until the memory adapter is wired."
              />
            }
          />
          <Route
            path="skills"
            element={
              <WorkspacePlaceholderPage
                title="Skills"
                description="Hermes/HAM skills catalogs can surface here through existing API seams — not wired in this slice."
              />
            }
          />
          <Route
            path="profiles"
            element={
              <WorkspacePlaceholderPage
                title="Profiles"
                description="Agent profiles and Agent Builder data can bind here later — display-only shell for now."
              />
            }
          />
        </Routes>
      </WorkspaceShell>
    </div>
  );
}
