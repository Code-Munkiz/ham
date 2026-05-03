import { describe, expect, it, vi } from "vitest";

import {
  isLocalContextEnginePayload,
  loadContextMemorySnapshot,
  shouldGateContextMemorySettingsMutations,
} from "../contextMemorySnapshotLoadPlan";
import type { ContextEnginePayload } from "@/lib/ham/types";

const basePayload = (cwd: string): ContextEnginePayload => ({
  cwd,
  current_date: "",
  platform_info: "",
  file_count: 0,
  instruction_file_count: 0,
  instruction_files: [],
  config_sources: [],
  memory_heist_section: {},
  session_memory: {
    compact_max_tokens: 8000,
    compact_preserve: 4,
    tool_prune_chars: 200,
    tool_prune_placeholder: "",
  },
  module_defaults: {
    max_instruction_file_chars: 4000,
    max_total_instruction_chars: 12000,
    max_diff_chars: 8000,
  },
  roles: {
    architect: { instruction_budget_chars: 1, max_diff_chars: 1, rendered_chars: 0 },
    commander: { instruction_budget_chars: 1, max_diff_chars: 1, rendered_chars: 0 },
    critic: { instruction_budget_chars: 1, max_diff_chars: 1, rendered_chars: 0 },
  },
  git: { status_chars: 0, diff_chars: 0, log_chars: 0, has_repo: false },
});

describe("loadContextMemorySnapshot", () => {
  it("prefers local snapshot when runtime is configured, health ok, and workspace root is configured", async () => {
    const localCwd = "/explicit/local/root";
    const deps = {
      isLocalRuntimeConfigured: () => true,
      fetchLocalWorkspaceHealth: vi.fn().mockResolvedValue({ ok: true, workspaceRootConfigured: true }),
      fetchLocalWorkspaceContextSnapshot: vi.fn().mockResolvedValue({ ...basePayload(localCwd), context_source: "local" }),
      fetchProjectContextEngine: vi.fn(),
      fetchContextEngine: vi.fn(),
    };
    const out = await loadContextMemorySnapshot("proj-1", deps);
    expect(out.source).toBe("local");
    expect(out.payload.cwd).toBe(localCwd);
    expect(out.payload.context_source).toBe("local");
    expect(out.fallbackNote).toBeNull();
    expect(deps.fetchProjectContextEngine).not.toHaveBeenCalled();
    expect(deps.fetchContextEngine).not.toHaveBeenCalled();
  });

  it("falls back to cloud when local runtime is not configured", async () => {
    const cloudCwd = "/cloud/cwd";
    const deps = {
      isLocalRuntimeConfigured: () => false,
      fetchLocalWorkspaceHealth: vi.fn(),
      fetchLocalWorkspaceContextSnapshot: vi.fn(),
      fetchProjectContextEngine: vi.fn().mockResolvedValue(basePayload(cloudCwd)),
      fetchContextEngine: vi.fn(),
    };
    const out = await loadContextMemorySnapshot("p2", deps);
    expect(out.source).toBe("project");
    expect(out.payload.context_source).toBe("cloud");
    expect(deps.fetchLocalWorkspaceHealth).not.toHaveBeenCalled();
    expect(deps.fetchLocalWorkspaceContextSnapshot).not.toHaveBeenCalled();
  });

  it("falls back to cloud when workspace root is not configured on local API", async () => {
    const cloudCwd = "/cloud/global";
    const deps = {
      isLocalRuntimeConfigured: () => true,
      fetchLocalWorkspaceHealth: vi.fn().mockResolvedValue({ ok: true, workspaceRootConfigured: false }),
      fetchLocalWorkspaceContextSnapshot: vi.fn(),
      fetchProjectContextEngine: vi.fn().mockRejectedValue(new Error("no project")),
      fetchContextEngine: vi.fn().mockResolvedValue(basePayload(cloudCwd)),
    };
    const out = await loadContextMemorySnapshot(null, deps);
    expect(out.source).toBe("global");
    expect(out.payload.context_source).toBe("cloud");
    expect(deps.fetchLocalWorkspaceContextSnapshot).not.toHaveBeenCalled();
  });

  it("falls back to cloud when local snapshot fails", async () => {
    const cloudCwd = "/after/fallback";
    const deps = {
      isLocalRuntimeConfigured: () => true,
      fetchLocalWorkspaceHealth: vi.fn().mockResolvedValue({ ok: true, workspaceRootConfigured: true }),
      fetchLocalWorkspaceContextSnapshot: vi.fn().mockRejectedValue(new Error("503")),
      fetchProjectContextEngine: vi.fn(),
      fetchContextEngine: vi.fn().mockResolvedValue(basePayload(cloudCwd)),
    };
    const out = await loadContextMemorySnapshot(null, deps);
    expect(out.source).toBe("global");
    expect(out.fallbackNote).toContain("This computer did not return");
    expect(out.payload.cwd).toBe(cloudCwd);
  });
});

describe("shouldGateContextMemorySettingsMutations", () => {
  it("gates when source is local", () => {
    expect(shouldGateContextMemorySettingsMutations("local")).toBe(true);
  });
  it("does not gate for cloud sources", () => {
    expect(shouldGateContextMemorySettingsMutations("project")).toBe(false);
    expect(shouldGateContextMemorySettingsMutations("global")).toBe(false);
    expect(shouldGateContextMemorySettingsMutations(null)).toBe(false);
  });
});

describe("isLocalContextEnginePayload", () => {
  it("detects local context_source", () => {
    expect(isLocalContextEnginePayload({ ...basePayload("/x"), context_source: "local" })).toBe(true);
    expect(isLocalContextEnginePayload({ ...basePayload("/x"), context_source: "cloud" })).toBe(false);
    expect(isLocalContextEnginePayload(null)).toBe(false);
  });
});
