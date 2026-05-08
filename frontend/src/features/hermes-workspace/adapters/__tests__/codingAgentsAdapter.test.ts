import { afterEach, describe, expect, it, vi } from "vitest";
import * as api from "@/lib/ham/api";
import {
  buildDroidAuditPreviewView,
  buildLaunchRequest,
  buildPreview,
  deriveCodingAgentRunStatus,
  deriveCursorReadiness,
  deriveDroidRunStatus,
  droidRunStatusLabel,
  fetchDroidAuditRunsForProject,
  launchDroidAuditFlow,
  launchNewCodingTask,
  previewDroidAuditFlow,
  userFacingDroidPreviewFailureMessage,
  userFacingLaunchFailureMessage,
  validateNewCodingTaskForm,
  validateNewDroidAuditForm,
  type NewCodingTaskFormInput,
  type NewDroidAuditFormInput,
} from "@/features/hermes-workspace/adapters/codingAgentsAdapter";
import { CODING_AGENT_LABELS } from "@/features/hermes-workspace/screens/coding-agents/codingAgentLabels";
import type { CursorCredentialsStatus } from "@/lib/ham/types";

const VALIDATION_COPY = {
  validationProjectRequired: "Pick a project.",
  validationRepositoryRequired: "Repository URL is required.",
  validationTaskRequired: "Describe what the agent should do.",
};

function input(overrides: Partial<NewCodingTaskFormInput> = {}): NewCodingTaskFormInput {
  return {
    projectId: "project.demo",
    repository: "https://github.com/Code-Munkiz/ham",
    taskPrompt: "Refactor the README intro paragraph.",
    ref: null,
    branchName: null,
    autoCreatePr: false,
    ...overrides,
  };
}

function credentialsStatus(
  overrides: Partial<CursorCredentialsStatus> = {},
): CursorCredentialsStatus {
  return {
    configured: true,
    source: "ui",
    masked_preview: "key_***ABCD",
    api_key_name: "primary",
    user_email: "user@example.com",
    key_created_at: null,
    error: null,
    ...overrides,
  };
}

afterEach(() => {
  vi.restoreAllMocks();
});

// ---------------------------------------------------------------------------
// Readiness
// ---------------------------------------------------------------------------

describe("deriveCursorReadiness", () => {
  it("returns Ready when configured and no error", () => {
    expect(deriveCursorReadiness(credentialsStatus())).toBe("ready");
  });

  it("returns Needs setup when configured=false", () => {
    expect(deriveCursorReadiness(credentialsStatus({ configured: false }))).toBe("needs_setup");
  });

  it("returns Needs setup when there is a key error", () => {
    expect(
      deriveCursorReadiness(credentialsStatus({ error: "Cursor rejected this API key (401)." })),
    ).toBe("needs_setup");
  });

  it("returns Needs setup for null status", () => {
    expect(deriveCursorReadiness(null)).toBe("needs_setup");
  });
});

// ---------------------------------------------------------------------------
// Run status mapping (cursor → product)
// ---------------------------------------------------------------------------

describe("deriveCodingAgentRunStatus", () => {
  it.each([
    ["FINISHED"],
    ["COMPLETED"],
    ["SUCCEEDED"],
    ["SUCCESS"],
    ["DONE"],
    ["finished"],
    ["completed"],
  ])("treats %s as Complete", (raw) => {
    expect(deriveCodingAgentRunStatus(raw)).toBe("complete");
  });

  it.each([["FAILED"], ["ERROR"], ["ERRORED"], ["CANCELLED"], ["CANCELED"], ["failed"], ["error"]])(
    "treats %s as Failed",
    (raw) => {
      expect(deriveCodingAgentRunStatus(raw)).toBe("failed");
    },
  );

  it.each([
    ["RUNNING"],
    ["PENDING"],
    ["QUEUED"],
    ["STARTING"],
    ["WORKING"],
    ["unknown"],
    [""],
    [null],
    [undefined],
  ])("treats %s as In progress (never claims Complete for unknown)", (raw) => {
    expect(deriveCodingAgentRunStatus(raw)).toBe("in_progress");
  });
});

