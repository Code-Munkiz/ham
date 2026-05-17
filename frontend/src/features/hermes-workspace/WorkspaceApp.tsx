import * as React from "react";
import { Navigate, Route, Routes, useLocation } from "react-router-dom";
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
import { WorkspaceCodingAgentsScreen } from "./screens/coding-agents/WorkspaceCodingAgentsScreen";
import { BuilderStudioScreen } from "./screens/builder-studio";
import { WorkspaceProfilesScreen } from "./screens/profiles/WorkspaceProfilesScreen";
import { WorkspaceSkillsScreen } from "./screens/skills/WorkspaceSkillsScreen";
import { WorkspaceSocialScreen } from "./screens/social/WorkspaceSocialScreen";
import { WorkspaceSocialPolicyScreen } from "./screens/social/policy/WorkspaceSocialPolicyScreen";
import "./hermesWorkspace.css";
import { VoiceWorkspaceSettingsProvider } from "./voice/VoiceWorkspaceSettingsContext";
import { WorkspaceHamProjectProvider } from "./WorkspaceHamProjectContext";
import { WorkspaceGate } from "@/components/workspace/WorkspaceGate";

function WorkspaceChatFirstIndex() {
  const { search } = useLocation();
  return <Navigate to={`/workspace/chat${search}`} replace />;
}

/**
 * Hermes Workspace surface (`/workspace/*`). Not gated on `VITE_ENABLE_HERMES_WORKSPACE` (routing);
 * that flag is only for non-route toggles. `/legacy-chat` redirects to `/workspace/chat`.
 * @see docs/WHOLE_HERMES_WORKSPACE_LIFT_PLAN.md
 */
export function WorkspaceApp() {
  return (
    <WorkspaceHamProjectProvider>
      <VoiceWorkspaceSettingsProvider>
        <div className="hww-outer h-full min-h-0 w-full min-w-0">
          <WorkspaceShell>
            <WorkspaceGate>
              <Routes>
                <Route index element={<WorkspaceChatFirstIndex />} />
                <Route path="projects" element={<WorkspaceHome />} />
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
                <Route path="coding-agents" element={<WorkspaceCodingAgentsScreen />} />
                <Route path="builder-studio" element={<BuilderStudioScreen />} />
                <Route path="builder-studio/:builderId" element={<BuilderStudioScreen />} />
                <Route path="social/policy" element={<WorkspaceSocialPolicyScreen />} />
                <Route path="social" element={<WorkspaceSocialScreen />} />
                <Route path="memory" element={<WorkspaceMemoryScreen />} />
                <Route path="skills" element={<WorkspaceSkillsScreen />} />
                <Route path="profiles" element={<WorkspaceProfilesScreen />} />
              </Routes>
            </WorkspaceGate>
          </WorkspaceShell>
        </div>
      </VoiceWorkspaceSettingsProvider>
    </WorkspaceHamProjectProvider>
  );
}
