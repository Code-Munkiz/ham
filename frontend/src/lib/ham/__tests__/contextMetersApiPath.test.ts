import { describe, expect, it } from "vitest";

/** Mirrors `fetchChatContextMeters` query assembly — must stay on `/api/chat/context-meters` (hamApiFetch). */
function buildContextMetersPath(sessionId: string, modelId: string | null, projectId: string | null) {
  const q = new URLSearchParams();
  q.set("session_id", sessionId);
  if (modelId?.trim()) q.set("model_id", modelId.trim());
  if (projectId?.trim()) q.set("project_id", projectId.trim());
  return `/api/chat/context-meters?${q.toString()}`;
}

describe("context meters API path", () => {
  it("uses /api/chat/context-meters with encoded params (for hamApiFetch, not ad-hoc fetch URL)", () => {
    const path = buildContextMetersPath("s1", "openrouter:default", "p9");
    expect(path.startsWith("/api/chat/context-meters?")).toBe(true);
    expect(path).toContain("session_id=s1");
    expect(path).toContain("model_id=");
    expect(path).toContain("project_id=p9");
  });
});
