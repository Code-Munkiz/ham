import { afterEach, describe, expect, it, vi } from "vitest";
import * as api from "@/lib/ham/api";
import {
  buildLaunchRequest,
  buildPreview,
  deriveCodingAgentRunStatus,
  deriveCursorReadiness,
  launchNewCodingTask,
  userFacingLaunchFailureMessage,
  validateNewCodingTaskForm,
  type NewCodingTaskFormInput,
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
