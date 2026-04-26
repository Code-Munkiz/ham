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
          <Route
            path="jobs"
            element={
              <WorkspacePlaceholderPage
                title="Jobs"
                description="Placeholder for job-style workloads. Can align with HAM runs or Cloud Agent missions via adapters in a later slice."
              />
            }
          />
          <Route
            path="tasks"
            element={
              <WorkspacePlaceholderPage
                title="Tasks"
                description="Task lists and Conductor-style flows — UI shell only; wiring deferred."
              />
            }
          />
          <Route
            path="conductor"
            element={
              <WorkspacePlaceholderPage
                title="Conductor"
                description="Orchestration UI placeholder — no direct upstream Hermes or OpenAI calls from the client."
              />
            }
          />
          <Route
            path="operations"
            element={
              <WorkspacePlaceholderPage
                title="Operations"
                description="Operations / health-style views — can consume existing HAM APIs when modeled."
              />
            }
          />
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
