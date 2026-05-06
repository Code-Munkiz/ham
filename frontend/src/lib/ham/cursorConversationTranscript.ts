/**
 * Parse proxied Cursor `GET /v0/agents/{id}/conversation` JSON into readable lines.
 * Shapes differ across API versions; this is best-effort and never fabricates text.
 */
export type CursorTranscriptLine = {
  id: string;
  role: "user" | "assistant" | "system" | "unknown";
  body: string;
};

function asRecord(x: unknown): Record<string, unknown> | null {
  return x && typeof x === "object" && !Array.isArray(x) ? (x as Record<string, unknown>) : null;
}

function readString(x: unknown): string | null {
  if (typeof x === "string" && x.trim()) return x;
  return null;
}

function extractTextFromUnknown(x: unknown): string {
  if (typeof x === "string") return x;
  if (x == null) return "";
  if (Array.isArray(x)) {
    return x
      .map((p) => extractTextFromUnknown(p))
      .filter((s) => s.length > 0)
      .join("\n");
  }
  const r = asRecord(x);
  if (r) {
    const t =
      readString(r.text) ??
      readString(r.message) ??
      readString(r.body) ??
      (typeof r.content === "string" ? readString(r.content) : null);
    if (t) return t;
    if (Array.isArray(r.content)) {
      const fromParts = r.content.map((p) => extractTextFromUnknown(p)).filter((s) => s.length > 0);
      if (fromParts.length) return fromParts.join("\n");
    }
    if (r.content && typeof r.content === "object") {
      const c = extractTextFromUnknown(r.content);
      if (c) return c;
    }
  }
  try {
    return JSON.stringify(x, null, 2);
  } catch {
    return String(x);
  }
}

function normalizeToMessageArray(conversation: unknown): unknown[] {
  if (Array.isArray(conversation)) return conversation;
  const r = asRecord(conversation);
  if (r) {
    const a = r.messages ?? r.items ?? r.turns ?? r.data;
    if (Array.isArray(a)) return a;
  }
  return [];
}

/**
 * Heuristic line from a single message object, or a fallback string.
 */
function messageObjectToLine(msg: unknown, index: number): CursorTranscriptLine {
  const id = `cmsg-${index}`;
  const o = asRecord(msg);
  if (!o) {
    return { id, role: "unknown", body: extractTextFromUnknown(msg) };
  }

  if (o.user_message != null) {
    return { id, role: "user", body: extractTextFromUnknown(o.user_message) };
  }
  if (o.assistant_message != null) {
    return { id, role: "assistant", body: extractTextFromUnknown(o.assistant_message) };
  }
  if (o.tool_message != null || o.tool_result != null) {
    const raw = o.tool_message ?? o.tool_result;
    return { id, role: "system", body: extractTextFromUnknown(raw) };
  }

  const roleRaw = readString(o.role)?.toLowerCase() ?? readString(o.type)?.toLowerCase() ?? "";
  const body =
    readString(o.text) ??
    readString(o.content) ??
    (typeof o.content === "object" && o.content ? extractTextFromUnknown(o.content) : null) ??
    (Array.isArray(o.parts) ? extractTextFromUnknown(o.parts) : null) ??
    "";

  if (body) {
    if (roleRaw.includes("user") || roleRaw === "human" || roleRaw === "user_message")
      return { id, role: "user", body };
    if (
      roleRaw.includes("assistant") ||
      roleRaw === "model" ||
      roleRaw === "assistant_message" ||
      roleRaw === "agent"
    )
      return { id, role: "assistant", body };
    if (roleRaw.includes("tool") || roleRaw === "system") return { id, role: "system", body };
    if (readString(o.name)?.toLowerCase() === "user") return { id, role: "user", body };
    if (readString(o.name)?.toLowerCase() === "assistant") return { id, role: "assistant", body };
    return { id, role: "unknown", body };
  }

  return { id, role: "unknown", body: JSON.stringify(o, null, 2) };
}

/**
 * Produces 0+ lines. Empty array means “no list-shaped messages”; caller may still show raw JSON.
 */
export function parseCursorConversationToLines(conversation: unknown): CursorTranscriptLine[] {
  const arr = normalizeToMessageArray(conversation);
  if (arr.length === 0) return [];
  return arr.map((m, i) => messageObjectToLine(m, i));
}
