import { RunRecord, BackendRecord, ActivityEvent, Agent, ApiKey } from './types';

export const MOCK_BACKENDS: BackendRecord[] = [
  {
    id: "aws-lambda-adapter",
    version: "1.4.2",
    display_name: "AWS Lambda (US-East-1)",
    metadata: { runtime: "node20", memory: "1024MB" },
    is_default: true
  },
  {
    id: "k8s-pod-executor",
    version: "0.9.5",
    display_name: "Kubernetes Runner",
    metadata: { cluster: "prod-cluster-01", namespace: "ham-runners" },
    is_default: false
  },
  {
    id: "local-pty-bridge",
    version: "3.0.0",
    display_name: "Local PTY Bridge",
    metadata: { mode: "interactive" },
    is_default: false
  }
];

export const MOCK_RUNS: RunRecord[] = [
  {
    run_id: "run_881a2b",
    created_at: new Date(Date.now() - 3600000).toISOString(),
    author: "aaron",
    profile_id: "security-audit-v1",
    profile_version: "1.0.4",
    backend_id: "local.droid",
    backend_version: "1.0.0",
    prompt_summary: "Full repo scan for leaked API keys and sensitive environment patterns.",
    bridge_result: {
      intent_id: "intent_security_01",
      request_id: "req_xyz_123",
      run_id: "run_881a2b",
      status: "executed",
      policy_decision: {
        accepted: true,
        reasons: ["Policy P01: No hardcoded secrets (PASSED)"],
        policy_version: "bridge-v0",
      },
      started_at: "2026-04-18T12:00:00.000000+00:00",
      ended_at: "2026-04-18T12:00:05.000000+00:00",
      duration_ms: 5000,
      commands: [
        {
          command_id: "inspect-1",
          argv: ["grep", "-r", "API_KEY", "."],
          working_dir: "/repo",
          status: "executed",
          exit_code: 0,
          timed_out: false,
          stdout: "No matches found.\n",
          stderr: "",
          stdout_truncated: false,
          stderr_truncated: false,
          started_at: "2026-04-18T12:00:01.000000+00:00",
          ended_at: "2026-04-18T12:00:01.120000+00:00",
          duration_ms: 120,
        },
        {
          command_id: "inspect-2",
          argv: ["trufflehog", "filesystem", "."],
          working_dir: "/repo",
          status: "executed",
          exit_code: 0,
          timed_out: false,
          stdout: "Scanning 1.2k files...\n",
          stderr: "",
          stdout_truncated: false,
          stderr_truncated: false,
          started_at: "2026-04-18T12:00:02.000000+00:00",
          ended_at: "2026-04-18T12:00:06.500000+00:00",
          duration_ms: 4500,
        },
      ],
      summary: "Bridge v0 executed: 2 command(s), 2 executed, 0 failed, 0 timed out.",
      pre_exec_git_status: "## main... [clean]",
      post_exec_git_status: "## main... [clean]",
      mutation_detected: false,
      artifacts: [],
    },
    hermes_review: {
      ok: true,
      notes: ["Repository is clean of immediate high-risk secrets.", "Recommend periodic rotation of environment placeholders."],
      code: "REVIEW_PASSED",
    },
  },
  {
    run_id: "run_992c3d",
    created_at: new Date(Date.now() - 7200000).toISOString(),
    author: "system",
    profile_id: "inspect.git_diff",
    profile_version: "1.0.0",
    backend_id: "local.droid",
    backend_version: "1.0.0",
    prompt_summary: "Load test for the auth microservice under 10k RPS simulation.",
    bridge_result: {
      intent_id: "intent_perf_load",
      request_id: "req_abc_456",
      run_id: "run_992c3d",
      status: "failed",
      policy_decision: {
        accepted: false,
        reasons: ["Threshold T01: Response time < 200ms (FAILED)"],
        policy_version: "bridge-v0",
      },
      started_at: "2026-04-18T10:00:00.000000+00:00",
      ended_at: "2026-04-18T10:00:30.000000+00:00",
      duration_ms: 30000,
      commands: [
        {
          command_id: "inspect-1",
          argv: ["k6", "run", "script.js"],
          working_dir: "/repo/load",
          status: "failed",
          exit_code: 1,
          timed_out: false,
          stdout: "",
          stderr: "Error: Service overloaded, 503 received.\n",
          stdout_truncated: false,
          stderr_truncated: false,
          started_at: "2026-04-18T10:00:00.000000+00:00",
          ended_at: "2026-04-18T10:00:30.000000+00:00",
          duration_ms: 30000,
        },
      ],
      summary: "Bridge v0: command failed",
      mutation_detected: true,
      artifacts: [],
    },
    hermes_review: {
      ok: false,
      notes: ["Performance degradation detected at 8k RPS.", "Memory pressure on auth-svc-pod-2 suspected."],
      code: "THRESHOLD_EXCEEDED",
      context: "Auth service memory reached 95% capacity during ramp-up.",
    },
  },
];

