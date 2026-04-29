'use strict';

const crypto = require('node:crypto');

const DEFAULT_PAIRING_CODE_TTL_MS = 120_000;
const DEFAULT_TOKEN_TTL_MS = 900_000;
const DEFAULT_EXCHANGE_FAIL_WINDOW_MS = 60_000;
const DEFAULT_EXCHANGE_FAIL_MAX = 8;
const MIN_PAIRING_CODE_TTL_MS = 30_000;
const MAX_PAIRING_CODE_TTL_MS = 600_000;

function nowMsDefault() {
  return Date.now();
}

function randomHex(bytes) {
  return crypto.randomBytes(bytes).toString('hex');
}

function sessionId() {
  return `pair_sess_${randomHex(8)}`;
}

function pairingCode() {
  const a = crypto.randomInt(0, 1000).toString().padStart(3, '0');
  const b = crypto.randomInt(0, 1000).toString().padStart(3, '0');
  return `${a}-${b}`;
}

function ensureArrayMap(map, key) {
  if (!map.has(key)) map.set(key, []);
  return map.get(key);
}

function clampPairingCodeTtlMs(valueMs) {
  if (!Number.isFinite(Number(valueMs))) return DEFAULT_PAIRING_CODE_TTL_MS;
  const n = Math.floor(Number(valueMs));
  if (n < MIN_PAIRING_CODE_TTL_MS) return MIN_PAIRING_CODE_TTL_MS;
  if (n > MAX_PAIRING_CODE_TTL_MS) return MAX_PAIRING_CODE_TTL_MS;
  return n;
}

/**
 * In-memory pairing/session store for local web bridge.
 * No disk persistence in MVP by design.
 */
