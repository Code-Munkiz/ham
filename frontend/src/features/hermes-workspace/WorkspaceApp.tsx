import * as React from "react";
import { Navigate, Route, Routes } from "react-router-dom";
import { isHermesWorkspaceEnabled } from "./workspaceFlags";
import { WorkspaceShell } from "./WorkspaceShell";
import { WorkspaceHome } from "./WorkspaceHome";
import { WorkspaceChat } from "./WorkspaceChat";
import { WorkspacePlaceholderPage } from "./WorkspacePlaceholder";
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
          <Route
            path="files"
            element={
              <WorkspacePlaceholderPage
                title="Files"
                description="Browser-side filesystem and arbitrary paths are out of scope. A future HAM-sandboxed or adapter-driven files surface can land here without PTY in the client."
              />
            }
          />
          <Route
            path="terminal"
            element={
              <WorkspacePlaceholderPage
                title="Terminal"
                description="No raw PTY in the browser. Any terminal experience will be mediated by HAM/server contracts when scoped."
              />
            }
          />
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