export const MOCK_AGENTS: Agent[] = [
  {
    id: "agt_01",
    name: "Builder",
    role: "Core Developer & Logic Implementation",
    model: "Claude 3.5 Sonnet",
    provider: "Anthropic",
    status: "Ready",
    keyConnected: true,
    assignedTools: ["Git Inspector", "File System", "Code Parser"],
    description: "Specializes in writing high-quality TypeScript and React code with a focus on durability and clean architecture.",
    notes: "Currently working on the workbench overhaul.",
    systemPrompt: "You are a lead systems architect and senior engineer. Your goal is to implement robust, well-tested, and clean code. Always prioritize readability and performance. Use modern TypeScript patterns.",
    traits: ["methodical", "concise", "security-focused"],
    knowledgeAreas: ["TypeScript", "React", "API Design", "Testing"],
    communicationStyle: "Technical & Precise",
    reasoningDepth: "Balanced",
    contextSize: "200K tokens",
    autonomyLevel: "Semi-Auto",
    safeMode: true,
    requireApprovalFor: ["File deletion", "Git push/commit", "Shell commands"],
    memoryEnabled: true,
    memoryScope: "This Project",
    knowledgeSources: [{ name: "HAM Core Docs", id: "ks_01" }]
  },
  {
    id: "agt_02",
    name: "Reviewer",
    role: "Code Quality & Security Auditor",
    model: "GPT-4o",
    provider: "OpenAI",
    status: "Ready",
    keyConnected: true,
    assignedTools: ["Neural Auditor", "Diff Analysis"],
    description: "Evaluates pull requests for security vulnerabilities, architectural consistency, and performance bottlenecks.",
    notes: "Aggressive on security policies.",
    traits: ["meticulous", "critical", "security-first"],
    communicationStyle: "Minimal / Terse",
    reasoningDepth: "Deep"
  },
  {
    id: "agt_03",
    name: "Researcher",
    role: "Documentation & Technical Search",
    model: "Perplexity Pro",
    provider: "Perplexity",
    status: "Needs Setup",
    keyConnected: false,
    assignedTools: ["Web Search"],
    description: "Finds documentation, external libraries, and technical solutions for complex engineering problems.",
    notes: "Awaiting API key verification.",
    communicationStyle: "Detailed & Educational",
    reasoningDepth: "Fast"
  },
  {
    id: "agt_04",
    name: "Coordinator",
    role: "Task Decomposition & Planning",
    model: "Claude 3.5 Sonnet",
    provider: "Anthropic",
    status: "Ready",
    keyConnected: true,
    assignedTools: ["Project Graph", "Dependency Mapper"],
    description: "Breaks down high-level user requests into actionable technical tasks for the rest of the team.",
    notes: "Primary entry point for system directives.",
    communicationStyle: "Conversational",
    autonomyLevel: "Supervised"
  },
  {
    id: "agt_05",
    name: "QA",
    role: "Test Generation & Validation",
    model: "GPT-4o",
    provider: "OpenAI",
    status: "Working",
    keyConnected: true,
    assignedTools: ["Vitest Runner", "Playwright Bridge"],
    description: "Ensures the application works as expected by generating and running comprehensive test suites.",
    notes: "Validating the new ModelPicker component.",
    traits: ["thorough", "edge-case-obsessed"],
    autonomyLevel: "Full Auto",
    safeMode: false
  }
];

