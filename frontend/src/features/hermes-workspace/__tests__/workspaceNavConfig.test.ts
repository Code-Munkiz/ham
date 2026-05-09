import { describe, expect, it } from "vitest";

import { libraryNavItems, primaryRailItems } from "../workspaceNavConfig";

describe("workspaceNavConfig", () => {
  it("primary rail excludes Chat entry", () => {
    expect(primaryRailItems.map((i) => i.to)).not.toContain("/workspace/chat");
    expect(primaryRailItems.map((i) => i.label)).not.toContain("Chat");
  });

  it("primary rail orders Social then Coding agents", () => {
    expect(primaryRailItems[0]?.label).toBe("Social");
    expect(primaryRailItems[1]?.label).toBe("Coding agents");
  });

  it("library flyout lists Projects first", () => {
    expect(libraryNavItems[0]?.label).toBe("Projects");
    expect(libraryNavItems[0]?.to).toBe("/workspace/projects");
  });
});
