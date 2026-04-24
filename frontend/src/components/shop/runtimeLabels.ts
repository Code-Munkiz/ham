import type { HermesRuntimeInventory } from "@/lib/ham/api";

export function cliTruth(inv: HermesRuntimeInventory, st: string): string {
  if (!inv.available) return "Unavailable";
  if (st === "ok") return "Live local";
  if (st === "requires_tty") return "Requires TTY";
  if (st === "error") return "Error";
  return "Unavailable";
}

export function configTruth(st: string): string {
  if (st === "ok") return "Config-backed";
  if (st === "missing") return "Unavailable";
  return "Error";
}

export function inventoryAvailabilityLabel(inv: HermesRuntimeInventory | null): string {
  if (!inv) return "Unavailable";
  if (!inv.available) return "Unavailable";
  return "Live local";
}

export function staticCatalogLabel(staticCatalog: boolean): string {
  return staticCatalog ? "Static catalog" : "Catalog (runtime)";
}
