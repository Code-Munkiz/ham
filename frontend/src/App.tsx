/**
 * @license
 * SPDX-License-Identifier: Apache-2.0
 */

import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";
import { ThemeProvider } from "next-themes";
import { AppLayout } from "./components/layout/AppLayout";
import Overview from "./pages/Overview";
import Droids from "./pages/Droids";
import Chat from "./pages/Chat";
import Extensions from "./pages/Extensions";
import Runs from "./pages/Runs";
import RunDetail from "./pages/RunDetail";
import Profiles from "./pages/Profiles";
import Storage from "./pages/Storage";
import Activity from "./pages/Activity";
import Settings from "./pages/Settings";

import Logs from "./pages/Logs";
import Analytics from "./pages/Analytics";
import HermesSkills from "./pages/HermesSkills";

import { AgentProvider } from "./lib/ham/AgentContext";
import { WorkspaceProvider } from "./lib/ham/WorkspaceContext";

export default function App() {
  return (
    // @ts-ignore - ThemeProvider children type mismatch in some versions of next-themes with React 18/19
    <ThemeProvider attribute="class" defaultTheme="light" enableSystem={false}>
      <AgentProvider>
        <WorkspaceProvider>
          <BrowserRouter>
            <AppLayout>
              <Routes>
                <Route path="/" element={<Overview />} />
                <Route path="/chat" element={<Chat />} />
                <Route path="/droids" element={<Droids />} />
                <Route path="/extensions" element={<Extensions />} />
                <Route path="/runs" element={<Runs />} />
                <Route path="/runs/:runId" element={<RunDetail />} />
                <Route path="/profiles" element={<Profiles />} />
                <Route path="/storage" element={<Storage />} />
                <Route path="/activity" element={<Activity />} />
                <Route path="/settings" element={<Settings />} />
                <Route path="/logs" element={<Logs />} />
                <Route path="/analytics" element={<Analytics />} />
                <Route path="/skills" element={<HermesSkills />} />
                <Route path="/hermes-skills" element={<Navigate to="/skills" replace />} />
              </Routes>
            </AppLayout>
          </BrowserRouter>
        </WorkspaceProvider>
      </AgentProvider>
    </ThemeProvider>
  );
}