export const MOCK_KEYS: ApiKey[] = [
  {
    id: "key_01",
    provider: "Anthropic",
    maskedKey: "sk-ant-••••••••••••••••••••••••",
    status: "Connected",
    assignedAgents: ["Builder", "Coordinator"]
  },
  {
    id: "key_02",
    provider: "OpenAI",
    maskedKey: "sk-proj-••••••••••••••••••••••••",
    status: "Connected",
    assignedAgents: ["Reviewer", "QA"]
  },
  {
    id: "key_03",
    provider: "Perplexity",
    maskedKey: "pplx-••••••••••••••••••••••••",
    status: "Inactive",
    assignedAgents: ["Researcher"]
  }
];

export const MOCK_EXTENSIONS = [
  {
    id: "ext_git_bridge",
    name: "Git Inspector",
    description: "Deep repository history analysis and change-set verification.",
    category: "Connectivity",
    author: "HAM Core",
    installed: true,
    powers: ["Context Extraction", "Diff Analysis"]
  },
  {
    id: "ext_cloud_vision",
    name: "Infrastructure Vision",
    description: "Real-time visual monitoring of cloud topology and resource flow.",
    category: "Monitoring",
    author: "Hermes Labs",
    installed: true,
    powers: ["Drift Detection", "Visual Mapping"]
  },
  {
    id: "ext_data_vault",
    name: "Data Vault",
    description: "Hardened AES-256 storage adapter for sensitive run artifacts.",
    category: "Security",
    author: "Shield Team",
    installed: false,
    powers: ["Encryption", "Persistence"]
  },
  {
    id: "ext_neural_audit",
    name: "Neural Auditor",
    description: "Enforce advanced architectural consistency using LLM-driven consensus.",
    category: "Intelli",
    author: "HAM AI",
    installed: true,
    powers: ["Consensus", "Compliance"]
  }
];

export const MOCK_ACTIVITY: ActivityEvent[] = [
  {
    id: "evt_01",
    type: "run_event",
    level: "info",
    source: "ham",
    message: "Run run_881a2b completed successfully using profile security-audit-v1.",
    timestamp: new Date(Date.now() - 3600000).toISOString()
  },
  {
    id: "evt_02",
    type: "warning",
    level: "warn",
    source: "droid",
    message: "Malformed file skip: .DS_Store could not be parsed as UTF-8 in run_881a2b.",
    timestamp: new Date(Date.now() - 3650000).toISOString()
  },
  {
    id: "evt_03",
    type: "review_outcome",
    level: "error",
    source: "ham",
    message: "Hermes Review FAILED for run_992c3d: THRESHOLD_EXCEEDED.",
    timestamp: new Date(Date.now() - 7200000).toISOString()
  },
  {
    id: "evt_04",
    type: "persistence_warning",
    level: "warn",
    source: "cloud_agent",
    message: "Artifact persistence delayed for run_992c3d due to backend latency.",
    timestamp: new Date(Date.now() - 7100000).toISOString()
  },
  {
    id: "evt_05",
    type: "runtime_event",
    level: "info",
    source: "cursor",
    message: "Cursor task linked to session ses_3f9a1 (repository index refreshed).",
    timestamp: new Date(Date.now() - 1800000).toISOString()
  },
  {
    id: "evt_06",
    type: "run_event",
    level: "info",
    source: "factory_ai",
    message: "Factory pipeline batch fp_12 queued; worker capacity OK.",
    timestamp: new Date(Date.now() - 900000).toISOString()
  },
  {
    id: "evt_07",
    type: "runtime_event",
    level: "warn",
    message: "Legacy event shape (no source field) — should display UNKNOWN in UI until backfilled.",
    timestamp: new Date(Date.now() - 600000).toISOString(),
    metadata: { note: "intentional missing source" }
  }
];
