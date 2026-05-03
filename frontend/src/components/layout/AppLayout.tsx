import * as React from "react";
import { Toaster } from "sonner";
import { useLocation } from "react-router-dom";

import { useHamDeploymentAccess } from "@/lib/ham/ClerkAccessBridge";
import { HamDeploymentRestrictedBanner } from "./HamDeploymentRestrictedBanner";
import { HamWorkspaceTopbarPill } from "./HamWorkspaceTopbarPill";
import { isHamDesktopShell } from "@/lib/ham/desktopConfig";

/**
 * Layout: web `/` marketing landing (no chrome); all other routes use full-bleed canvas.
 * Legacy NavRail/Header/workbench shell removed — workspace owns in-app IA.
 */
export function AppLayout({ children }: { children: React.ReactNode }) {
  const location = useLocation();
  const { restricted: hamDeploymentRestricted } = useHamDeploymentAccess();

  const isBareLanding = location.pathname === "/";

  // Web marketing landing only — desktop shell redirects `/` → workspace chat and never shows this layout.
  if (isBareLanding && !isHamDesktopShell()) {
    return (
      <>
        <HamDeploymentRestrictedBanner show={hamDeploymentRestricted} />
        {children}
        <Toaster theme="dark" position="bottom-right" closeButton richColors />
      </>
    );
  }

  return (
    <div className="h-screen w-screen overflow-hidden bg-[#030b11] text-foreground transition-colors duration-300 relative font-sans">
      <HamDeploymentRestrictedBanner show={hamDeploymentRestricted} />
      <div className="pointer-events-none absolute right-3 top-3 z-40">
        <HamWorkspaceTopbarPill />
      </div>
      <div className="h-full w-full min-h-0 min-w-0 overflow-hidden">{children}</div>
      <Toaster theme="dark" position="bottom-right" closeButton richColors />
    </div>
  );
}
