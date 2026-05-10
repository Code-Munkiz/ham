import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import {
  buildLocalDevWorkspaceMeResponse,
  isLocalWorkspaceBypassHostnameAllowed,
  localWorkspaceBypassEligible,
  LOCAL_UI_QA_WORKSPACE_ID,
  shouldActivateLocalWorkspaceUiBypass,
} from "@/lib/ham/localDevWorkspaceBypass";

describe("localDevWorkspaceBypass", () => {
  const fixedTs = "2026-05-03T12:00:00.000Z";

  describe("localWorkspaceBypassEligible", () => {
    it("is false when not in dev mode", () => {
      expect(
        localWorkspaceBypassEligible({
          dev: false,
          prod: false,
          viteFlag: "true",
          hostname: "localhost",
        }),
      ).toBe(false);
    });

    it("is false when production bundle (prod=true)", () => {
      expect(
        localWorkspaceBypassEligible({
          dev: true,
          prod: true,
          viteFlag: "true",
          hostname: "localhost",
        }),
      ).toBe(false);
    });

    it("is false when Vite flag unset", () => {
      expect(
        localWorkspaceBypassEligible({
          dev: true,
          prod: false,
          viteFlag: undefined,
          hostname: "localhost",
        }),
      ).toBe(false);
    });

    it("is false on non-loopback hostname", () => {
      expect(
        localWorkspaceBypassEligible({
          dev: true,
          prod: false,
          viteFlag: "true",
          hostname: "ham-nine-mu.vercel.app",
        }),
      ).toBe(false);
    });

    it("is true with dev + no prod + flag + loopback", () => {
      expect(
        localWorkspaceBypassEligible({
          dev: true,
          prod: false,
          viteFlag: "true",
          hostname: "127.0.0.1",
        }),
      ).toBe(true);
    });
  });

  describe("hostname allow-list", () => {
    it("allows standard loopback names", () => {
      expect(isLocalWorkspaceBypassHostnameAllowed("localhost")).toBe(true);
      expect(isLocalWorkspaceBypassHostnameAllowed("127.0.0.1")).toBe(true);
      expect(isLocalWorkspaceBypassHostnameAllowed("::1")).toBe(true);
    });

    it("rejects LAN / production-ish hosts", () => {
      expect(isLocalWorkspaceBypassHostnameAllowed("192.168.1.10")).toBe(false);
      expect(isLocalWorkspaceBypassHostnameAllowed("evil.test")).toBe(false);
    });
  });

  describe("shouldActivateLocalWorkspaceUiBypass (vite flag stubbed)", () => {
    beforeEach(() => {
      vi.stubEnv("VITE_HAM_LOCAL_DEV_WORKSPACE_BYPASS", "true");
    });
    afterEach(() => {
      vi.unstubAllEnvs();
    });

    it("yields false when Clerk user is actively signed in", () => {
      expect(
        shouldActivateLocalWorkspaceUiBypass(
          { clerkConfigured: true, isSignedIn: true },
          "localhost",
        ),
      ).toBe(false);
    });

    it("allows when Clerk is wired but signed out under loopback host", () => {
      expect(
        shouldActivateLocalWorkspaceUiBypass(
          { clerkConfigured: true, isSignedIn: false },
          "localhost",
        ),
      ).toBe(true);
    });

    it("allows when Clerk is not configured", () => {
      expect(
        shouldActivateLocalWorkspaceUiBypass(
          { clerkConfigured: false, isSignedIn: false },
          "localhost",
        ),
      ).toBe(true);
    });
  });

  describe("mock me payload safety", () => {
    it("buildLocalDevWorkspaceMeResponse does not expose email or tokens", () => {
      const me = buildLocalDevWorkspaceMeResponse(fixedTs);
      expect(me.user.user_id).toBe("dev-local-user");
      expect(me.user.email).toBeNull();
      expect(me.auth_mode).toBe("local_dev_bypass");
      expect(me.workspaces[0]?.workspace_id).toBe(LOCAL_UI_QA_WORKSPACE_ID);
      expect(me.workspaces[0]?.name).toBe("ham repo");
      expect(me.workspaces[0]?.slug).toBe("ham-repo");
    });
  });
});
