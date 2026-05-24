import { describe, expect, it } from "vitest";

import {
  knowledgeSettingsLinks,
  libraryNavItems,
  primaryRailItems,
  workspacePathTitle,
} from "../workspaceNavConfig";

describe("workspaceNavConfig", () => {
  it("primary rail excludes Chat entry", () => {
    expect(primaryRailItems.map((i) => i.to)).not.toContain("/workspace/chat");
    expect(primaryRailItems.map((i) => i.label)).not.toContain("Chat");
  });

  it("primary rail is empty after GoHAM Social extraction", () => {
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

  it("titles legacy social routes as moved", () => {
    expect(workspacePathTitle("/workspace/social")).toBe("Social (moved)");
    expect(workspacePathTitle("/workspace/social/anything")).toBe("Social (moved)");
  });

  it("does not expose a HAMgomoon nav entry", () => {
    const allItems = [...primaryRailItems, ...libraryNavItems, ...knowledgeSettingsLinks];
    expect(allItems.every((item) => item.label !== "HAMgomoon")).toBe(true);
    expect(allItems.every((item) => !item.to.startsWith("/workspace/hamgomoon"))).toBe(true);
  });
});
