/**
 * GoHAM v1 safety classifier for bounded browser research.
 * It classifies candidate text / URLs only; it does not authorize new actions.
 */

import type { HamDesktopRealBrowserClickCandidate } from "@/lib/ham/desktopBundleBridge";

export type GohamSafetyCategory =
  | "safe"
  | "auth"
  | "account"
  | "checkout"
  | "download_upload"
  | "external_app"
  | "submit"
  | "permission_extension"
  | "unknown_risky";

export type GohamSafetyClassification = {
  category: GohamSafetyCategory;
  blocked: boolean;
  reason: string;
};

const AUTH_RE = /\b(sign\s*in|sign\s*up|log\s*in|login|register|create\s+account|continue\s+with\s+google)\b/iu;
const ACCOUNT_RE = /\b(account|profile|settings|dashboard|api\s*key|get\s+api\s+key|billing\s+portal)\b/iu;
const CHECKOUT_RE = /\b(checkout|payment|pay|billing|cart|subscribe|buy\s+now|purchase|invoice|credit\s*card)\b/iu;
const DOWNLOAD_UPLOAD_RE = /\b(download|upload|choose\s+file|attach\s+file|import|export)\b/iu;
const SUBMIT_RE = /\b(submit|send|post|publish|save\s+changes|confirm|authorize|allow)\b/iu;
const PERMISSION_RE = /\b(permission|extension|install\s+extension|add\s+to\s+chrome|allow access)\b/iu;
const EXTERNAL_SCHEME_RE = /^(mailto|tel|sms|intent|file|data|javascript|chrome|chrome-extension):/iu;

function textBlob(candidate: HamDesktopRealBrowserClickCandidate): string {
  return `${candidate.text || ""} ${candidate.role ?? ""} ${candidate.tag || ""}`.replace(/\s+/gu, " ").trim();
}

function classifyText(text: string): GohamSafetyClassification {
  if (AUTH_RE.test(text)) return { category: "auth", blocked: true, reason: "login or sign-up area" };
  if (CHECKOUT_RE.test(text)) return { category: "checkout", blocked: true, reason: "checkout/payment/billing area" };
  if (DOWNLOAD_UPLOAD_RE.test(text)) return { category: "download_upload", blocked: true, reason: "download/upload action" };
  if (PERMISSION_RE.test(text)) return { category: "permission_extension", blocked: true, reason: "permission or extension prompt" };
  if (SUBMIT_RE.test(text)) return { category: "submit", blocked: true, reason: "submit/send/post style action" };
  if (ACCOUNT_RE.test(text)) return { category: "account", blocked: true, reason: "account/settings/API-key area" };
  return { category: "safe", blocked: false, reason: "safe candidate" };
}

export function classifyGohamUrl(url: string | null | undefined): GohamSafetyClassification {
  const raw = String(url || "").trim();
  if (!raw) return { category: "safe", blocked: false, reason: "safe candidate" };
  try {
    const u = new URL(raw);
    if (EXTERNAL_SCHEME_RE.test(u.protocol)) {
      return { category: "external_app", blocked: true, reason: "external app or unsafe URL scheme" };
    }
    return classifyText(`${u.hostname} ${u.pathname}`);
  } catch {
    if (EXTERNAL_SCHEME_RE.test(raw)) {
      return { category: "external_app", blocked: true, reason: "external app or unsafe URL scheme" };
    }
    return { category: "safe", blocked: false, reason: "safe candidate" };
  }
}

export function classifyGohamCandidate(candidate: HamDesktopRealBrowserClickCandidate): GohamSafetyClassification {
  if (candidate.risk !== "low") {
    return { category: "unknown_risky", blocked: true, reason: "candidate marked risky by browser guard" };
  }
  return classifyText(textBlob(candidate));
}
