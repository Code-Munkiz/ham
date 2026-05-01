#!/usr/bin/env node
import { spawn } from "node:child_process";
import path from "node:path";
import { fileURLToPath } from "node:url";

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const frontendRoot = path.resolve(__dirname, "..");
const viteBin = path.resolve(frontendRoot, "node_modules", "vite", "bin", "vite.js");

const env = {
  ...process.env,
  BROWSER: process.env.BROWSER || "none",
  // Force proxy target for this run so stale .env.local values do not silently drift.
  VITE_HAM_API_PROXY_TARGET: process.env.VITE_HAM_API_PROXY_TARGET || "http://127.0.0.1:8000",
};

const args = [viteBin, "--port=3000", "--host=0.0.0.0", ...process.argv.slice(2)];

console.log("[dev:comfy] starting Vite with local Comfy profile");
console.log(`[dev:comfy] VITE_HAM_API_PROXY_TARGET=${env.VITE_HAM_API_PROXY_TARGET}`);

const child = spawn(process.execPath, args, {
  cwd: frontendRoot,
  env,
  stdio: "inherit",
});

child.on("exit", (code, signal) => {
  if (signal) {
    process.kill(process.pid, signal);
    return;
  }
  process.exit(code ?? 0);
});
