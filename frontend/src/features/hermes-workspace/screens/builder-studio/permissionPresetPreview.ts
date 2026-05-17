import type { PermissionPreset } from "./builderStudioLabels";

const PRESET_PREVIEW: Record<PermissionPreset, string> = {
  safe_docs: "Can edit docs only. Cannot delete. No network. Asks before changes.",
  app_build: "Can build and edit. Deletes need review. May ask for shell and install.",
  bug_fix: "Can edit existing files. Won't add new dirs. Deletes need review.",
  refactor: "Can edit and create. No shell or network. Deletes need review.",
  game_build: "Can build and edit. Deletes need review. May ask for shell and install. No network.",
  test_write: "Can edit tests only. Cannot delete. May ask for shell.",
  readonly_analyst: "Read only. Cannot edit, create, or delete. Always asks.",
  custom:
    "Advanced. Same safety floor as App Builder (deletes need review), with your scopes added.",
};

export function permissionPresetPreview(preset: PermissionPreset): string {
  return PRESET_PREVIEW[preset];
}
