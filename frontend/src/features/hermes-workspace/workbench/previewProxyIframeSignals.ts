/**
 * Infer whether an iframe navigation body looks like a preview-proxy warmup / gateway issue
 * (JSON PREVIEW_PROXY errors, nginx 502 pages, …) versus a loaded app bundle.
 */

export type PreviewIframeProxySignal = {
  /** Treat like preview-proxy warmup: apply strike counter + backoff, do not reset to "healthy". */
  previewProxyWarmupLike: boolean;
  /** JSON body signaled upstream unavailable — may map to terminal failure when runtime is READY. */
  upstreamUnavailableMarked: boolean;
};

export function detectPreviewIframeProxySignals(
  frameText: string,
  contentType: string,
): PreviewIframeProxySignal {
  const text = frameText.trim();
  const ct = (contentType || "").toLowerCase();
  const upper = text.slice(0, 2000).toUpperCase();

  const proxyJsonOrMarker =
    /PREVIEW_PROXY_[A-Z_]+/.test(text) ||
    (ct.includes("application/json") &&
      (upper.includes("PREVIEW_PROXY_") || /\bupstream is unavailable\b/i.test(text)));

  const nginxStyle502 =
    /\b502\b/.test(text) ||
    /\bbad\s+gateway\b/i.test(text) ||
    /\bgateway\s+time-?out\b/i.test(text) ||
    /\bupstream\s+prematurely\s+closed\s+connection\b/i.test(text);

  const warmupLike = Boolean(proxyJsonOrMarker || nginxStyle502);

  const upstreamUnavailableMarked =
    /PREVIEW_PROXY_UPSTREAM_UNAVAILABLE/i.test(text) ||
    (ct.includes("application/json") && upper.includes("PREVIEW_PROXY_UPSTREAM_UNAVAILABLE"));

  return { previewProxyWarmupLike: warmupLike, upstreamUnavailableMarked };
}
