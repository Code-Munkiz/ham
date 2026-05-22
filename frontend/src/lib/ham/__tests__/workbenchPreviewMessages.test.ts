import { describe, expect, it } from "vitest";
import {
  buildPreviewPrimaryState,
  previewPhaseUserLabel,
  previewUserCopyLooksSafe,
  sanitizePreviewDetailsStatus,
  sanitizePreviewFetchError,
  sanitizePreviewStateError,
} from "@/lib/ham/workbenchPreviewMessages";

describe("workbenchPreviewMessages", () => {
  it("maps preview phases to normie-friendly pill labels", () => {
    expect(previewPhaseUserLabel("no_project")).toBe("No project");
    expect(previewPhaseUserLabel("preparing")).toBe("Preparing");
    expect(previewPhaseUserLabel("source_ready")).toBe("Almost ready");
    expect(previewPhaseUserLabel("error")).toBe("Needs attention");
  });

  it("builds preparing and almost-ready primary copy", () => {
    expect(buildPreviewPrimaryState("preparing", { hasBackendSource: false })).toEqual({
      title: "HAM is preparing your preview.",
      subtitle: "Hang tight while HAM sets up your project files.",
    });
    expect(
      buildPreviewPrimaryState("starting", {
        hasBackendSource: true,
        previewMode: "cloud",
        cloudPreviewDisconnected: false,
      }),
    ).toEqual({
      title: "Preview is almost ready.",
      subtitle:
        "Your project files are ready. The hosted preview will appear here when the environment finishes starting.",
    });
  });

  it("builds error primary copy without leaking raw API messages", () => {
    expect(
      buildPreviewPrimaryState("error", {
        hasBackendSource: true,
        rawError: "PREVIEW_PROXY_FAILED",
        previewMessage: "builder-artifact://secret/path",
      }),
    ).toEqual({
      title: "Preview could not start.",
      subtitle:
        "Your project files are saved in the Code tab. Try again or open details for setup help.",
    });
  });

  it("sanitizes fetch and state errors", () => {
    expect(sanitizePreviewFetchError("HTTP 502 Bad Gateway")).toMatch(/still preparing/i);
    expect(
      sanitizePreviewFetchError('{"detail":{"code":"PREVIEW_PROXY_UPSTREAM_UNAVAILABLE"}}'),
    ).toMatch(/warming up/i);
    expect(sanitizePreviewStateError("Unknown project_id 'proj_x'.")).toMatch(
      /no longer available/i,
    );
    expect(sanitizePreviewStateError("safe_edit_low token leak")).toMatch(/could not start/i);
  });

  it("sanitizes details panel status", () => {
    expect(sanitizePreviewDetailsStatus("PREVIEW_PROXY_TIMEOUT upstream pod-abc")).toMatch(
      /warming up|updating/i,
    );
    expect(sanitizePreviewDetailsStatus(null)).toBe("Preview status is updating.");
  });

  it("flags forbidden internal strings in user copy", () => {
    expect(previewUserCopyLooksSafe("Preview is almost ready.")).toBe(true);
    expect(previewUserCopyLooksSafe("preview_proxy upstream")).toBe(false);
    expect(previewUserCopyLooksSafe("ControlPlaneRun failed")).toBe(false);
  });
});
