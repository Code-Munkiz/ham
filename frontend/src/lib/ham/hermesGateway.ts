/**
 * Types for GET /api/hermes-gateway/snapshot (command center).
 * Keep in sync with src/ham/hermes_gateway/broker.py output.
 */

export interface HermesGatewayFreshness {
  inventory_cached: boolean;
  skills_installed_cached: boolean;
  http_probe_cached: boolean;
  hermes_version_cached: boolean;
  build_latency_ms: number;
}

export interface HermesGatewayExternalRunner {
  id: string;
  label: string;
  description: string;
  availability: string;
  capabilities: string[];
  status: string;
  requires_auth: boolean;
  requires_tty: boolean;
  configured: boolean;
  last_seen: string | null;
  actions_supported: string[];
  source: string;
  warnings: string[];
}

export interface HermesGatewayPlaceholder {
  id: string;
  label?: string;
  status: string;
  note?: string;
}

/** Derived single pane: Ham API snapshot of CLI probe + HTTP probe + chat gateway mode (see broker). */
export interface HermesGatewayOperatorConnection {
  summary: {
    cli_probe: string;
    cli_version_line: string;
    http_gateway_status: string;
    ham_chat_gateway_mode: string | null;
  };
  snapshot_meta: {
    captured_at: string;
    ttl_seconds: number;
    degraded_capabilities_count: number;
    has_degraded: boolean;
  };
  guidance: string;
}

export interface HermesGatewaySnapshot {
  kind: "ham_hermes_gateway_snapshot";
  schema_version: string;
  captured_at: string;
  ttl_seconds: number;
  /** Present on API >= this feature; older servers omit. */
  operator_connection?: HermesGatewayOperatorConnection;
  freshness: HermesGatewayFreshness;
  hermes_version: { cli_report: Record<string, unknown> };
  hermes_hub: Record<string, unknown>;
  runtime_inventory: Record<string, unknown>;
  skills_installed: Record<string, unknown>;
  http_gateway: Record<string, unknown>;
  counts: {
    tools_lines: number;
    plugins: number;
    mcp: number;
    skills_catalog: number;
    skills_installed: number;
    droids_registered: number;
  };
  commands_and_menus: Record<string, unknown>;
  activity: {
    control_plane_runs: Array<Record<string, unknown>>;
    control_plane_error: string | null;
    ham_run_store_count: number | null;
  };
  external_runners: HermesGatewayExternalRunner[];
  degraded_capabilities: string[];
  warnings: string[];
  future_adapter_placeholders: HermesGatewayPlaceholder[];
}

export interface HermesGatewayStreamTick {
  kind: "ham_hermes_gateway_stream_tick";
  schema_version?: string;
  captured_at?: string;
  gateway_mode?: string;
  degraded_capabilities?: string[];
  warnings_count?: number;
  freshness?: HermesGatewayFreshness;
}
