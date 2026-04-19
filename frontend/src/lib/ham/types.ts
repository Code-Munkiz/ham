export interface RunRecord {
  run_id: string;
  created_at: string;
  author: string | null;
  profile_id: string;
  profile_version: string;
  backend_id: string;
  backend_version: string;
  prompt_summary: string;
  bridge_result: BridgeResult;
  hermes_review: HermesReview;
}

/** Matches `src/bridge/contracts.py` BridgeStatus */
export type BridgeStatus =
  | 'rejected'
  | 'executed'
  | 'failed'
  | 'timed_out'
  | 'partial';

/** Matches `src/bridge/contracts.py` PolicyDecision */
export interface PolicyDecision {
  accepted: boolean;
  reasons: string[];
  policy_version: string;
}

/** Matches `src/bridge/contracts.py` CommandState */
export type CommandState =
  | 'executed'
  | 'failed'
  | 'timed_out'
  | 'skipped';

/**
 * Matches `src/bridge/contracts.py` CommandEvidence
 * (serialized in RunRecord.bridge_result from pydantic).
 */
export interface CommandEvidence {
  command_id: string;
  argv: string[];
  working_dir: string;
  status: CommandState;
  exit_code: number | null;
  timed_out: boolean;
  stdout: string;
  stderr: string;
  stdout_truncated: boolean;
  stderr_truncated: boolean;
  started_at: string;
  ended_at: string;
  duration_ms: number;
}

/**
 * Matches `src/bridge/contracts.py` BridgeResult
 * (embedded in persisted run JSON and /api/runs).
 */
export interface BridgeResult {
  intent_id: string;
  request_id: string;
  run_id: string;
  status: BridgeStatus;
  policy_decision: PolicyDecision;
  started_at: string;
  ended_at: string;
  duration_ms: number;
  commands: CommandEvidence[];
  summary: string;
  pre_exec_git_status?: string | null;
  post_exec_git_status?: string | null;
  mutation_detected?: boolean | null;
  artifacts: string[];
}

/** Bridge completed command execution successfully (green-path for inspect runs). */
export function isBridgeSuccess(b: BridgeResult): boolean {
  return b.status === 'executed';
}

export interface HermesReview {
  ok: boolean;
  notes: string[];
  code?: string;
  context?: string;
}

/** Matches `src/registry/profiles.py` IntentProfile (+ optional UI fields). */
export interface ProfileRecord {
  id: string;
  version: string;
  argv: string[];
  metadata: Record<string, any>;
  display_name?: string;
  description?: string;
  sample_command?: string;
}

export interface BackendRecord {
  id: string;
  version: string;
  display_name?: string;
  metadata: Record<string, any>;
  is_default?: boolean;
}

export interface ActivityEvent {
  id: string;
  type: 'run_event' | 'warning' | 'persistence_warning' | 'review_outcome' | 'runtime_event';
  level: 'info' | 'warn' | 'error';
  message: string;
  timestamp: string;
  metadata?: Record<string, any>;
}

export interface Agent {
  id: string;
  name: string;
  role: string;
  model: string;
  provider: string;
  status: 'Ready' | 'Needs Setup' | 'Working' | 'Offline';
  keyConnected: boolean;
  assignedTools: string[];
  description?: string;
  notes?: string;

  // Persona
  systemPrompt?: string;
  traits?: string[];
  knowledgeAreas?: string[];
  communicationStyle?: string;

  // Model Config
  reasoningDepth?: 'Fast' | 'Balanced' | 'Deep';
  contextSize?: string;

  // Behavior & Safety
  autonomyLevel?: 'Supervised' | 'Semi-Auto' | 'Full Auto';
  safeMode?: boolean;
  requireApprovalFor?: string[];
  allowlist?: string;
  denylist?: string;

  // Memory
  memoryEnabled?: boolean;
  memoryScope?: string;
  knowledgeSources?: { name: string; id: string }[];
}

export interface ApiKey {
  id: string;
  provider: string;
  maskedKey: string;
  status: 'Connected' | 'Error' | 'Inactive';
  assignedAgents: string[];
}