// ---------------------------------------------------------------------------
// Form validation
// ---------------------------------------------------------------------------

describe("validateNewCodingTaskForm", () => {
  it("accepts a valid GitHub URL + project + prompt", () => {
    const v = validateNewCodingTaskForm(input(), VALIDATION_COPY);
    expect(v.ok).toBe(true);
    expect(v.errors).toEqual({});
  });

  it("rejects missing project id", () => {
    const v = validateNewCodingTaskForm(input({ projectId: "  " }), VALIDATION_COPY);
    expect(v.ok).toBe(false);
    expect(v.errors.projectId).toBe(VALIDATION_COPY.validationProjectRequired);
  });

  it("rejects empty task prompt", () => {
    const v = validateNewCodingTaskForm(input({ taskPrompt: "   " }), VALIDATION_COPY);
    expect(v.ok).toBe(false);
    expect(v.errors.taskPrompt).toBe(VALIDATION_COPY.validationTaskRequired);
  });

  it("rejects missing repository URL", () => {
    const v = validateNewCodingTaskForm(input({ repository: "" }), VALIDATION_COPY);
    expect(v.ok).toBe(false);
    expect(v.errors.repository).toBe(VALIDATION_COPY.validationRepositoryRequired);
  });

  it("rejects non-GitHub URLs", () => {
    const v = validateNewCodingTaskForm(
      input({ repository: "https://gitlab.com/foo/bar" }),
      VALIDATION_COPY,
    );
    expect(v.ok).toBe(false);
    expect(v.errors.repository).toBe(VALIDATION_COPY.validationRepositoryRequired);
  });

  it("rejects http (non-https) GitHub URLs", () => {
    const v = validateNewCodingTaskForm(
      input({ repository: "http://github.com/foo/bar" }),
      VALIDATION_COPY,
    );
    expect(v.ok).toBe(false);
    expect(v.errors.repository).toBe(VALIDATION_COPY.validationRepositoryRequired);
  });

  it("rejects GitHub URL missing org/repo path", () => {
    const v = validateNewCodingTaskForm(
      input({ repository: "https://github.com/" }),
      VALIDATION_COPY,
    );
    expect(v.ok).toBe(false);
    expect(v.errors.repository).toBe(VALIDATION_COPY.validationRepositoryRequired);
  });

  it("rejects malformed URLs", () => {
    const v = validateNewCodingTaskForm(input({ repository: "not a url" }), VALIDATION_COPY);
    expect(v.ok).toBe(false);
    expect(v.errors.repository).toBe(VALIDATION_COPY.validationRepositoryRequired);
  });
});

// ---------------------------------------------------------------------------
// Launch payload normalization
// ---------------------------------------------------------------------------

describe("buildLaunchRequest", () => {
  it("trims and pins mission_handling=managed and project_id", () => {
    const body = buildLaunchRequest(
      input({
        projectId: "  project.demo  ",
        repository: "  https://github.com/Code-Munkiz/ham  ",
        taskPrompt: "  do the thing  ",
      }),
    );
    expect(body.project_id).toBe("project.demo");
    expect(body.repository).toBe("https://github.com/Code-Munkiz/ham");
    expect(body.prompt_text).toBe("do the thing");
    expect(body.mission_handling).toBe("managed");
    expect(body.model).toBe("default");
    expect(body.auto_create_pr).toBe(false);
  });

  it("omits empty optional fields", () => {
    const body = buildLaunchRequest(input({ ref: "  ", branchName: "" }));
    expect(body.ref).toBeUndefined();
    expect(body.branch_name).toBeUndefined();
  });

  it("includes optional ref + branch when set", () => {
    const body = buildLaunchRequest(
      input({ ref: " main ", branchName: " feat/x ", autoCreatePr: true }),
    );
    expect(body.ref).toBe("main");
    expect(body.branch_name).toBe("feat/x");
    expect(body.auto_create_pr).toBe(true);
  });
});

