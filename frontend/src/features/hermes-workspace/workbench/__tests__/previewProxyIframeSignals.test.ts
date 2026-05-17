import { describe, expect, it } from "vitest";
import { detectPreviewIframeProxySignals } from "../previewProxyIframeSignals";

describe("detectPreviewIframeProxySignals", () => {
  it("treats PREVIEW_PROXY JSON markers as warmup-like proxy issues", () => {
    const r = detectPreviewIframeProxySignals("PREVIEW_PROXY_WARMUP", "application/json; charset=utf-8");
    expect(r.previewProxyWarmupLike).toBe(true);
    expect(r.upstreamUnavailableMarked).toBe(false);
  });

  it("treats nginx-style 502 pages as warmup-like gateway issues", () => {
    const r = detectPreviewIframeProxySignals("502 Bad Gateway\nnginx", "text/html");
    expect(r.previewProxyWarmupLike).toBe(true);
    expect(r.upstreamUnavailableMarked).toBe(false);
  });

  it("does not treat normal app text as warmup-like", () => {
    const r = detectPreviewIframeProxySignals("Calculator\n7 8 9", "text/html");
    expect(r.previewProxyWarmupLike).toBe(false);
  });
});
