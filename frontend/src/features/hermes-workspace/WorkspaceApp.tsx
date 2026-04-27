import * as React from "react";
import { Navigate, Route, Routes } from "react-router-dom";
import { WorkspaceShell } from "./WorkspaceShell";
import { WorkspaceHome } from "./WorkspaceHome";
import { WorkspaceChatScreen } from "./screens/chat";
import { WorkspaceFilesScreen } from "./screens/files/WorkspaceFilesScreen";
import { WorkspaceTerminalScreen } from "./screens/terminal/WorkspaceTerminalScreen";
import { WorkspaceSettingsScreen } from "./screens/settings/WorkspaceSettingsScreen";
import { WorkspaceMcpSettingsScreen } from "./screens/settings/WorkspaceMcpSettingsScreen";
import { WorkspaceJobsScreen } from "./screens/jobs/WorkspaceJobsScreen";
import { WorkspaceTasksScreen } from "./screens/tasks/WorkspaceTasksScreen";
import { WorkspaceConductorScreen } from "./screens/conductor/WorkspaceConductorScreen";
import { WorkspaceMemoryScreen } from "./screens/memory/WorkspaceMemoryScreen";
import { WorkspaceOperationsScreen } from "./screens/operations/WorkspaceOperationsScreen";
import { WorkspaceProfilesScreen } from "./screens/profiles/WorkspaceProfilesScreen";
import { WorkspaceSkillsScreen } from "./screens/skills/WorkspaceSkillsScreen";
import "./hermesWorkspace.css";

/**
 * Hermes Workspace surface (`/workspace/*`). Not gated on `VITE_ENABLE_HERMES_WORKSPACE` (routing);
 * that flag is only for non-route toggles.
 * @see docs/WHOLE_HERMES_WORKSPACE_LIFT_PLAN.md
 */
export function WorkspaceApp() {
  return (
    <div className="hww-outer h-full min-h-0 w-full min-w-0">
      <WorkspaceShell>
        <Routes>
          <Route index element={<WorkspaceHome />} />
          <Route path="chat" element={<WorkspaceChatScreen />} />
          <Route path="files" element={<WorkspaceFilesScreen />} />
          <Route path="terminal" element={<WorkspaceTerminalScreen />} />
          <Route path="settings/mcp" element={<WorkspaceMcpSettingsScreen />} />
          <Route
            path="settings/providers"
            element={<Navigate to="/workspace/settings?section=hermes" replace />}
          />
          <Route path="settings" element={<WorkspaceSettingsScreen />} />
          <Route path="jobs" element={<WorkspaceJobsScreen />} />
          <Route path="tasks" element={<WorkspaceTasksScreen />} />
          <Route path="conductor" element={<WorkspaceConductorScreen />} />
          <Route path="operations" element={<WorkspaceOperationsScreen />} />
          <Route path="memory" element={<WorkspaceMemoryScreen />} />
          <Route path="skills" element={<WorkspaceSkillsScreen />} />
          <Route path="profiles" element={<WorkspaceProfilesScreen />} />
        </Routes>
      </WorkspaceShell>
    </div>
  );
}
