/**
 * HAM /api/workspace/skills — JSON-backed items + server-side Hermes static catalog
 * (same vendored data as /shop; no browser → Hermes VM / external hub).
 */

import type {
  HermesSkillCatalogEntryDetail,
  HermesSkillsCatalogResponse,
  HermesSkillsInstalledResponse,
} from "@/lib/ham/api";
import { hamApiFetch } from "@/lib/ham/api";

import { workspaceApiPending } from "../lib/workspaceHamApiState";

const BASE = "/api/workspace/skills";
/** Same catalog JSON as GET ${BASE}/hermes-catalog; available on older API builds before workspace routes shipped. */
const LEGACY_HERMES_CATALOG = "/api/hermes-skills/catalog";
const LEGACY_HERMES_CATALOG_ENTRY = (id: string) => `/api/hermes-skills/catalog/${encodeURIComponent(id)}`;
const LEGACY_HERMES_INSTALLED = "/api/hermes-skills/installed";

function withCatalogMeta(raw: HermesSkillsCatalogResponse): WorkspaceHermesCatalogListResponse {
  return {
    ...raw,
    readOnly: true,
    source: "hermes_static_catalog",
  };
}

export type WorkspaceSkill = {
  id: string;
  name: string;
  description: string;
  installed: boolean;
  enabled: boolean;
  config: string;
  createdAt: number;
  updatedAt: number;
};

export type SkillsBridge = { status: "ready" } | { status: "pending"; detail: string };

/** GET /api/workspace/skills/hermes-catalog — extends the hermes-skills catalog payload. */
export type WorkspaceHermesCatalogListResponse = HermesSkillsCatalogResponse & {
  readOnly: boolean;
  source: string;
};

