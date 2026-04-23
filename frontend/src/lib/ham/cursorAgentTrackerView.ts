/**
 * Read-only presentation of `GET /api/cursor/agents/{id}` JSON for the Tracker tab.
 * Best-effort; unknown shapes fall back to raw JSON in the panel.
 */
export type AgentReadableField = { label: string; value: string };

function r(o: unknown): Record<string, unknown> | null {
  return o && typeof o === "object" && !Array.isArray(o) ? (o as Record<string, unknown>) : null;
}

function s(x: unknown): string | null {
  if (typeof x === "string" && x.trim()) return x;
  if (typeof x === "number" && Number.isFinite(x)) return String(x);
  if (typeof x === "boolean") return x ? "true" : "false";
  return null;
}

/**
 * Flattens common Cursor agent object fields into labeled lines.
 */
export function buildReadableAgentFields(agent: Record<string, unknown> | null): AgentReadableField[] {
  if (!agent) return [];
  const out: AgentReadableField[] = [];
  const push = (label: string, value: string | null | undefined) => {
    const t = value?.trim();
    if (t) out.push({ label, value: t });
  };

  push("Id", s(agent["id"]));
  push("Name", s(agent["name"]));
  push("Status", s(agent["status"]));
  const src = r(agent["source"]);
  if (src) {
    push("Repository", s(src["repository"] ?? src["url"]));
    push("Ref", s(src["ref"] ?? src["branch"]));
  }
  const target = r(agent["target"]) ?? r(agent["pr"]) ?? r(agent["pull_request"]);
  if (target) {
    push("Branch", s(target["branchName"] ?? target["branch"] ?? target["ref"]));
    push("Handoff URL", s(target["url"] ?? target["html_url"]));
    if (target["autoCreatePr"] === true) push("Auto-create PR", "yes");
  }
  push("Created", s(agent["createdAt"] ?? agent["created_at"]));
  push("Updated", s(agent["updatedAt"] ?? agent["updated_at"]));
  if (out.length === 0) {
    return [{ label: "Payload", value: "No common fields were recognized; use raw JSON (toggle)." }];
  }
  return out;
}
