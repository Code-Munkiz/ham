import type { ProjectRecord } from "@/lib/ham/types";

/** Stored under `ProjectRecord.metadata` (see PATCH /api/projects/{id}). */
export const PROJECT_DEFAULT_DEPLOY_APPROVAL_KEY = "default_deploy_approval_mode" as const;

export type ProjectDefaultDeployPolicy = "off" | "audit" | "soft" | "hard";

const ORDER: ProjectDefaultDeployPolicy[] = ["off", "audit", "soft", "hard"];

export function isProjectDefaultDeployPolicy(v: unknown): v is ProjectDefaultDeployPolicy {
  return typeof v === "string" && (ORDER as readonly string[]).includes(v);
}

export function getProjectDefaultDeployPolicy(p: ProjectRecord): ProjectDefaultDeployPolicy {
  const v = p.metadata?.[PROJECT_DEFAULT_DEPLOY_APPROVAL_KEY];
  if (isProjectDefaultDeployPolicy(v)) return v;
  return "off";
}

export const PROJECT_DEFAULT_DEPLOY_POLICY_OPTIONS: { value: ProjectDefaultDeployPolicy; label: string }[] = [
  { value: "off", label: "Off" },
  { value: "audit", label: "Audit" },
  { value: "soft", label: "Soft" },
  { value: "hard", label: "Hard" },
];
