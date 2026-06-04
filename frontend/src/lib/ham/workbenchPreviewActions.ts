export const WORKBENCH_ASK_HAM_FIX_PREVIEW_EVENT = "hww-workbench-ask-ham-fix-preview";

export const WORKBENCH_ASK_HAM_FIX_PREVIEW_MESSAGE =
  "The preview didn't finish. Please fix the app and try building again.";

export function dispatchAskHamFixPreview(): void {
  window.dispatchEvent(new CustomEvent(WORKBENCH_ASK_HAM_FIX_PREVIEW_EVENT));
}
