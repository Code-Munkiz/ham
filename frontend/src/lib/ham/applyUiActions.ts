import type { NavigateFunction } from "react-router-dom";
import { toast } from "sonner";

import { normalizeSettingsTabParam } from "@/components/workspace/UnifiedSettings";

import type { HamUiAction, HamWorkbenchViewMode } from "./api";

export function applyHamUiActions(
  actions: HamUiAction[],
  ctx: {
    navigate: NavigateFunction;
    setIsControlPanelOpen: (open: boolean) => void;
    isControlPanelOpen: boolean;
    setWorkbenchView: (mode: HamWorkbenchViewMode) => void;
    /** Optional – needed to activate the browser-only split variant. */
    setBrowserMode?: (active: boolean) => void;
  },
): void {
  for (const a of actions) {
    switch (a.type) {
      case "navigate":
        ctx.navigate(a.path);
        break;
      case "open_settings": {
        const tab = normalizeSettingsTabParam(a.tab ?? null);
        ctx.navigate(`/settings?tab=${encodeURIComponent(tab)}`);
        break;
      }
      case "toast": {
        const msg = a.message;
        switch (a.level) {
          case "success":
            toast.success(msg);
            break;
          case "error":
            toast.error(msg);
            break;
          case "warning":
            toast.warning(msg);
            break;
          default:
            toast.message(msg);
        }
        break;
      }
      case "toggle_control_panel":
        if (a.open === undefined || a.open === null) {
          ctx.setIsControlPanelOpen(!ctx.isControlPanelOpen);
        } else {
          ctx.setIsControlPanelOpen(a.open);
        }
        break;
      case "set_workbench_view":
        if (a.mode === "browser") {
          // Browser mode is a split variant with browser panel only
          ctx.setWorkbenchView("split");
          ctx.setBrowserMode?.(true);
        } else {
          ctx.setWorkbenchView(a.mode);
          ctx.setBrowserMode?.(false);
        }
        break;
      default:
        break;
    }
  }
}
