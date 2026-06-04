/** When true, workbench Preview shows operator tooling (diagnostics drawer, refresh, URLs). */
export function isWorkbenchOperatorUiEnabled(): boolean {
  return import.meta.env.VITE_HAM_WORKBENCH_OPERATOR_UI === "1";
}
