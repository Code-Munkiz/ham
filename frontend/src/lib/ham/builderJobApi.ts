import { hamApiFetch } from "@/lib/ham/api";
import type { CancelResponse } from "@/lib/ham/builderPlan";

export class BuilderJobApiError extends Error {
  code: string;

  constructor(code: string, message: string) {
    super(message);
    this.name = "BuilderJobApiError";
    this.code = code;
  }
}

export async function cancelBuilderJob(
  jobId: string,
  reason?: string | null,
): Promise<CancelResponse> {
  const res = await hamApiFetch(`/api/jobs/${encodeURIComponent(jobId)}/cancel`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ reason: reason ?? null }),
  });
  if (!res.ok) {
    let code = `http_${res.status}`;
    let message = `Cancel failed (${res.status})`;
    try {
      const payload = (await res.json()) as {
        detail?: { error?: { code?: string; message?: string } };
      };
      code = payload.detail?.error?.code ?? code;
      message = payload.detail?.error?.message ?? message;
    } catch {
      /* ignore parse errors */
    }
    throw new BuilderJobApiError(code, message);
  }
  return (await res.json()) as CancelResponse;
}
