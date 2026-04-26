/**
 * @license
 * SPDX-License-Identifier: Apache-2.0
 */

import { BrowserRouter, HashRouter, Routes, Route, Navigate, useLocation } from "react-router-dom";
import { ClerkProvider } from "@clerk/clerk-react";
import { ThemeProvider } from "next-themes";
import { AppLayout } from "./components/layout/AppLayout";
import Chat from "./pages/Chat";
import Extensions from "./pages/Extensions";
import Runs from "./pages/Runs";
import RunDetail from "./pages/RunDetail";
import ControlPlaneRuns from "./pages/ControlPlaneRuns";
import Storage from "./pages/Storage";
import Activity from "./pages/Activity";
import Settings from "./pages/Settings";

import Logs from "./pages/Logs";
import Analytics from "./pages/Analytics";
import HermesHub from "./pages/HermesHub";
import CommandCenter from "./pages/CommandCenter";
import HermesSkills from "./pages/HermesSkills";
import HamShop from "./pages/HamShop";
import AgentBuilder from "./pages/AgentBuilder";
import Landing from "./pages/Landing";

import { AgentProvider } from "./lib/ham/AgentContext";
import { WorkspaceProvider } from "./lib/ham/WorkspaceContext";
import { ClerkAccessBridge } from "./lib/ham/ClerkAccessBridge";
import { getHamDesktopConfig, isHamDesktopShell } from "./lib/ham/desktopConfig";
import { WorkspaceApp } from "./features/hermes-workspace";
import { isHermesWorkspaceEnabled } from "./features/hermes-workspace/workspaceFlags";

const clerkPublishableKey = (import.meta.env.VITE_CLERK_PUBLISHABLE_KEY as string | undefined)?.trim();

/** Web: marketing landing. Desktop shell: go straight to chat (no landing hero). */
function HomeRoute() {
  if (isHamDesktopShell()) {
    return <Navigate to="/chat" replace />;
  }
  return <Landing />;
}

/** When Hermes workspace is enabled, primary chat lives under `/workspace/chat`; keep `/chat` as entry alias. */
function ChatEntryRoute() {
  const { search } = useLocation();
  if (isHermesWorkspaceEnabled()) {
    return <Navigate to={`/workspace/chat${search}`} replace />;
  }
  return <Chat />;
}

function AppRoutes() {
  const useHash = getHamDesktopConfig()?.useHashRouter === true;
  const Router = useHash ? HashRouter : BrowserRouter;
  return (
    <Router>
      <AppLayout>
        <Routes>
          <Route path="/" element={<HomeRoute />} />
          {/* Legacy path: product stream lives on Activity, not a separate Overview page. */}
          <Route path="/overview" element={<Navigate to="/activity" replace />} />
          <Route path="/chat" element={<ChatEntryRoute />} />
          <Route path="/workspace/*" element={<WorkspaceApp />} />
          <Route path="/droids" element={<Navigate to="/command-center" replace />} />
          <Route path="/extensions" element={<Extensions />} />
          <Route path="/runs" element={<Runs />} />
          <Route path="/runs/:runId" element={<RunDetail />} />
          <Route path="/control-plane" element={<ControlPlaneRuns />} />
          <Route path="/profiles" element={<Navigate to="/agents" replace />} />
          <Route path="/storage" element={<Storage />} />
          <Route path="/activity" element={<Activity />} />
          <Route path="/settings" element={<Settings />} />
          <Route path="/logs" element={<Logs />} />
          <Route path="/analytics" element={<Analytics />} />
          <Route path="/hermes" element={<HermesHub />} />
          <Route path="/command-center" element={<CommandCenter />} />
          <Route path="/shop" element={<HamShop />} />
          <Route path="/skills" element={<HermesSkills />} />
          <Route path="/agents" element={<AgentBuilder />} />
          <Route path="/hermes-skills" element={<Navigate to="/skills" replace />} />
        </Routes>
      </AppLayout>
    </Router>
  );
}

export default function App() {
  const tree = (
    // @ts-ignore - ThemeProvider children type mismatch in some versions of next-themes with React 18/19
    <ThemeProvider attribute="class" defaultTheme="light" enableSystem={false}>
      <AgentProvider>
        <WorkspaceProvider>
          <AppRoutes />
        </WorkspaceProvider>
      </AgentProvider>
    </ThemeProvider>
  );
  if (clerkPublishableKey) {
    return (
      <ClerkProvider publishableKey={clerkPublishableKey}>
        <ClerkAccessBridge>{tree}</ClerkAccessBridge>
      </ClerkProvider>
    );
  }
  return tree;
}