export const workspaceSkillsAdapter = {
  description: "HAM /api/workspace/skills — list/create/patch/delete items",

  async list(q?: string): Promise<{ skills: WorkspaceSkill[]; bridge: SkillsBridge }> {
    try {
      const url = q?.trim() ? `${BASE}/items?q=${encodeURIComponent(q.trim())}` : `${BASE}/items`;
      const res = await hamApiFetch(url, { credentials: "include" });
      if (!res.ok) return { skills: [], bridge: workspaceApiPending("skills", res) };
      const data = (await res.json()) as { skills?: WorkspaceSkill[] };
      return { skills: Array.isArray(data.skills) ? data.skills : [], bridge: { status: "ready" } };
    } catch (e) {
      return { skills: [], bridge: workspaceApiPending("skills", null, e) };
    }
  },

  async create(
    name: string,
    description: string,
  ): Promise<{ skill: WorkspaceSkill | null; bridge: SkillsBridge; error?: string }> {
    try {
      const res = await hamApiFetch(`${BASE}/items`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        credentials: "include",
        body: JSON.stringify({ name, description: description || "" }),
      });
      if (!res.ok) return { skill: null, bridge: workspaceApiPending("skills", res), error: `HTTP ${res.status}` };
      return { skill: (await res.json()) as WorkspaceSkill, bridge: { status: "ready" } };
    } catch (e) {
      return { skill: null, bridge: workspaceApiPending("skills", null, e), error: e instanceof Error ? e.message : String(e) };
    }
  },

  async patch(
    id: string,
    body: Partial<{
      name: string;
      description: string;
      installed: boolean;
      enabled: boolean;
      config: string;
    }>,
  ): Promise<{ skill: WorkspaceSkill | null; bridge: SkillsBridge; error?: string }> {
    try {
      const res = await hamApiFetch(`${BASE}/items/${encodeURIComponent(id)}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        credentials: "include",
        body: JSON.stringify(body),
      });
      if (!res.ok) return { skill: null, bridge: workspaceApiPending("skills", res), error: `HTTP ${res.status}` };
      return { skill: (await res.json()) as WorkspaceSkill, bridge: { status: "ready" } };
    } catch (e) {
      return { skill: null, bridge: workspaceApiPending("skills", null, e), error: e instanceof Error ? e.message : String(e) };
    }
  },

  async remove(id: string): Promise<{ ok: boolean; bridge: SkillsBridge; error?: string }> {
    try {
      const res = await hamApiFetch(`${BASE}/items/${encodeURIComponent(id)}`, {
        method: "DELETE",
        credentials: "include",
      });
      if (res.status !== 204) return { ok: false, bridge: workspaceApiPending("skills", res), error: `HTTP ${res.status}` };
      return { ok: true, bridge: { status: "ready" } };
    } catch (e) {
      return { ok: false, bridge: workspaceApiPending("skills", null, e), error: e instanceof Error ? e.message : String(e) };
    }
  },

  /** Vendored Hermes runtime skills catalog (read-only, bundled JSON; same as /api/hermes-skills/catalog). */
  async hermesStaticCatalog(): Promise<{ data: WorkspaceHermesCatalogListResponse | null; bridge: SkillsBridge }> {
    try {
      const res = await hamApiFetch(`${BASE}/hermes-catalog`, { credentials: "include" });
      if (res.ok) {
        const data = (await res.json()) as WorkspaceHermesCatalogListResponse;
        return { data, bridge: { status: "ready" } };
      }
      if (res.status === 404) {
        const leg = await hamApiFetch(LEGACY_HERMES_CATALOG, { credentials: "include" });
        if (!leg.ok) return { data: null, bridge: workspaceApiPending("skills", leg) };
        const raw = (await leg.json()) as HermesSkillsCatalogResponse;
        return { data: withCatalogMeta(raw), bridge: { status: "ready" } };
      }
      return { data: null, bridge: workspaceApiPending("skills", res) };
    } catch (e) {
      return { data: null, bridge: workspaceApiPending("skills", null, e) };
    }
  },

  async hermesStaticCatalogEntry(
    catalogId: string,
  ): Promise<{ entry: HermesSkillCatalogEntryDetail | null; bridge: SkillsBridge; error?: string }> {
    try {
      const res = await hamApiFetch(`${BASE}/hermes-catalog/${encodeURIComponent(catalogId)}`, {
        credentials: "include",
      });
      if (res.ok) {
        const j = (await res.json()) as { entry?: HermesSkillCatalogEntryDetail };
        return { entry: j.entry ?? null, bridge: { status: "ready" } };
      }
      if (res.status === 404) {
        const leg = await hamApiFetch(LEGACY_HERMES_CATALOG_ENTRY(catalogId), { credentials: "include" });
        if (!leg.ok) return { entry: null, bridge: workspaceApiPending("skills", leg), error: `HTTP ${leg.status}` };
        const j = (await leg.json()) as { entry?: HermesSkillCatalogEntryDetail };
        return { entry: j.entry ?? null, bridge: { status: "ready" } };
      }
      return { entry: null, bridge: workspaceApiPending("skills", res), error: `HTTP ${res.status}` };
    } catch (e) {
      return { entry: null, bridge: workspaceApiPending("skills", null, e), error: e instanceof Error ? e.message : String(e) };
    }
  },

  /** Live overlay (read-only); same as GET /api/hermes-skills/installed. */
  async hermesLiveOverlay(): Promise<{ overlay: HermesSkillsInstalledResponse | null; bridge: SkillsBridge }> {
    try {
      const res = await hamApiFetch(`${BASE}/hermes-live-overlay`, { credentials: "include" });
      if (res.ok) {
        return { overlay: (await res.json()) as HermesSkillsInstalledResponse, bridge: { status: "ready" } };
      }
      if (res.status === 404) {
        const leg = await hamApiFetch(LEGACY_HERMES_INSTALLED, { credentials: "include" });
        if (!leg.ok) return { overlay: null, bridge: workspaceApiPending("skills", leg) };
        return { overlay: (await leg.json()) as HermesSkillsInstalledResponse, bridge: { status: "ready" } };
      }
      return { overlay: null, bridge: workspaceApiPending("skills", res) };
    } catch (e) {
      return { overlay: null, bridge: workspaceApiPending("skills", null, e) };
    }
  },
} as const;
