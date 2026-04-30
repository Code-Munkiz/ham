import crypto from "node:crypto";

import { Agent } from "@cursor/sdk";

function nowIso() {
  return new Date().toISOString();
}

function stableEventId(agentId, runId, kind, message, fallbackIndex) {
  const seed = `${agentId}|${runId}|${kind}|${message}|${fallbackIndex}`;
  return `sdk_${crypto.createHash("sha1").update(seed).digest("hex").slice(0, 16)}`;
}

function emit(obj) {
  process.stdout.write(`${JSON.stringify(obj)}\n`);
}

function normalizeKind(t) {
  const m = {
    assistant: "assistant_message",
    tool_call: "tool_event",
    thinking: "thinking",
    status: "status",
  };
  return m[String(t || "").trim()] || "status";
}

function messageFromSdkEvent(event) {
  if (!event || typeof event !== "object") return "";
  if (event.type === "assistant") {
    const parts = [];
    for (const block of event?.message?.content || []) {
      if (block?.type === "text" && block?.text) parts.push(String(block.text));
    }
    return parts.join("");
  }
  if (event.type === "thinking") {
    return String(event.text || event.message || "");
  }
  if (event.type === "tool_call") {
    return String(event?.tool_call?.name || event.name || "tool_call");
  }
  return String(event.message || event.text || event.type || "event");
}

async function readPayload() {
  const chunks = [];
  for await (const c of process.stdin) chunks.push(c);
  const raw = Buffer.concat(chunks).toString("utf8").trim();
  if (!raw) return {};
  return JSON.parse(raw);
}

async function main() {
  const apiKey = String(process.env.CURSOR_API_KEY || "").trim();
  if (!apiKey) {
    throw new Error("CURSOR_API_KEY is required");
  }

  const payload = await readPayload();
  const mode = String(payload.mode || "stream_existing_run");
  if (mode !== "stream_existing_run") {
    throw new Error(`Unsupported mode: ${mode}`);
  }

  const agentId = String(payload.agent_id || "").trim();
  if (!agentId) throw new Error("agent_id is required");
  let runId = String(payload.run_id || "").trim() || null;

  const maxSeconds = Number(payload.max_seconds || 30);
  const started = Date.now();
  let idx = 0;
  let timedOut = false;

  const agent = await Agent.resume(agentId, { apiKey });
  if (!runId) {
    const runs = await Agent.listRuns(agentId, { runtime: "cloud", apiKey, limit: 1 });
    const first = Array.isArray(runs?.items) ? runs.items[0] : null;
    runId = first?.id ? String(first.id) : null;
  }
  if (!runId) {
    throw new Error("No run_id resolved for this agent");
  }

  const run = await Agent.getRun(runId, { runtime: "cloud", apiKey, agentId });
  for await (const ev of run.stream()) {
    if ((Date.now() - started) / 1000 > maxSeconds) {
      timedOut = true;
      emit({
        provider: "cursor",
        agent_id: agentId,
        run_id: runId,
        event_id: stableEventId(agentId, runId, "error", "bridge_timeout", idx++),
        kind: "error",
        message: "sdk_bridge_timeout",
        time: nowIso(),
        metadata: { reason: "max_seconds_exceeded" },
      });
      break;
    }
    const t = String(ev?.type || "status");
    const kind = normalizeKind(t);
    const message = messageFromSdkEvent(ev);
    emit({
      provider: "cursor",
      agent_id: String(ev?.agent_id || ev?.agentId || agentId),
      run_id: String(ev?.run_id || ev?.runId || runId),
      event_id: stableEventId(agentId, runId, kind, message, idx++),
      kind,
      message,
      time: nowIso(),
      metadata: { sdk_type: t },
    });
  }

  if (timedOut) {
    // Bounded chunk complete: exit without waiting for the run — Python may reconnect.
    process.exitCode = 0;
    return;
  }

  const result = await run.wait();
  const status = String(result?.status || "finished");
  emit({
    provider: "cursor",
    agent_id: agentId,
    run_id: runId,
    event_id: stableEventId(agentId, runId, "completed", status, idx++),
    kind: "completed",
    message: status,
    time: nowIso(),
    metadata: { status },
  });

  for (const b of result?.git?.branches || []) {
    const prUrl = String(b?.prUrl || "").trim();
    if (!prUrl) continue;
    emit({
      provider: "cursor",
      agent_id: agentId,
      run_id: runId,
      event_id: stableEventId(agentId, runId, "pr_url", prUrl, idx++),
      kind: "pr_url",
      message: prUrl,
      time: nowIso(),
      metadata: { repoUrl: b?.repoUrl || null, branch: b?.branch || null },
    });
  }

  const artifacts = await agent.listArtifacts().catch(() => []);
  for (const a of Array.isArray(artifacts) ? artifacts : []) {
    emit({
      provider: "cursor",
      agent_id: agentId,
      run_id: runId,
      event_id: stableEventId(agentId, runId, "artifact", String(a?.path || "artifact"), idx++),
      kind: "artifact",
      message: String(a?.path || "artifact"),
      time: nowIso(),
      metadata: { sizeBytes: a?.sizeBytes ?? null, updatedAt: a?.updatedAt ?? null },
    });
  }
}

await main();