// ---------------------------------------------------------------------------
// Preview shape
// ---------------------------------------------------------------------------

describe("buildPreview", () => {
  it("normalizes the preview shape with trimmed values", () => {
    const p = buildPreview(input({ ref: " main ", branchName: " feat/x ", autoCreatePr: true }));
    expect(p).toEqual({
      projectId: "project.demo",
      repository: "https://github.com/Code-Munkiz/ham",
      taskPromptPreview: "Refactor the README intro paragraph.",
      ref: "main",
      branchName: "feat/x",
      autoCreatePr: true,
    });
  });

  it("returns null for empty optional fields", () => {
    const p = buildPreview(input());
    expect(p.ref).toBeNull();
    expect(p.branchName).toBeNull();
  });

  it("truncates very long prompts for the preview pane", () => {
    const long = "a".repeat(2_000);
    const p = buildPreview(input({ taskPrompt: long }));
    expect(p.taskPromptPreview.length).toBeLessThanOrEqual(600);
    expect(p.taskPromptPreview.endsWith("…")).toBe(true);
  });
});

// ---------------------------------------------------------------------------
// Launch UX (normie errors + auth parity with credentials-status)
// ---------------------------------------------------------------------------

describe("userFacingLaunchFailureMessage", () => {
  it("maps Cursor API key rejection to Settings copy (no 401 in output)", () => {
    const msg = userFacingLaunchFailureMessage("Cursor rejected this API key (401).");
    expect(msg).toBe(CODING_AGENT_LABELS.launchCursorConnectionHelp);
    expect(msg.toLowerCase()).not.toContain("401");
  });

  it("maps Clerk session gate copy to sign-in guidance", () => {
    expect(userFacingLaunchFailureMessage("Code: CLERK_SESSION_REQUIRED — use Bearer token")).toBe(
      CODING_AGENT_LABELS.launchSessionAuthorizeHelp,
    );
  });

  it("maps bare HTTP 401 fallback to Cursor connection copy", () => {
    expect(userFacingLaunchFailureMessage("HTTP 401")).toBe(
      CODING_AGENT_LABELS.launchCursorConnectionHelp,
    );
  });

  it("passes through other errors shortened", () => {
    expect(userFacingLaunchFailureMessage("Cursor launch error: rate limited")).toContain("rate");
  });
});

describe("launchNewCodingTask", () => {
  it("returns agent id on success", async () => {
    vi.spyOn(api, "launchCursorAgent").mockResolvedValue({ id: "bc-win" });
    const out = await launchNewCodingTask(input());
    expect(out.ok).toBe(true);
    expect(out.cursorAgentId).toBe("bc-win");
    expect(out.errorMessage).toBeNull();
  });

  it("returns friendly copy when launch rejects credentials", async () => {
    vi.spyOn(api, "launchCursorAgent").mockRejectedValue(
      new Error("Cursor rejected this API key (401)."),
    );
    const out = await launchNewCodingTask(input());
    expect(out.ok).toBe(false);
    expect(out.cursorAgentId).toBeNull();
    expect(out.errorMessage).toBe(CODING_AGENT_LABELS.launchCursorConnectionHelp);
  });
});

// ---------------------------------------------------------------------------
// Factory Droid — read-only audit lane
// ---------------------------------------------------------------------------

const AUDIT_VALIDATION_COPY = {
  validationProjectRequired: "Pick a project.",
  validationTaskRequired: "Describe what you want audited.",
};

function auditInput(overrides: Partial<NewDroidAuditFormInput> = {}): NewDroidAuditFormInput {
  return {
    projectId: "project.demo",
    taskPrompt: "Audit security and architecture risks.",
    ...overrides,
  };
}

