import { describe, expect, it } from "vitest";

import { knowledgeSettingsLinks, libraryNavItems, primaryRailItems } from "../workspaceNavConfig";

describe("workspaceNavConfig", () => {
  it("primary rail excludes Chat entry", () => {
    expect(primaryRailItems.map((i) => i.to)).not.toContain("/workspace/chat");
    expect(primaryRailItems.map((i) => i.label)).not.toContain("Chat");
  });

  it("primary rail is empty", () => {
    expect(primaryRailItems).toHaveLength(0);
  });

  it("primary rail does not list Builder Studio", () => {
    expect(primaryRailItems.every((item) => !item.to.startsWith("/workspace/builder-studio"))).toBe(
      true,
    );
    expect(primaryRailItems.every((item) => !/builder studio/i.test(item.label))).toBe(true);
  });

  it("library flyout lists Projects first", () => {
    expect(libraryNavItems[0]?.label).toBe("Projects");
    expect(libraryNavItems[0]?.to).toBe("/workspace/projects");
  });

  it("does not expose legacy social or hamgomoon nav entries", () => {
    const allItems = [...primaryRailItems, ...libraryNavItems, ...knowledgeSettingsLinks];
    expect(allItems.every((item) => item.label !== "Social")).toBe(true);
    expect(allItems.every((item) => item.label !== "HAMgomoon")).toBe(true);
    expect(allItems.every((item) => !item.to.startsWith("/workspace/social"))).toBe(true);
    expect(allItems.every((item) => !item.to.startsWith("/workspace/hamgomoon"))).toBe(true);
  });
});
