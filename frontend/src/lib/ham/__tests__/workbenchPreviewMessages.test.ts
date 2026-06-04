import { describe, expect, it } from "vitest";
import {
  PREVIEW_BUILDING_TITLE,
  PREVIEW_FAILURE_TITLE,
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

  it("builds simplified building and empty primary copy", () => {
    expect(buildPreviewPrimaryState("preparing", { hasBackendSource: false })).toEqual({
      title: PREVIEW_BUILDING_TITLE,
      subtitle: "",
    });
    expect(
      buildPreviewPrimaryState("starting", {
        hasBackendSource: true,
        previewMode: "cloud",
        cloudPreviewDisconnected: false,
      }),
    ).toEqual({
      title: PREVIEW_BUILDING_TITLE,
      subtitle: "",
    });
  });

  it("builds simplified error primary copy without leaking raw API messages", () => {
    expect(
      buildPreviewPrimaryState("error", {
        hasBackendSource: true,
        rawError: "PREVIEW_PROXY_FAILED",
        previewMessage: "builder-artifact://secret/path",
      }),
    ).toEqual({
      title: PREVIEW_FAILURE_TITLE,
      subtitle: "",
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
    expect(previewUserCopyLooksSafe("HAM is building your preview…")).toBe(true);
    expect(previewUserCopyLooksSafe("preview_proxy upstream")).toBe(false);
    expect(previewUserCopyLooksSafe("ControlPlaneRun failed")).toBe(false);
  });
});
