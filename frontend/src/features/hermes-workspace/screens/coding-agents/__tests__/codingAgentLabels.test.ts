import { describe, expect, it } from "vitest";
import { CODING_AGENT_LABELS } from "@/features/hermes-workspace/screens/coding-agents/codingAgentLabels";

/**
 * Locks the user-facing copy for the Coding Agents screen. The product rule
 * for this MVP: never expose internal vocabulary in primary UI. These tests
 * are the canary — if they fail because of a copy change, update the label
 * map and this file together, on purpose.
 */
describe("CODING_AGENT_LABELS — locked product copy", () => {
  it("uses the agreed primary action labels", () => {
    expect(CODING_AGENT_LABELS.surfaceTitle).toBe("Coding agents");
    expect(CODING_AGENT_LABELS.newTaskCta).toBe("New task");
    expect(CODING_AGENT_LABELS.previewCta).toBe("Preview");
    expect(CODING_AGENT_LABELS.approveCta).toBe("Approve launch");
    expect(CODING_AGENT_LABELS.trackProgressCta).toBe("Track progress");
  });

  it("uses the agreed readiness labels", () => {
    expect(CODING_AGENT_LABELS.readinessReady).toBe("Ready");
    expect(CODING_AGENT_LABELS.readinessNeedsSetup).toBe("Needs setup");
  });

  it("uses the agreed run status labels", () => {
    expect(CODING_AGENT_LABELS.statusInProgress).toBe("In progress");
    expect(CODING_AGENT_LABELS.statusComplete).toBe("Complete");
    expect(CODING_AGENT_LABELS.statusFailed).toBe("Failed");
    expect(CODING_AGENT_LABELS.statusRunning).toBe("Running");
    expect(CODING_AGENT_LABELS.statusNeedsAttention).toBe("Needs attention");
  });

  it("uses the agreed audit-flow labels", () => {
    expect(CODING_AGENT_LABELS.auditTitle).toBe("Factory Droid audit");
    expect(CODING_AGENT_LABELS.auditCta).toBe("New audit");
    expect(CODING_AGENT_LABELS.auditReadOnlyPill).toContain("Read-only");
    expect(CODING_AGENT_LABELS.chooserCursorTitle).toContain("Cursor");
    expect(CODING_AGENT_LABELS.chooserDroidTitle).toContain("Factory Droid");
  });

  it("uses friendly copy for audit failure / no-project / load-failed states", () => {
    expect(CODING_AGENT_LABELS.auditNoProjectTitle.toLowerCase()).toContain("project");
    expect(CODING_AGENT_LABELS.auditDeploymentNotReady.toLowerCase()).toContain("deployment");
    expect(CODING_AGENT_LABELS.auditPreviewFailed.toLowerCase()).toContain("try again");
    expect(CODING_AGENT_LABELS.auditPreviewValidationFailed.toLowerCase()).toContain("try again");
    expect(CODING_AGENT_LABELS.auditRunsLoadFailed.toLowerCase()).toContain("try again");
  });

  it("uses friendly copy for launch failures", () => {
    expect(CODING_AGENT_LABELS.launchCursorConnectionHelp).toContain("Settings");
    expect(CODING_AGENT_LABELS.launchSessionAuthorizeHelp).toContain("Sign in");
  });

  it("never leaks internal vocabulary in any public-facing label", () => {
    const banned = [
      "ControlPlaneRun",
      "control_plane",
      "audit_sink",
      "audit sink",
      "JSONL",
      "jsonl",
      "planned_candidate",
      "registry_status",
      "harness_family",
      "cursor_cloud_agent",
      "factory_droid",
      "claude_code",
      "opencode_cli",
      "mission_handling",
      "operator phase",
      "proposal_digest",
      "mission_registry_id",
      "ManagedMission",
      "HAM_CURSOR_AGENT_LAUNCH_TOKEN",
      "HAM_DROID_EXEC_TOKEN",
      "/api/",
      "safe_edit_low",
      "workflow_id",
      "requires_launch_token",
      "base_revision",
      "REGISTRY_REVISION",
      "HTTP 404",
      "HTTP 422",
      "Not Found",
    ];
    for (const [key, value] of Object.entries(CODING_AGENT_LABELS)) {
      for (const term of banned) {
        expect(
          value.toLowerCase().includes(term.toLowerCase()),
          `label ${key} leaks internal term ${term}: ${value}`,
        ).toBe(false);
      }
    }
  });
});
