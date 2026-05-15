/**
 * @license
 * SPDX-License-Identifier: Apache-2.0
 */

import { BrowserRouter, HashRouter, Routes, Route, Navigate, useLocation } from "react-router-dom";
import { ClerkProvider, useAuth, useClerk } from "@clerk/clerk-react";
import * as React from "react";
import { ThemeProvider } from "next-themes";
import { AppLayout } from "./components/layout/AppLayout";
import Landing from "./pages/Landing";

import { AgentProvider } from "./lib/ham/AgentContext";
import { WorkspaceProvider } from "./lib/ham/WorkspaceContext";
import { HamWorkspaceProvider, useHamWorkspace } from "./lib/ham/HamWorkspaceContext";
import { ClerkAccessBridge } from "./lib/ham/ClerkAccessBridge";
import { getHamDesktopConfig, isHamDesktopShell } from "./lib/ham/desktopConfig";
import { WorkspaceApp } from "./features/hermes-workspace";
import { primaryChatPath } from "./features/hermes-workspace/workspaceFlags";

const clerkPublishableKey = (
  import.meta.env.VITE_CLERK_PUBLISHABLE_KEY as string | undefined
)?.trim();

/** Web: marketing landing. Desktop shell: go straight to chat (no landing hero). */
function HomeRoute() {
  if (isHamDesktopShell()) {
    return <Navigate to={primaryChatPath()} replace />;
  }
  return <Landing />;
}

function LegacyChatRedirect() {
  const { search } = useLocation();
  return <Navigate to={`/workspace/chat${search}`} replace />;
}

function LegacySettingsRedirect() {
  const { search } = useLocation();
  return <Navigate to={`/workspace/settings${search}`} replace />;
}

/** Preserve query (e.g. `project_id`) when moving bookmarked URLs to workspace. */
function RedirectWithSearch({ to }: { to: string }) {
  const { search } = useLocation();
  return <Navigate to={`${to}${search}`} replace />;
}

function SignInRecoveryRoute() {
  const { hostedAuth, openSignIn, state } = useHamWorkspace();
  React.useEffect(() => {
    if (hostedAuth?.clerkConfigured && openSignIn && state.status !== "ready") {
      openSignIn();
    }
  }, [hostedAuth, openSignIn, state.status]);

  if (!hostedAuth?.clerkConfigured) {
    return <Navigate to="/workspace/chat" replace />;
  }
  if (state.status === "ready") {
    return <Navigate to="/workspace/chat" replace />;
  }
  return (
    <div className="mx-auto my-12 max-w-md rounded-xl border border-white/15 bg-black/30 p-6 text-white">
      <h1 className="text-sm font-semibold">Sign in required</h1>
      <p className="mt-2 text-sm text-white/80">
        Continue to the workspace by signing in.
      </p>
      <div className="mt-4 flex gap-2">
        <button
          type="button"
          onClick={() => openSignIn?.()}
          className="rounded-lg border border-sky-300/25 bg-sky-400/20 px-3 py-1.5 text-xs font-semibold text-sky-50 transition hover:bg-sky-400/30"
        >
          Sign in
        </button>
        <button
          type="button"
          onClick={() => window.location.assign("/workspace/chat")}
          className="rounded-lg border border-white/14 bg-white/10 px-3 py-1.5 text-xs font-semibold text-white transition hover:bg-white/[0.15]"
        >
          Back to workspace
        </button>
      </div>
    </div>
  );
}

function AppRoutes() {
  const useHash = getHamDesktopConfig()?.useHashRouter === true;
  const Router = useHash ? HashRouter : BrowserRouter;
  return (
    <Router>
      <AppLayout>
        <Routes>
          <Route path="/" element={<HomeRoute />} />
          <Route path="/overview" element={<Navigate to="/workspace/operations" replace />} />
          <Route path="/chat" element={<Navigate to="/workspace/chat" replace />} />
          <Route path="/sign-in" element={<SignInRecoveryRoute />} />
          <Route path="/legacy-chat" element={<LegacyChatRedirect />} />
          <Route path="/workspace/*" element={<WorkspaceApp />} />
          <Route path="/droids" element={<Navigate to="/workspace/operations" replace />} />
          <Route path="/runs" element={<Navigate to="/workspace/jobs" replace />} />
          <Route path="/runs/:runId" element={<Navigate to="/workspace/jobs" replace />} />
          <Route path="/control-plane" element={<Navigate to="/workspace/operations" replace />} />
          <Route path="/profiles" element={<Navigate to="/workspace/profiles" replace />} />
          <Route path="/storage" element={<Navigate to="/workspace" replace />} />
          <Route path="/activity" element={<Navigate to="/workspace/operations" replace />} />
          <Route path="/settings" element={<LegacySettingsRedirect />} />
          <Route path="/logs" element={<Navigate to="/workspace/settings" replace />} />
          <Route path="/analytics" element={<Navigate to="/workspace" replace />} />
          <Route path="/hermes" element={<Navigate to="/workspace" replace />} />
          <Route path="/command-center" element={<Navigate to="/workspace/operations" replace />} />
          <Route path="/shop" element={<RedirectWithSearch to="/workspace/skills" />} />
          <Route path="/skills" element={<RedirectWithSearch to="/workspace/skills" />} />
          <Route path="/agents" element={<RedirectWithSearch to="/workspace/profiles" />} />
          <Route path="/hermes-skills" element={<Navigate to="/workspace/skills" replace />} />
        </Routes>
      </AppLayout>
    </Router>
  );
}

function AppProviders({
  children,
  hostedAuth,
  openSignIn,
}: {
  children: React.ReactNode;
  hostedAuth: {
    clerkConfigured: boolean;
    isLoaded: boolean;
    isSignedIn: boolean;
  } | null;
  openSignIn?: () => void;
}) {
  return (
    // @ts-ignore - ThemeProvider children type mismatch in some versions of next-themes with React 18/19
    <ThemeProvider attribute="class" defaultTheme="light" enableSystem={false}>
      <AgentProvider>
        <WorkspaceProvider>
          <HamWorkspaceProvider hostedAuth={hostedAuth} openSignIn={openSignIn}>
            {children}
          </HamWorkspaceProvider>
        </WorkspaceProvider>
      </AgentProvider>
    </ThemeProvider>
  );
}

function ClerkHostedApp() {
  const { isLoaded, isSignedIn } = useAuth();
  const clerk = useClerk();
  const openSignIn = React.useCallback(() => {
    void clerk.openSignIn();
  }, [clerk]);
  const hostedAuth = React.useMemo(
    () => ({
      clerkConfigured: true,
      isLoaded,
      isSignedIn: Boolean(isSignedIn),
    }),
    [isLoaded, isSignedIn],
  );
  return (
    <ClerkAccessBridge>
      <AppProviders hostedAuth={hostedAuth} openSignIn={openSignIn}>
        <AppRoutes />
      </AppProviders>
    </ClerkAccessBridge>
  );
}

export default function App() {
  if (clerkPublishableKey) {
    return (
      <ClerkProvider publishableKey={clerkPublishableKey}>
        <ClerkHostedApp />
      </ClerkProvider>
    );
  }
  return (
    <AppProviders
      hostedAuth={{
        clerkConfigured: false,
        isLoaded: true,
        isSignedIn: false,
      }}
    >
      <AppRoutes />
    </AppProviders>
  );
}