function createWebBridgePairingStore(opts = {}) {
  const nowMs = typeof opts.nowMs === 'function' ? opts.nowMs : nowMsDefault;
  const emitAudit = typeof opts.emitAudit === 'function' ? opts.emitAudit : () => {};
  let pairCodeTtlMsCurrent = clampPairingCodeTtlMs(opts.pairCodeTtlMs);
  const tokenTtlMs = Number(opts.tokenTtlMs) > 0 ? Number(opts.tokenTtlMs) : DEFAULT_TOKEN_TTL_MS;
  const failWindowMs =
    Number(opts.failWindowMs) > 0 ? Number(opts.failWindowMs) : DEFAULT_EXCHANGE_FAIL_WINDOW_MS;
  const failMax = Number(opts.failMax) > 0 ? Number(opts.failMax) : DEFAULT_EXCHANGE_FAIL_MAX;

  /** @type {Map<string, { expiresAt: number, used: boolean, sessionId: string }>} */
  const codes = new Map();
  /** @type {Map<string, { sessionId: string, origin: string, expiresAt: number, revoked: boolean, scopes: string[] }>} */
  const tokens = new Map();
  /** @type {Map<string, number[]>} */
  const failures = new Map();

  function prune() {
    const now = nowMs();
    for (const [code, row] of codes) {
      if (row.used) codes.delete(code);
    }
    for (const [tok, row] of tokens) {
      if (row.expiresAt <= now || row.revoked) tokens.delete(tok);
    }
    for (const [key, arr] of failures) {
      const kept = arr.filter((ts) => now - ts <= failWindowMs);
      if (kept.length) failures.set(key, kept);
      else failures.delete(key);
    }
  }

  function issuePairingCode() {
    prune();
    let code = pairingCode();
    let guard = 0;
    while (codes.has(code) && guard < 8) {
      code = pairingCode();
      guard += 1;
    }
    const sid = sessionId();
    const expiresAt = nowMs() + pairCodeTtlMsCurrent;
    codes.set(code, { expiresAt, used: false, sessionId: sid });
    emitAudit({ event: 'pairing_code_created', session_id: sid, expires_at_ms: expiresAt });
    return { code, session_id: sid, expires_at_ms: expiresAt };
  }

  function recordFailure(origin, reason) {
    const key = String(origin || 'unknown').trim() || 'unknown';
    const arr = ensureArrayMap(failures, key);
    arr.push(nowMs());
    emitAudit({ event: 'pairing_exchange_failure', origin: key, reason_code: reason });
  }

  function tooManyFailures(origin) {
    const key = String(origin || 'unknown').trim() || 'unknown';
    const arr = failures.get(key);
    if (!arr || !arr.length) return false;
    return arr.length >= failMax;
  }

  function exchangePairingCode({ pairing_code, requested_origin, client_nonce }) {
    prune();
    const origin = String(requested_origin || '').trim();
    emitAudit({
      event: 'pairing_exchange_attempt',
      origin,
      client_nonce: String(client_nonce || '').slice(0, 64),
    });
    if (tooManyFailures(origin)) {
      recordFailure(origin, 'pairing_rate_limited');
      return { ok: false, reason_code: 'pairing_rate_limited' };
    }

    const code = String(pairing_code || '').trim();
    if (!code || !codes.has(code)) {
      recordFailure(origin, 'pairing_code_invalid');
      return { ok: false, reason_code: 'pairing_code_invalid' };
    }
    const row = codes.get(code);
    const now = nowMs();
    if (row.used) {
      codes.delete(code);
      recordFailure(origin, 'pairing_code_already_used');
      return { ok: false, reason_code: 'pairing_code_already_used' };
    }
    if (row.expiresAt <= now) {
      codes.delete(code);
      recordFailure(origin, 'pairing_code_expired');
      return { ok: false, reason_code: 'pairing_code_expired' };
    }

    row.used = true;
    codes.set(code, row);
    const tok = randomHex(24);
    const expiresAt = now + tokenTtlMs;
    const sessionIdValue = row.sessionId;
    const scopes = ['status.read', 'browser.intent', 'machine.escalation.request'];
    tokens.set(tok, {
      sessionId: sessionIdValue,
      origin,
      expiresAt,
      revoked: false,
      scopes,
    });
    failures.delete(origin);
    emitAudit({
      event: 'pairing_exchange_success',
      session_id: sessionIdValue,
      origin,
      expires_at_ms: expiresAt,
    });
    return {
      ok: true,
      access_token: tok,
      expires_in_sec: Math.floor(tokenTtlMs / 1000),
      session_id: sessionIdValue,
      scopes,
    };
  }

  function validateToken({ token, origin, requiredScope }) {
    prune();
    const tok = String(token || '').trim();
    if (!tok) return { ok: false, reason_code: 'token_missing' };
    if (!tokens.has(tok)) return { ok: false, reason_code: 'token_invalid' };
    const row = tokens.get(tok);
    const now = nowMs();
    if (row.revoked) {
      tokens.delete(tok);
      return { ok: false, reason_code: 'token_revoked' };
    }
    if (row.expiresAt <= now) {
      tokens.delete(tok);
      return { ok: false, reason_code: 'token_expired' };
    }
    if (String(origin || '').trim() !== row.origin) {
      return { ok: false, reason_code: 'origin_mismatch' };
    }
    if (requiredScope && !row.scopes.includes(requiredScope)) {
      return { ok: false, reason_code: 'scope_denied' };
    }
    return { ok: true, session_id: row.sessionId, scopes: [...row.scopes] };
  }

  function revokeToken(token) {
    prune();
    const tok = String(token || '').trim();
    if (!tok || !tokens.has(tok)) return false;
    const row = tokens.get(tok);
    row.revoked = true;
    tokens.set(tok, row);
    emitAudit({ event: 'token_revoked', session_id: row.sessionId, origin: row.origin });
    tokens.delete(tok);
    return true;
  }

  function revokeAll() {
    let count = 0;
    for (const tok of tokens.keys()) {
      if (revokeToken(tok)) count += 1;
    }
    return count;
  }

  function isPairedForOrigin(origin) {
    prune();
    const o = String(origin || '').trim();
    if (!o) return false;
    for (const row of tokens.values()) {
      if (!row.revoked && row.origin === o && row.expiresAt > nowMs()) return true;
    }
    return false;
  }

  function getPairingConfig() {
    return {
      pairing_code_ttl_sec: Math.floor(pairCodeTtlMsCurrent / 1000),
      pairing_code_ttl_min_sec: Math.floor(MIN_PAIRING_CODE_TTL_MS / 1000),
      pairing_code_ttl_default_sec: Math.floor(DEFAULT_PAIRING_CODE_TTL_MS / 1000),
      pairing_code_ttl_max_sec: Math.floor(MAX_PAIRING_CODE_TTL_MS / 1000),
      token_ttl_sec: Math.floor(tokenTtlMs / 1000),
    };
  }

  function setPairingCodeTtlSec(ttlSec) {
    const ttlMs = clampPairingCodeTtlMs(Number(ttlSec) * 1000);
    pairCodeTtlMsCurrent = ttlMs;
    emitAudit({
      event: 'pairing_ttl_updated',
      pairing_code_ttl_sec: Math.floor(ttlMs / 1000),
    });
    return getPairingConfig();
  }

  return {
    issuePairingCode,
    exchangePairingCode,
    validateToken,
    revokeToken,
    revokeAll,
    isPairedForOrigin,
    getPairingConfig,
    setPairingCodeTtlSec,
    _debugCounts: () => ({ codes: codes.size, tokens: tokens.size }),
  };
}

module.exports = {
  createWebBridgePairingStore,
  DEFAULT_PAIRING_CODE_TTL_MS,
  DEFAULT_TOKEN_TTL_MS,
  DEFAULT_EXCHANGE_FAIL_WINDOW_MS,
  DEFAULT_EXCHANGE_FAIL_MAX,
  MIN_PAIRING_CODE_TTL_MS,
  MAX_PAIRING_CODE_TTL_MS,
};

