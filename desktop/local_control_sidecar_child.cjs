"use strict";

/**
 * Desktop Local Control Phase 3B — inert sidecar child (stdio only).
 * No network listener, no filesystem I/O, no tools, no automation.
 * Responds to: health, status, shutdown (unknown methods → error).
 */

const ALLOWED = new Set(["health", "status", "shutdown"]);

const CAPABILITIES = {
  browser_automation: "not_implemented",
  filesystem_access: "not_implemented",
  shell_commands: "not_implemented",
  app_window_control: "not_implemented",
  mcp_adapters: "not_implemented",
};

function writeLine(obj) {
  process.stdout.write(`${JSON.stringify(obj)}\n`);
}

function handleRequest(raw) {
  let req;
  try {
    req = JSON.parse(raw);
  } catch {
    writeLine({ ok: false, error: "invalid_json" });
    return;
  }
  if (!req || typeof req !== "object" || Array.isArray(req)) {
    writeLine({ ok: false, error: "invalid_request" });
    return;
  }
  const method = req.method;
  const id = req.id !== undefined && req.id !== null ? req.id : null;
  if (typeof method !== "string" || !ALLOWED.has(method)) {
    writeLine({
      ok: false,
      error: "method_not_allowed",
      method: typeof method === "string" ? method : null,
      id,
    });
    return;
  }

  if (method === "health") {
    writeLine({
      ok: true,
      id,
      method: "health",
      result: { status: "ok", inert: true },
    });
    return;
  }

  if (method === "status") {
    writeLine({
      ok: true,
      id,
      method: "status",
      result: {
        mode: "inert_process_shell",
        inbound_network: false,
        droid_access: "not_enabled",
        capabilities: { ...CAPABILITIES },
      },
    });
    return;
  }

  if (method === "shutdown") {
    writeLine({
      ok: true,
      id,
      method: "shutdown",
      result: { stopping: true },
    });
    setImmediate(() => process.exit(0));
  }
}

let buf = "";
process.stdin.setEncoding("utf8");
process.stdin.on("data", (chunk) => {
  buf += chunk;
  let i;
  while ((i = buf.indexOf("\n")) >= 0) {
    const line = buf.slice(0, i).trim();
    buf = buf.slice(i + 1);
    if (line.length === 0) continue;
    handleRequest(line);
  }
});

process.stdin.on("end", () => {
  process.exit(0);
});
