import { describe, expect, it } from "vitest";

import { libraryNavItems, primaryRailItems } from "../workspaceNavConfig";

describe("workspaceNavConfig", () => {
  it("primary rail excludes Chat entry", () => {
    expect(primaryRailItems.map((i) => i.to)).not.toContain("/workspace/chat");
    expect(primaryRailItems.map((i) => i.label)).not.toContain("Chat");
  });

  it("primary rail contains only Social", () => {
    expect(primaryRailItems).toHaveLength(1);
    expect(primaryRailItems[0]?.label).toBe("Social");
    expect(primaryRailItems[0]?.to).toBe("/workspace/social");
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
});
