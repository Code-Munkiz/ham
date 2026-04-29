'use strict';

const http = require('node:http');
const { createWebBridgePairingStore } = require('./local_control_web_bridge_pairing.cjs');

const BRIDGE_VERSION = 'v1';
const BRIDGE_PREFIX = '/ham/local-control/v1';
const CANONICAL_ORIGIN = 'https://ham-nine-mu.vercel.app';

function json(res, statusCode, payload, extraHeaders = {}) {
  const body = JSON.stringify(payload);
  res.writeHead(statusCode, {
    'Content-Type': 'application/json; charset=utf-8',
    'Content-Length': Buffer.byteLength(body),
    ...extraHeaders,
  });
  res.end(body);
}

function parseBearer(authorization) {
  const raw = String(authorization || '').trim();
  if (!raw) return '';
  const m = /^Bearer\s+(.+)$/i.exec(raw);
  if (!m) return '';
  return String(m[1] || '').trim();
}

function parseJsonBody(req, maxBytes = 4096) {
  return new Promise((resolve, reject) => {
    let total = 0;
    const chunks = [];
    req.on('data', (chunk) => {
      total += chunk.length;
      if (total > maxBytes) {
        reject(new Error('payload_too_large'));
        return;
      }
      chunks.push(chunk);
    });
    req.on('end', () => {
      if (!chunks.length) {
        resolve({});
        return;
      }
      try {
        const parsed = JSON.parse(Buffer.concat(chunks).toString('utf8'));
        resolve(parsed && typeof parsed === 'object' ? parsed : {});
      } catch {
        reject(new Error('invalid_json'));
      }
    });
    req.on('error', reject);
  });
}

function looksLikeDeniedStaleOrigin(origin) {
  const o = String(origin || '').trim().toLowerCase();
  if (!o) return false;
  if (o === 'https://ham-kappa-fawn.vercel.app') return true;
  return /^https:\/\/.*aaron-bundys-projects.*\.vercel\.app$/i.test(o);
}