describe("validateNewDroidAuditForm", () => {
  it("accepts a project + non-empty prompt", () => {
    const v = validateNewDroidAuditForm(auditInput(), AUDIT_VALIDATION_COPY);
    expect(v.ok).toBe(true);
  });

  it("rejects missing project id", () => {
    const v = validateNewDroidAuditForm(auditInput({ projectId: " " }), AUDIT_VALIDATION_COPY);
    expect(v.ok).toBe(false);
    expect(v.errors.projectId).toBe(AUDIT_VALIDATION_COPY.validationProjectRequired);
  });

  it("rejects empty prompt", () => {
    const v = validateNewDroidAuditForm(auditInput({ taskPrompt: "" }), AUDIT_VALIDATION_COPY);
    expect(v.ok).toBe(false);
    expect(v.errors.taskPrompt).toBe(AUDIT_VALIDATION_COPY.validationTaskRequired);
  });
});

describe("deriveDroidRunStatus", () => {
  it.each([["running"], ["RUNNING"], ["in_progress"]])("treats %s as running", (raw) => {
    expect(deriveDroidRunStatus(raw)).toBe("running");
  });
  it.each([["succeeded"], ["complete"], ["completed"], ["ok"]])("treats %s as complete", (raw) => {
    expect(deriveDroidRunStatus(raw)).toBe("complete");
  });
  it.each([["failed"], ["error"], ["errored"], ["cancelled"]])("treats %s as failed", (raw) => {
    expect(deriveDroidRunStatus(raw)).toBe("failed");
  });
  it.each([["unknown"], [""], [null], [undefined], ["weird-state"]])(
    "treats %s as needs_attention (never claims complete)",
    (raw) => {
      expect(deriveDroidRunStatus(raw as string | null | undefined)).toBe("needs_attention");
    },
  );
});

describe("droidRunStatusLabel", () => {
  it("maps each status to the agreed friendly label", () => {
    expect(droidRunStatusLabel("running")).toBe(CODING_AGENT_LABELS.statusRunning);
    expect(droidRunStatusLabel("complete")).toBe(CODING_AGENT_LABELS.statusComplete);
    expect(droidRunStatusLabel("failed")).toBe(CODING_AGENT_LABELS.statusFailed);
    expect(droidRunStatusLabel("needs_attention")).toBe(CODING_AGENT_LABELS.statusNeedsAttention);
  });
});

describe("buildDroidAuditPreviewView", () => {
  it("trims and truncates the prompt for preview display", () => {
    const long = "z".repeat(1_500);
    const view = buildDroidAuditPreviewView({
      kind: "droid_audit_preview",
      project_id: "project.demo",
      project_name: "Demo",
      user_prompt: long,
      summary_preview: "  some summary  ",
      proposal_digest: "0".repeat(64),
      base_revision: "rev-1",
      is_readonly: true,
      mutates: false,
    });
    expect(view.taskPromptPreview.length).toBeLessThanOrEqual(600);
    expect(view.taskPromptPreview.endsWith("…")).toBe(true);
    expect(view.summaryPreview).toBe("some summary");
    expect(view.projectName).toBe("Demo");
  });
});

