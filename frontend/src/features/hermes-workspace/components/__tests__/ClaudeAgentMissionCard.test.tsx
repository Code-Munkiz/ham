/**
 * Claude Agent Mission Card — Operations surface for bounded plan-mode validation.
 * Verifies: render, launch, loading state, success display, failure display, no secrets.
 */
import { describe, expect, it, vi, beforeEach } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import * as HamApi from "@/lib/ham/api";
import { ClaudeAgentMissionCard } from "../ClaudeAgentMissionCard";

vi.mock("@/lib/ham/api", () => ({
  postClaudeAgentMission: vi.fn(),
}));

const MOCK_SUCCESS_RESPONSE = {
  ok: true,
  mission_ok: true,
  worker: "claude_agent_sdk",
  mission_type: "non_mutating_review",
  result_text: "This is a test result from Claude Agent SDK plan mode mission.",
  parsed_result: {
    mission_status: "ok",
    worker: "claude_agent_sdk",
    job_type: "non_mutating_review",
    summary: "Reviewed project structure",
    acceptance_criteria: ["Criterion one", "Criterion two", "Criterion three"],
  },
  duration_ms: 4200,
  safety_mode: "plan",
  blocker: null,
};

const MOCK_FAILURE_RESPONSE = {
  ok: true,
  mission_ok: false,
  worker: "claude_agent_sdk",
  mission_type: "non_mutating_review",
  result_text: "some text",
  parsed_result: null,
  duration_ms: 1200,
  safety_mode: "plan",
  blocker: "Mission JSON did not match acceptance: could not parse a single JSON object",
};

function mockFetchResponse(body: unknown, status = 200): Response {
  return {
    ok: status >= 200 && status < 300,
    status,
    json: () => Promise.resolve(body),
    headers: new Headers(),
    redirected: false,
    statusText: "OK",
    type: "basic",
    url: "",
    clone: () => mockFetchResponse(body, status),
    body: null,
    bodyUsed: false,
    arrayBuffer: () => Promise.resolve(new ArrayBuffer(0)),
    blob: () => Promise.resolve(new Blob()),
    formData: () => Promise.resolve(new FormData()),
    text: () => Promise.resolve(JSON.stringify(body)),
    bytes: () => Promise.resolve(new Uint8Array()),
  } as unknown as Response;
}

describe("ClaudeAgentMissionCard", () => {
  beforeEach(() => {
    vi.resetAllMocks();
  });

  it("renders the run button on Operations", () => {
    render(<ClaudeAgentMissionCard />);
    expect(screen.getByTestId("run-claude-mission-btn")).toBeDefined();
    expect(screen.getByText("Run Claude Agent mission")).toBeDefined();
  });

  it("shows loading state when mission is running", async () => {
    let resolvePromise: (v: Response) => void;
    const pending = new Promise<Response>((resolve) => { resolvePromise = resolve; });
    vi.mocked(HamApi.postClaudeAgentMission).mockReturnValue(pending);

    render(<ClaudeAgentMissionCard />);
    fireEvent.click(screen.getByTestId("run-claude-mission-btn"));

    await waitFor(() => {
      expect(screen.getByTestId("mission-loading")).toBeDefined();
    });

    resolvePromise!(mockFetchResponse(MOCK_SUCCESS_RESPONSE));
  });

  it("calls mission endpoint without X-HAM-SMOKE-TOKEN", async () => {
    vi.mocked(HamApi.postClaudeAgentMission).mockResolvedValue(mockFetchResponse(MOCK_SUCCESS_RESPONSE));

    render(<ClaudeAgentMissionCard />);
    fireEvent.click(screen.getByTestId("run-claude-mission-btn"));

    await waitFor(() => {
      expect(HamApi.postClaudeAgentMission).toHaveBeenCalledTimes(1);
    });
    // postClaudeAgentMission is called with no arguments (no token)
    expect(HamApi.postClaudeAgentMission).toHaveBeenCalledWith();
  });

  it("renders success result with mission_ok true", async () => {
    vi.mocked(HamApi.postClaudeAgentMission).mockResolvedValue(mockFetchResponse(MOCK_SUCCESS_RESPONSE));

    render(<ClaudeAgentMissionCard />);
    fireEvent.click(screen.getByTestId("run-claude-mission-btn"));

    await waitFor(() => {
      expect(screen.getByTestId("mission-success")).toBeDefined();
    });

    expect(screen.getByTestId("mission-ok-badge").textContent).toContain("mission_ok: true");
    expect(screen.getByTestId("mission-worker").textContent).toContain("claude_agent_sdk");
  });

  it("renders acceptance criteria with count 3", async () => {
    vi.mocked(HamApi.postClaudeAgentMission).mockResolvedValue(mockFetchResponse(MOCK_SUCCESS_RESPONSE));

    render(<ClaudeAgentMissionCard />);
    fireEvent.click(screen.getByTestId("run-claude-mission-btn"));

    await waitFor(() => {
      expect(screen.getByTestId("acceptance-criteria")).toBeDefined();
    });

    const criteriaSection = screen.getByTestId("acceptance-criteria");
    expect(criteriaSection.textContent).toContain("Acceptance criteria (3)");
    expect(criteriaSection.textContent).toContain("Criterion one");
    expect(criteriaSection.textContent).toContain("Criterion two");
    expect(criteriaSection.textContent).toContain("Criterion three");
  });

  it("renders failure result with safe blocker message", async () => {
    vi.mocked(HamApi.postClaudeAgentMission).mockResolvedValue(mockFetchResponse(MOCK_FAILURE_RESPONSE));

    render(<ClaudeAgentMissionCard />);
    fireEvent.click(screen.getByTestId("run-claude-mission-btn"));

    await waitFor(() => {
      expect(screen.getByTestId("mission-error")).toBeDefined();
    });

    expect(screen.getByTestId("mission-error").textContent).toContain("Parser rejected output");
  });

  it("renders connect-first message on 400 CONNECT_CLAUDE_AGENT_REQUIRED", async () => {
    vi.mocked(HamApi.postClaudeAgentMission).mockResolvedValue(
      mockFetchResponse(
        { detail: { code: "CONNECT_CLAUDE_AGENT_REQUIRED", message: "Connect Claude Agent first." } },
        400,
      ),
    );

    render(<ClaudeAgentMissionCard />);
    fireEvent.click(screen.getByTestId("run-claude-mission-btn"));

    await waitFor(() => {
      expect(screen.getByTestId("mission-error")).toBeDefined();
    });

    expect(screen.getByTestId("mission-error").textContent).toContain("Connect Claude Agent first");
  });

  it("does not expose raw keys or tokens in rendered output", async () => {
    vi.mocked(HamApi.postClaudeAgentMission).mockResolvedValue(mockFetchResponse(MOCK_SUCCESS_RESPONSE));

    const { container } = render(<ClaudeAgentMissionCard />);
    fireEvent.click(screen.getByTestId("run-claude-mission-btn"));

    await waitFor(() => {
      expect(screen.getByTestId("mission-success")).toBeDefined();
    });

    const html = container.innerHTML;
    expect(html).not.toContain("sk-ant-");
    expect(html).not.toContain("ANTHROPIC_API_KEY");
    expect(html).not.toContain("X-HAM-SMOKE-TOKEN");
    expect(html).not.toContain("Bearer ");
  });
});