function createLocalControlWebBridge(opts = {}) {
  const host = '127.0.0.1';
  const port = Number.isFinite(Number(opts.port)) ? Number(opts.port) : 0;
  const canonicalOrigin = String(opts.canonicalOrigin || CANONICAL_ORIGIN).trim() || CANONICAL_ORIGIN;
  const emitAudit = typeof opts.emitAudit === 'function' ? opts.emitAudit : () => {};
  const executeBrowserIntent = typeof opts.executeBrowserIntent === 'function' ? opts.executeBrowserIntent : null;
  const executeMachineEscalationRequest =
    typeof opts.executeMachineEscalationRequest === 'function' ? opts.executeMachineEscalationRequest : null;
  const pairing = createWebBridgePairingStore({
    nowMs: opts.nowMs,
    emitAudit,
    pairCodeTtlMs: opts.pairCodeTtlMs,
    tokenTtlMs: opts.tokenTtlMs,
    failWindowMs: opts.failWindowMs,
    failMax: opts.failMax,
  });

  /** @type {http.Server | null} */
  let server = null;
  let started = false;

  function isOriginAllowed(origin) {
    const o = String(origin || '').trim();
    if (!o) return false;
    if (looksLikeDeniedStaleOrigin(o)) return false;
    return o === canonicalOrigin;
  }

  function corsHeaders(origin) {
    return {
      'Access-Control-Allow-Origin': origin,
      Vary: 'Origin',
      'Access-Control-Allow-Methods': 'GET,POST,OPTIONS',
      'Access-Control-Allow-Headers': 'Authorization,Content-Type',
      'Access-Control-Max-Age': '300',
    };
  }

  async function handle(req, res) {
    const origin = String(req.headers.origin || '').trim();
    const allowed = isOriginAllowed(origin);
    const method = String(req.method || 'GET').toUpperCase();
    const url = String(req.url || '');
    if (!url.startsWith(BRIDGE_PREFIX)) {
      json(res, 404, { ok: false, error: 'not_found' });
      return;
    }
    const path = url.slice(BRIDGE_PREFIX.length) || '/';

    if (method === 'OPTIONS') {
      if (!allowed) {
        json(res, 403, { ok: false, error: 'origin_not_allowed' });
        return;
      }
      res.writeHead(204, corsHeaders(origin));
      res.end();
      return;
    }

    if (!allowed) {
      if (method === 'GET' && path === '/health') {
        json(res, 403, {
          ok: false,
          bridge_version: BRIDGE_VERSION,
          pairing_required: true,
          paired: false,
          origin_allowed: false,
          error: 'origin_not_allowed',
        });
        return;
      }
      json(res, 403, { ok: false, error: 'origin_not_allowed' });
      return;
    }

    const headers = corsHeaders(origin);

    if (method === 'GET' && path === '/health') {
      emitAudit({ event: 'bridge_health_read', origin });
      json(
        res,
        200,
        {
          ok: true,
          bridge_version: BRIDGE_VERSION,
          pairing_required: true,
          paired: pairing.isPairedForOrigin(origin),
          origin_allowed: true,
        },
        headers
      );
      return;
    }

    if (method === 'POST' && path === '/pairing/exchange') {
      let body;
      try {
        body = await parseJsonBody(req);
      } catch (err) {
        const code = err instanceof Error ? err.message : 'bad_request';
        json(res, 400, { ok: false, error: code }, headers);
        return;
      }
      const requestedOrigin = String(body.requested_origin || '').trim();
      if (requestedOrigin !== origin || requestedOrigin !== canonicalOrigin) {
        emitAudit({
          event: 'pairing_exchange_failure',
          origin,
          reason_code: 'requested_origin_mismatch',
        });
        json(res, 403, { ok: false, error: 'requested_origin_mismatch' }, headers);
        return;
      }
      const outcome = pairing.exchangePairingCode({
        pairing_code: body.pairing_code,
        requested_origin: requestedOrigin,
        client_nonce: body.client_nonce,
      });
      if (!outcome.ok) {
        const status = outcome.reason_code === 'pairing_rate_limited' ? 429 : 401;
        json(res, status, { ok: false, error: outcome.reason_code }, headers);
        return;
      }
      json(
        res,
        200,
        {
          ok: true,
          token_type: 'Bearer',
          access_token: outcome.access_token,
          expires_in_sec: outcome.expires_in_sec,
          session_id: outcome.session_id,
          scopes: outcome.scopes,
        },
        headers
      );
      return;
    }

    if (method === 'POST' && path === '/pairing/revoke') {
      const token = parseBearer(req.headers.authorization);
      if (!token) {
        json(res, 401, { ok: false, error: 'token_missing' }, headers);
        return;
      }
      const valid = pairing.validateToken({ token, origin });
      if (!valid.ok) {
        json(res, 401, { ok: false, error: valid.reason_code }, headers);
        return;
      }
      pairing.revokeToken(token);
      json(res, 200, { ok: true }, headers);
      return;
    }

    if (method === 'GET' && path === '/status') {
      const token = parseBearer(req.headers.authorization);
      if (!token) {
        json(res, 401, { ok: false, error: 'token_missing' }, headers);
        return;
      }
      const valid = pairing.validateToken({ token, origin, requiredScope: 'status.read' });
      if (!valid.ok) {
        json(res, 401, { ok: false, error: valid.reason_code }, headers);
        return;
      }
      json(
        res,
        200,
        {
          ok: true,
          kind: 'ham_local_control_bridge_status',
          bridge_version: BRIDGE_VERSION,
          pairing_required: true,
          paired: true,
        },
        headers
      );
      return;
    }

    if (method === 'POST' && path === '/browser/intent') {
      const token = parseBearer(req.headers.authorization);
      if (!token) {
        json(res, 401, { ok: false, error: 'token_missing' }, headers);
        return;
      }
      const valid = pairing.validateToken({ token, origin, requiredScope: 'browser.intent' });
      if (!valid.ok) {
        json(res, 401, { ok: false, error: valid.reason_code }, headers);
        return;
      }
      let body;
      try {
        body = await parseJsonBody(req);
      } catch (err) {
        const code = err instanceof Error ? err.message : 'bad_request';
        json(res, 400, { ok: false, error: code }, headers);
        return;
      }
      const action = String(body.action || '').trim();
      const url = String(body.url || '').trim();
      const intentId = String(body.intent_id || '').trim();
      if (!action || action !== 'navigate_and_capture' || !url) {
        json(res, 400, { ok: false, error: 'invalid_intent' }, headers);
        return;
      }
      if (!executeBrowserIntent) {
        json(res, 503, { ok: false, error: 'browser_intent_unavailable' }, headers);
        return;
      }
      const result = await executeBrowserIntent({
        action,
        url,
        intent_id: intentId,
        session_id: valid.session_id,
        origin,
        client_context: body.client_context && typeof body.client_context === 'object' ? body.client_context : {},
      });
      const statusCode =
        result && typeof result.http_status === 'number'
          ? result.http_status
          : result && result.ok === false
            ? 409
            : 200;
      json(res, statusCode, result, headers);
      return;
    }

    if (method === 'POST' && path === '/machine/escalation-request') {
      const token = parseBearer(req.headers.authorization);
      if (!token) {
        json(res, 401, { ok: false, error: 'token_missing' }, headers);
        return;
      }
      const valid = pairing.validateToken({
        token,
        origin,
        requiredScope: 'machine.escalation.request',
      });
      if (!valid.ok) {
        json(res, 401, { ok: false, error: valid.reason_code }, headers);
        return;
      }
      let body;
      try {
        body = await parseJsonBody(req);
      } catch (err) {
        const code = err instanceof Error ? err.message : 'bad_request';
        json(res, 400, { ok: false, error: code }, headers);
        return;
      }
      const escalatedFrom = String(body.escalated_from || '').trim();
      const trigger = String(body.trigger || '').trim();
      const userConfirmed = body.user_confirmed === true;
      const allowedTrigger =
        trigger === 'partial' || trigger === 'blocked' || trigger === 'browser_insufficient';
      if (escalatedFrom !== 'browser') {
        json(res, 409, { ok: false, error: 'browser_context_required' }, headers);
        return;
      }
      if (!allowedTrigger) {
        json(res, 400, { ok: false, error: 'trigger_not_allowed' }, headers);
        return;
      }
      if (!userConfirmed) {
        json(res, 409, { ok: false, error: 'user_confirmation_required' }, headers);
        return;
      }
      if (!executeMachineEscalationRequest) {
        json(res, 503, { ok: false, error: 'machine_escalation_unavailable' }, headers);
        return;
      }
      const result = await executeMachineEscalationRequest({
        intent_id: String(body.intent_id || '').trim(),
        escalated_from: escalatedFrom,
        trigger,
        user_confirmed: true,
        requested_scope: String(body.requested_scope || '').trim(),
        browser_bridge_status: String(body.browser_bridge_status || '').trim(),
        session_id: valid.session_id,
        origin,
      });
      const statusCode =
        result && typeof result.http_status === 'number'
          ? result.http_status
          : result && result.ok === false
            ? 409
            : 200;
      json(res, statusCode, result, headers);
      return;
    }

    json(res, 404, { ok: false, error: 'not_found' }, headers);
  }

  async function start() {
    if (started && server) return address();
    server = http.createServer((req, res) => {
      void handle(req, res).catch(() => {
        json(res, 500, { ok: false, error: 'internal_error' });
      });
    });
    await new Promise((resolve, reject) => {
      server.once('error', reject);
      server.listen({ host, port }, () => resolve());
    });
    started = true;
    return address();
  }

  async function stop() {
    if (!server) return;
    const s = server;
    server = null;
    started = false;
    await new Promise((resolve) => s.close(() => resolve()));
  }

  function address() {
    if (!server) return null;
    const a = server.address();
    if (!a || typeof a === 'string') return null;
    return {
      host: a.address,
      port: a.port,
      family: a.family,
    };
  }

  function getPairingConfig() {
    return pairing.getPairingConfig();
  }

  function setPairingCodeTtlSec(ttlSec) {
    return pairing.setPairingCodeTtlSec(ttlSec);
  }

  function getStatusSnapshot(origin) {
    const addr = address();
    const o = String(origin || '').trim();
    const originAllowed = o ? isOriginAllowed(o) : false;
    const paired = originAllowed ? pairing.isPairedForOrigin(o) : false;
    return {
      ok: true,
      bridge_version: BRIDGE_VERSION,
      enabled: true,
      running: Boolean(addr),
      detected: Boolean(addr),
      listener: addr ? { host: addr.host, port: addr.port } : null,
      pairing_required: true,
      origin_allowed: originAllowed,
      paired,
      status_read_available: originAllowed && paired,
      pairing: pairing.getPairingConfig(),
    };
  }

  function exchangePairingCodeTrusted({ pairing_code, client_nonce }) {
    return pairing.exchangePairingCode({
      pairing_code,
      requested_origin: canonicalOrigin,
      client_nonce: String(client_nonce || '').slice(0, 64),
    });
  }

  function readStatusTrusted({ token }) {
    const valid = pairing.validateToken({
      token,
      origin: canonicalOrigin,
      requiredScope: 'status.read',
    });
    if (!valid.ok) {
      return { ok: false, error: valid.reason_code };
    }
    return {
      ok: true,
      kind: 'ham_local_control_bridge_status',
      bridge_version: BRIDGE_VERSION,
      pairing_required: true,
      paired: true,
    };
  }

  async function executeBrowserIntentTrusted({ token, payload }) {
    const valid = pairing.validateToken({
      token,
      origin: canonicalOrigin,
      requiredScope: 'browser.intent',
    });
    if (!valid.ok) {
      return { ok: false, error: valid.reason_code, reason_code: valid.reason_code, http_status: 401 };
    }
    if (!executeBrowserIntent) {
      return { ok: false, error: 'browser_intent_unavailable', reason_code: 'browser_intent_unavailable', http_status: 503 };
    }
    const body = payload && typeof payload === 'object' ? payload : {};
    const action = String(body.action || '').trim();
    const url = String(body.url || '').trim();
    const intentId = String(body.intent_id || '').trim();
    if (action !== 'navigate_and_capture' || !url) {
      return { ok: false, error: 'invalid_intent', reason_code: 'invalid_intent', http_status: 400 };
    }
    const result = await executeBrowserIntent({
      action,
      url,
      intent_id: intentId,
      session_id: valid.session_id,
      origin: canonicalOrigin,
      client_context:
        body.client_context && typeof body.client_context === 'object'
          ? body.client_context
          : {},
    });
    return result && typeof result === 'object' ? result : { ok: false, error: 'browser_intent_failed', reason_code: 'browser_intent_failed', http_status: 409 };
  }

  function revokeTrustedToken({ token }) {
    return pairing.revokeToken(token);
  }

  function getStatusSnapshotTrusted() {
    return getStatusSnapshot(canonicalOrigin);
  }

  return {
    start,
    stop,
    address,
    issuePairingCode: () => pairing.issuePairingCode(),
    revokeAllPairings: () => pairing.revokeAll(),
    isOriginAllowed,
    getPairingConfig,
    setPairingCodeTtlSec,
    getStatusSnapshot,
    getStatusSnapshotTrusted,
    exchangePairingCodeTrusted,
    readStatusTrusted,
    executeBrowserIntentTrusted,
    revokeTrustedToken,
    BRIDGE_PREFIX,
    BRIDGE_VERSION,
  };
}

module.exports = {
  createLocalControlWebBridge,
  BRIDGE_PREFIX,
  BRIDGE_VERSION,
  CANONICAL_ORIGIN,
};