describe("previewDroidAuditFlow", () => {
  it("returns ok preview on success", async () => {
    vi.spyOn(api, "previewDroidAudit").mockResolvedValue({
      kind: "droid_audit_preview",
      project_id: "project.demo",
      project_name: "Demo",
      user_prompt: "audit",
      summary_preview: "summary",
      proposal_digest: "a".repeat(64),
      base_revision: "rev-1",
      is_readonly: true,
      mutates: false,
    });
    const out = await previewDroidAuditFlow(auditInput());
    expect(out.ok).toBe(true);
    if (out.ok) {
      expect(out.preview.proposalDigest).toBe("a".repeat(64));
    }
  });

  it("returns generic friendly message on unmapped failure (never raw error text)", async () => {
    vi.spyOn(api, "previewDroidAudit").mockRejectedValue(new Error("boom"));
    const out = await previewDroidAuditFlow(auditInput());
    expect(out.ok).toBe(false);
    if (out.ok === false) {
      expect(out.errorMessage).toBe(CODING_AGENT_LABELS.auditPreviewFailed);
      expect(out.errorMessage).not.toContain("boom");
      expect(out.errorMessage).not.toContain("HTTP");
      expect(out.errorMessage).not.toContain("/api/");
    }
  });

  it("maps 404 / Not Found to auditDeploymentNotReady", async () => {
    vi.spyOn(api, "previewDroidAudit").mockRejectedValue(new Error("Not Found"));
    const out = await previewDroidAuditFlow(auditInput());
    expect(out.ok).toBe(false);
    if (out.ok === false) {
      expect(out.errorMessage).toBe(CODING_AGENT_LABELS.auditDeploymentNotReady);
    }
  });

  it("maps 422 to auditPreviewValidationFailed", async () => {
    vi.spyOn(api, "previewDroidAudit").mockRejectedValue(new Error("HTTP 422"));
    const out = await previewDroidAuditFlow(auditInput());
    expect(out.ok).toBe(false);
    if (out.ok === false) {
      expect(out.errorMessage).toBe(CODING_AGENT_LABELS.auditPreviewValidationFailed);
    }
  });

  it("maps Clerk session errors to sign-in copy", async () => {
    vi.spyOn(api, "previewDroidAudit").mockRejectedValue(
      new Error("CLERK_SESSION_REQUIRED — use Bearer token"),
    );
    const out = await previewDroidAuditFlow(auditInput());
    expect(out.ok).toBe(false);
    if (out.ok === false) {
      expect(out.errorMessage).toBe(CODING_AGENT_LABELS.launchSessionAuthorizeHelp);
    }
  });
});

describe("userFacingDroidPreviewFailureMessage", () => {
  it.each([
    ["Not Found"],
    ["HTTP 404"],
    ["404 — PROJECT_NOT_FOUND"],
    ["DROID_AUDIT_WORKFLOW_MISSING"],
  ])("maps %s to deployment-not-ready copy", (raw) => {
    expect(userFacingDroidPreviewFailureMessage(raw)).toBe(
      CODING_AGENT_LABELS.auditDeploymentNotReady,
    );
  });

  it.each([["HTTP 422"], ["validation error: project_id"], ["422 Unprocessable Entity"]])(
    "maps %s to preview-validation-failed copy",
    (raw) => {
      expect(userFacingDroidPreviewFailureMessage(raw)).toBe(
        CODING_AGENT_LABELS.auditPreviewValidationFailed,
      );
    },
  );

  it("never returns raw HTTP / Not Found / API path text", () => {
    const samples = ["HTTP 500", "EOF", "Not Found", "HTTP 422", "/api/droid/preview"];
    for (const raw of samples) {
      const msg = userFacingDroidPreviewFailureMessage(raw);
      expect(msg.toLowerCase()).not.toContain("http 5");
      expect(msg.toLowerCase()).not.toContain("not found");
      expect(msg).not.toContain("/api/");
    }
  });
});

