'use strict';

/**
 * Phase 4A — validate navigation targets for desktop browser MVP (main-process BrowserWindow).
 * Allow only http(s). Optional loopback gated by policy.
 */

const LOOPBACK_HOSTS = new Set(['localhost', '127.0.0.1', '[::1]']);

function isLoopbackHost(hostname) {
  const h = String(hostname || '').toLowerCase();
  if (LOOPBACK_HOSTS.has(h)) return true;
  if (h.endsWith('.localhost')) return true;
  return false;
}

/**
 * @param {string} urlString
 * @param {{ allow_loopback: boolean }} opts
 * @returns {{ ok: true, href: string } | { ok: false, error: string }}
 */
function validateNavigateUrl(urlString, opts) {
  const raw = String(urlString || '').trim();
  if (!raw) return { ok: false, error: 'url_empty' };
  let u;
  try {
    u = new URL(raw);
  } catch {
    return { ok: false, error: 'url_invalid' };
  }
  const proto = u.protocol.toLowerCase();
  if (proto !== 'http:' && proto !== 'https:') {
    return { ok: false, error: 'scheme_not_allowed' };
  }
  if (!opts.allow_loopback && isLoopbackHost(u.hostname)) {
    return { ok: false, error: 'loopback_not_allowed' };
  }
  const href = `${u.protocol}//${u.host}${u.pathname}${u.search}`;
  return { ok: true, href };
}

/**
 * Strip query + hash for status IPC (reduce accidental secret leakage).
 * @param {string} href
 */
function safeDisplayUrl(href) {
  try {
    const u = new URL(href);
    return `${u.origin}${u.pathname}`;
  } catch {
    return '';
  }
}

module.exports = {
  validateNavigateUrl,
  safeDisplayUrl,
  isLoopbackHost,
};
