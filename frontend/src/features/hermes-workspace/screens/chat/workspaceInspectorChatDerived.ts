/**
 * Read-only Inspector summaries for Workspace chat: file mentions in transcript + composer queue,
 * and structured signals from assistant UI actions / operator results (no fake rows).
 */
import type { HamOperatorResult, HamUiAction } from "@/lib/ham/api";
import { tryParseHamChatUserV1String } from "@/lib/ham/chatUserContent";
import {
  formatAttachmentByteSize,
  type WorkspaceComposerAttachment,
} from "./composerAttachmentHelpers";
import type { HwwMsgRow } from "./WorkspaceChatMessageList";

const MAX_ARTIFACT_ROWS = 40;

const RE_ATT_IMAGE = /\[Attached image:\s*([^\]]+?)\s*\(([^)]+)\)\]/g;
const RE_ATT_FILE = /\[Attached file:\s*([^\]]+?)\s*\(([^)]+)\)\]/g;
const RE_ATT_BINARY = /\[Attached:\s*([^(]+?)\s*\(([^)]+)\)\s*—/g;

export type ChatInspectorFileRow = {
  id: string;
  name: string;
  sizeLabel: string;
  kindLabel: string;
  source: "queued_in_composer" | "transcript";
  atLabel?: string;
};

export type ChatInspectorArtifactRow = {
  id: string;
  atIso: string;
  title: string;
  typeLabel: string;
  source: string;
  status: string;
  navigateTo?: string | null;
  detail?: string;
};

function truncate(s: string, max: number): string {
  const t = s.replace(/\s+/g, " ").trim();
  if (t.length <= max) return t;
  return `${t.slice(0, max - 1)}…`;
}

/** Paths we can offer as in-app links from Inspector (HashRouter workspace). */
export function workspaceInspectorSafeLink(path: string): string | null {
  const p = path.trim();
  if (!p.startsWith("/")) return null;
  if (p.startsWith("/workspace") || p === "/workspace") return p;
  return null;
}

export function composerAttachmentRows(attachments: WorkspaceComposerAttachment[]): ChatInspectorFileRow[] {
  return attachments
    .filter((a) => !a.error)
    .map((a) => ({
      id: `q-${a.id}`,
      name: a.name || "attachment",
      sizeLabel: formatAttachmentByteSize(a.size),
      kindLabel: a.kind,
      source: "queued_in_composer" as const,
    }));
}

export function extractTranscriptAttachmentRows(messages: HwwMsgRow[]): ChatInspectorFileRow[] {
  const out: ChatInspectorFileRow[] = [];
  const seen = new Set<string>();
  let seq = 0;

  const pushMatch = (nameRaw: string, sizeRaw: string, kindLabel: string, atLabel: string) => {
    const name = nameRaw.trim();
    const sizeLabel = sizeRaw.trim();
    if (!name) return;
    const key = `${name}\0${sizeLabel}\0${kindLabel}`;
    if (seen.has(key)) return;
    seen.add(key);
    seq += 1;
    out.push({
      id: `tx-${seq}-${name.slice(0, 24)}`,
      name,
      sizeLabel: sizeLabel || "—",
      kindLabel,
      source: "transcript",
      atLabel,
    });
  };

  for (const m of messages) {
    if (m.role !== "user") continue;
    const v1 = tryParseHamChatUserV1String(m.content);
    if (v1 && v1.images.length > 0) {
      for (const im of v1.images) {
        const name = (im.name || "screenshot").trim();
        if (!name) continue;
        const key = `${name}\0${im.mime}\0v1`;
        if (seen.has(key)) continue;
        seen.add(key);
        seq += 1;
        out.push({
          id: `tx-v1-${seq}-${name.slice(0, 24)}`,
          name,
          sizeLabel: "—",
          kindLabel: im.mime || "image",
          source: "transcript",
          atLabel: m.timestamp,
        });
      }
      continue;
    }
    const text = m.content;
    for (const match of text.matchAll(RE_ATT_IMAGE)) {
      pushMatch(match[1], match[2], "image", m.timestamp);
    }
    for (const match of text.matchAll(RE_ATT_FILE)) {
      pushMatch(match[1], match[2], "file", m.timestamp);
    }
    for (const match of text.matchAll(RE_ATT_BINARY)) {
      pushMatch(match[1], match[2], "binary", m.timestamp);
    }
  }
  return out;
}

function summarizeUiAction(a: HamUiAction): { title: string; typeLabel: string; navigateTo: string | null } {
  switch (a.type) {
    case "navigate":
      return { title: truncate(a.path, 56), typeLabel: "Navigate", navigateTo: workspaceInspectorSafeLink(a.path) };
    case "open_settings": {
      const tab = a.tab?.trim();
      return {
        title: tab ? `tab: ${tab}` : "Settings",
        typeLabel: "Open settings",
        navigateTo: tab
          ? `/workspace/settings?tab=${encodeURIComponent(tab)}`
          : "/workspace/settings",
      };
    }
    case "toast":
      return { title: truncate(a.message, 64), typeLabel: `Toast (${a.level})`, navigateTo: null };
    case "toggle_control_panel":
      return {
        title: a.open === undefined || a.open === null ? "Toggle panel" : a.open ? "Open panel" : "Close panel",
        typeLabel: "Control panel",
        navigateTo: null,
      };
    default:
      return { title: "UI action", typeLabel: "Unknown", navigateTo: null };
  }
}

export function mergeArtifactRowsAfterTurn(
  prev: ChatInspectorArtifactRow[],
  atIso: string,
  actions: HamUiAction[] | undefined,
  operatorResult: HamOperatorResult | null | undefined,
): ChatInspectorArtifactRow[] {
  const next = [...prev];
  let n = 0;
  for (const a of actions ?? []) {
    n += 1;
    const s = summarizeUiAction(a);
    next.push({
      id: `ui-${Date.now()}-${n}`,
      atIso,
      title: s.title,
      typeLabel: s.typeLabel,
      source: "ui_action",
      status: "applied",
      navigateTo: s.navigateTo,
    });
  }

  if (operatorResult) {
    const hasSignal =
      operatorResult.handled === true ||
      Boolean(operatorResult.intent?.trim()) ||
      Boolean(operatorResult.blocking_reason?.trim()) ||
      operatorResult.ok === false;
    if (hasSignal) {
      const title = operatorResult.intent?.trim()
        ? truncate(`Intent: ${operatorResult.intent}`, 56)
        : operatorResult.handled
          ? "Operator handled request"
          : "Operator turn";
      next.push({
        id: `op-${Date.now()}`,
        atIso,
        title,
        typeLabel: "Operator",
        source: "assistant",
        status: operatorResult.ok ? "ok" : "blocked",
        navigateTo: null,
        detail: operatorResult.blocking_reason?.trim() || undefined,
      });
    }
  }

  return next.length > MAX_ARTIFACT_ROWS ? next.slice(-MAX_ARTIFACT_ROWS) : next;
}