describe("fetchDroidAuditRunsForProject", () => {
  it("does not call the API when projectId is null/empty (avoids 422)", async () => {
    const spy = vi.spyOn(api, "fetchDroidAuditRuns").mockResolvedValue([]);
    const out = await fetchDroidAuditRunsForProject(null);
    expect(spy).not.toHaveBeenCalled();
    expect(out.ok).toBe(true);
    if (out.ok === true) {
      expect(out.runs).toEqual([]);
      expect(out.reason).toBe("no_project");
    }
  });

  it("does not call the API for whitespace-only projectId", async () => {
    const spy = vi.spyOn(api, "fetchDroidAuditRuns").mockResolvedValue([]);
    const out = await fetchDroidAuditRunsForProject("   ");
    expect(spy).not.toHaveBeenCalled();
    expect(out.ok).toBe(true);
    if (out.ok === true) {
      expect(out.reason).toBe("no_project");
    }
  });

  it("calls the API with project_id when provided", async () => {
    const spy = vi.spyOn(api, "fetchDroidAuditRuns").mockImplementation(async (projectId, opts) => {
      expect(projectId).toBe("project.demo");
      expect(opts?.limit).toBe(25);
      return [];
    });
    const out = await fetchDroidAuditRunsForProject("project.demo");
    expect(spy).toHaveBeenCalled();
    expect(out.ok).toBe(true);
    if (out.ok === true) {
      expect(out.runs).toEqual([]);
      expect("reason" in out ? out.reason : undefined).toBeUndefined();
    }
  });

  it("trims project_id before passing to API", async () => {
    let received: string | null | undefined = undefined;
    vi.spyOn(api, "fetchDroidAuditRuns").mockImplementation(async (projectId) => {
      received = projectId;
      return [];
    });
    await fetchDroidAuditRunsForProject("  project.demo  ");
    expect(received).toBe("project.demo");
  });

  it("maps any thrown error to friendly auditRunsLoadFailed (never raw text)", async () => {
    vi.spyOn(api, "fetchDroidAuditRuns").mockRejectedValue(new Error("HTTP 422"));
    const out = await fetchDroidAuditRunsForProject("project.demo");
    expect(out.ok).toBe(false);
    if (out.ok === false) {
      expect(out.errorMessage).toBe(CODING_AGENT_LABELS.auditRunsLoadFailed);
      expect(out.errorMessage).not.toContain("422");
      expect(out.errorMessage).not.toContain("HTTP");
    }
  });
});

describe("launchDroidAuditFlow", () => {
  it("returns ham_run_id on success", async () => {
    vi.spyOn(api, "launchDroidAudit").mockResolvedValue({
      kind: "droid_audit_launch",
      project_id: "project.demo",
      ok: true,
      ham_run_id: "11111111-1111-1111-1111-111111111111",
      control_plane_status: "succeeded",
      summary: "audit ok",
      blocking_reason: null,
      is_readonly: true,
    });
    const out = await launchDroidAuditFlow(auditInput(), {
      projectId: "project.demo",
      projectName: "Demo",
      taskPromptPreview: "audit",
      summaryPreview: "",
      proposalDigest: "a".repeat(64),
      baseRevision: "rev-1",
    });
    expect(out.ok).toBe(true);
    expect(out.hamRunId).toBe("11111111-1111-1111-1111-111111111111");
  });

  it("masks server blocking_reason behind friendly copy (never leaks raw exec details)", async () => {
    vi.spyOn(api, "launchDroidAudit").mockResolvedValue({
      kind: "droid_audit_launch",
      project_id: "project.demo",
      ok: false,
      ham_run_id: null,
      control_plane_status: "failed",
      summary: null,
      blocking_reason: "droid exec failed (exit 7)",
      is_readonly: true,
    });
    const out = await launchDroidAuditFlow(auditInput(), {
      projectId: "project.demo",
      projectName: "Demo",
      taskPromptPreview: "audit",
      summaryPreview: "",
      proposalDigest: "a".repeat(64),
      baseRevision: "rev-1",
    });
    expect(out.ok).toBe(false);
    expect(out.errorMessage).toBe(CODING_AGENT_LABELS.auditPreviewFailed);
    expect(out.errorMessage).not.toContain("exit");
    expect(out.errorMessage).not.toContain("droid exec");
  });

  it("maps thrown 404 from launch to deployment-not-ready copy", async () => {
    vi.spyOn(api, "launchDroidAudit").mockRejectedValue(new Error("Not Found"));
    const out = await launchDroidAuditFlow(auditInput(), {
      projectId: "project.demo",
      projectName: "Demo",
      taskPromptPreview: "audit",
      summaryPreview: "",
      proposalDigest: "a".repeat(64),
      baseRevision: "rev-1",
    });
    expect(out.ok).toBe(false);
    expect(out.errorMessage).toBe(CODING_AGENT_LABELS.auditDeploymentNotReady);
  });
});
