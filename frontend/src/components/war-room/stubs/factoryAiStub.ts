/**
 * Stub view models for Factory AI panels — replace with API-backed models later.
 */
export type SwarmWorkerStub = {
  id: string;
  status: string;
  progressPct: number;
};

export const STUB_SWARM_WORKERS: SwarmWorkerStub[] = [
  { id: "WORKER_01", status: "SYNCHRONIZING", progressPct: 12 },
  { id: "WORKER_02", status: "EXECUTING", progressPct: 88 },
  { id: "WORKER_03", status: "WAITING", progressPct: 0 },
  { id: "COORDINATOR", status: "ORCHESTRATING", progressPct: 45 },
];
