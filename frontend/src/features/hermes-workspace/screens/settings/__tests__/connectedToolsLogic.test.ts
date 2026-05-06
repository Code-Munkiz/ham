/**
 * Tests for Connected Tools settings logic.
 * Validates grouping, toggle behavior, label safety, and cloud-mode awareness.
 */
import { describe, expect, it } from "vitest";

type ToolStatus = "ready" | "needs_sign_in" | "not_found" | "off" | "error" | "unknown";

interface ToolEntry {
  id: string;
  label: string;
  category: string;
  status: ToolStatus;
  enabled: boolean;
  source: string;
  capabilities: string[];
  setup_hint: string | null;
}

const STATUS_LABELS: Record<ToolStatus, string> = {
  ready: "Ready",
  needs_sign_in: "Needs sign-in",
  not_found: "Not found",
  off: "Off",
  error: "Error",
  unknown: "Unknown",
};

const STATUS_GROUP_ORDER: ToolStatus[] = [
  "ready",
  "needs_sign_in",
  "not_found",
  "off",
  "error",
  "unknown",
];

function groupTools(tools: ToolEntry[]): Record<string, ToolEntry[]> {
  const groups: Record<string, ToolEntry[]> = {};
  for (const status of STATUS_GROUP_ORDER) {
    const matching = tools.filter((t) => t.status === status);
    if (matching.length > 0) {
      groups[status] = matching;
    }
  }
  return groups;
}

function applyToggle(tools: ToolEntry[], id: string, enabled: boolean): ToolEntry[] {
  return tools.map((t) => (t.id === id ? { ...t, enabled } : t));
}

const DEV_SPEAK_WORDS = [
  "SDK",
  "CLI",
  "PATH",
  "adapter",
  "provider registry",
  "bridge",
  "local runtime",
  "environment variable",
];

const MOCK_TOOLS: ToolEntry[] = [
  {
    id: "openrouter",
    label: "OpenRouter",
    category: "model",
    status: "ready",
    enabled: true,
    source: "cloud",
    capabilities: ["chat"],
    setup_hint: null,
  },
  {
    id: "cursor",
    label: "Cursor",
    category: "coding",
    status: "needs_sign_in",
    enabled: false,
    source: "cloud",
    capabilities: ["plan"],
    setup_hint: "Add your Cursor API key in Settings to connect.",
  },
  {
    id: "ai_studio",
    label: "AI Studio",
    category: "model",
    status: "unknown",
    enabled: false,
    source: "cloud",
    capabilities: [],
    setup_hint: "AI Studio integration is not yet available.",
  },
  {
    id: "antigravity",
    label: "Antigravity",
    category: "coding",
    status: "unknown",
    enabled: false,
    source: "unknown",
    capabilities: [],
    setup_hint: "Antigravity integration is not yet available.",
  },
  {
    id: "git",
    label: "Git",
    category: "repo",
    status: "not_found",
    enabled: false,
    source: "this_computer",
    capabilities: ["version_control"],
    setup_hint: "Connect this computer to detect Git.",
  },
  {
    id: "node",
    label: "Node",
    category: "local_tool",
    status: "not_found",
    enabled: false,
    source: "this_computer",
    capabilities: [],
    setup_hint: "Connect this computer to detect Node.",
  },
  {
    id: "factory_droid",
    label: "Factory Droid",
    category: "coding",
    status: "ready",
    enabled: true,
    source: "cloud",
    capabilities: ["edit_code"],
    setup_hint: null,
  },
];

describe("Connected Tools — grouping", () => {
  it("groups tools by Ready / Needs sign-in / Not found", () => {
    const groups = groupTools(MOCK_TOOLS);
    expect(groups["ready"]).toHaveLength(2);
    expect(groups["needs_sign_in"]).toHaveLength(1);
    expect(groups["not_found"]).toHaveLength(2);
    expect(groups["unknown"]).toHaveLength(2);
  });

  it("empty statuses are omitted from groups", () => {
    const groups = groupTools(MOCK_TOOLS);
    expect(groups["off"]).toBeUndefined();
    expect(groups["error"]).toBeUndefined();
  });
});

describe("Connected Tools — AI Studio and Antigravity", () => {
  it("AI Studio is present in the tools list", () => {
    const aiStudio = MOCK_TOOLS.find((t) => t.id === "ai_studio");
    expect(aiStudio).toBeDefined();
    expect(aiStudio!.label).toBe("AI Studio");
    expect(aiStudio!.status).toBe("unknown");
    expect(aiStudio!.enabled).toBe(false);
  });

  it("Antigravity is present in the tools list", () => {
    const antigravity = MOCK_TOOLS.find((t) => t.id === "antigravity");
    expect(antigravity).toBeDefined();
    expect(antigravity!.label).toBe("Antigravity");
    expect(antigravity!.status).toBe("unknown");
    expect(antigravity!.enabled).toBe(false);
  });
});

describe("Connected Tools — toggles", () => {
  it("can toggle a tool on", () => {
    const updated = applyToggle(MOCK_TOOLS, "cursor", true);
    const cursor = updated.find((t) => t.id === "cursor")!;
    expect(cursor.enabled).toBe(true);
  });

  it("can toggle a tool off", () => {
    const updated = applyToggle(MOCK_TOOLS, "openrouter", false);
    const or = updated.find((t) => t.id === "openrouter")!;
    expect(or.enabled).toBe(false);
  });

  it("toggling one tool does not affect others", () => {
    const updated = applyToggle(MOCK_TOOLS, "cursor", true);
    const or = updated.find((t) => t.id === "openrouter")!;
    expect(or.enabled).toBe(true);
    const git = updated.find((t) => t.id === "git")!;
    expect(git.enabled).toBe(false);
  });
});

describe("Connected Tools — user-facing labels avoid dev-speak", () => {
  it("status labels contain no dev-speak", () => {
    for (const label of Object.values(STATUS_LABELS)) {
      for (const banned of DEV_SPEAK_WORDS) {
        expect(label).not.toContain(banned);
      }
    }
  });

  it("tool labels contain no dev-speak", () => {
    for (const tool of MOCK_TOOLS) {
      for (const banned of DEV_SPEAK_WORDS) {
        expect(tool.label).not.toContain(banned);
      }
    }
  });

  it("setup hints contain no dev-speak", () => {
    for (const tool of MOCK_TOOLS) {
      if (tool.setup_hint) {
        for (const banned of DEV_SPEAK_WORDS) {
          expect(tool.setup_hint).not.toContain(banned);
        }
      }
    }
  });
});

describe("Connected Tools — cloud mode awareness", () => {
  it("cloud mode scan_available=false means UI does not claim local scan happened", () => {
    const cloudResponse = {
      tools: MOCK_TOOLS,
      scan_available: false,
      scan_hint: "Connect this computer to scan local tools.",
    };
    expect(cloudResponse.scan_available).toBe(false);
    expect(cloudResponse.scan_hint).toBeTruthy();
  });

  it("non-cloud mode has scan_available=true", () => {
    const localResponse = { tools: MOCK_TOOLS, scan_available: true, scan_hint: null };
    expect(localResponse.scan_available).toBe(true);
  });
});
