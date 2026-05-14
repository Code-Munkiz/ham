# HAM GCP Live Preview Staging Runbook

This runbook is for post-acceptance staging operations of HAM GCP live preview.
It is intentionally narrow and does not change architecture.

## Scope

- Validate normal Workbench preview behavior in staging.
- Triage common preview failures quickly.
- Keep browser-facing preview URLs on HAM proxy paths only.

## Required Environment Signals

Required runtime controls for staging Cloud Run `ham-api`:

- `HAM_BUILDER_CLOUD_RUNTIME_PROVIDER=gcp_gke_sandbox`
- `HAM_BUILDER_CLOUD_RUNTIME_EXPERIMENTS_ENABLED=true`
- `HAM_BUILDER_GCP_RUNTIME_ENABLED=true`
- `HAM_BUILDER_GCP_RUNTIME_DRY_RUN=false`
- `HAM_BUILDER_GCP_RUNTIME_LIVE_K8S_ENABLED=true`
- `HAM_BUILDER_GCP_RUNTIME_LIVE_BUNDLE_UPLOAD=true`
- `HAM_BUILDER_GCP_PROJECT_ID`
- `HAM_BUILDER_GCP_REGION`
- `HAM_BUILDER_GKE_CLUSTER`
- `HAM_BUILDER_GKE_NAMESPACE_PREFIX=ham-builder-preview`
- `HAM_BUILDER_PREVIEW_SOURCE_BUCKET`
- `HAM_BUILDER_PREVIEW_RUNNER_IMAGE`
- `HAM_BUILDER_PREVIEW_DEFAULT_PORT=3000`
- `HAM_BUILDER_PREVIEW_TTL_SECONDS`
- `HAM_BUILDER_CLOUD_RUNTIME_STALE_JOB_SECONDS`

Optional diagnostics:

- `HAM_BUILDER_PREVIEW_PROXY_AUTH_DIAGNOSTICS`

## Expected Staging Runtime Shape

- GKE namespace: `ham-builder-preview-spike`
- Preview source bucket: from `HAM_BUILDER_PREVIEW_SOURCE_BUCKET`
- Runner image: from `HAM_BUILDER_PREVIEW_RUNNER_IMAGE`
- Browser preview URL: `/api/workspaces/{workspace_id}/projects/{project_id}/builder/preview-proxy/`

Never expose pod IP, ClusterIP, service DNS, or internal upstream URL to browser payloads.

## Standard Smoke (Workbench UI)

1. Open `https://ham-nine-mu.vercel.app/workspace/chat`.
2. Use a staging workspace/project.
3. Send prompt: `build me a game like Tetris`.
4. Verify:
   - source snapshot appears,
   - preview status reaches ready,
   - iframe loads proxy URL,
   - `@vite/client` and `src/main.tsx` load under proxy prefix,
   - no strict MIME module errors,
   - app renders in iframe.

## API/Proxy Verification

- Cloud Run status: `GET https://ham-api-13856606312.us-central1.run.app/api/status`
- Vercel status: `GET https://ham-nine-mu.vercel.app/api/status`
- Preview status: `GET /api/workspaces/{ws}/projects/{project}/builder/preview-status`
- Preview proxy: `GET /api/workspaces/{ws}/projects/{project}/builder/preview-proxy/`

## Common Failure Classes

- `401` auth: preview session/auth context missing.
- `404` no ready endpoint: no active ready proxy endpoint selected.
- `502` upstream unavailable: proxy cannot fetch live upstream.
- MIME module error: asset path escaped proxy prefix or wrong content-type pathing.
- React runtime crash: scaffold/runtime app code issue (for example missing import).
- stale pending runtime: active state selection shadowed by older sessions/jobs.

## Cleanup and TTL

Validate these routinely:

- Pod/service ownership labels exist:
  - `ham.workspace_id`
  - `ham.project_id`
  - `ham.runtime_session_id`
- Expiry label present: `ham.expires_at`
- Service routes `80 -> targetPort 3000`.
- Cleanup deletes only owned expired resources.
- Stale endpoints are not treated as ready after cleanup.

Useful checks:

- `kubectl get pods -n ham-builder-preview-spike -L ham.workspace_id,ham.project_id,ham.runtime_session_id,ham.expires_at`
- `kubectl get svc -n ham-builder-preview-spike -L ham.workspace_id,ham.project_id,ham.runtime_session_id`
- `kubectl get endpoints -n ham-builder-preview-spike`

## Rollback

If regression occurs:

1. Identify last known-good Cloud Run revision.
2. Shift traffic back to that revision.
3. Re-run smoke prompt and proxy checks.
4. File regression note with failing class and first bad commit/revision.

## Diagnostics Flag Policy

- Keep `HAM_BUILDER_PREVIEW_PROXY_AUTH_DIAGNOSTICS=1` only for short staging burn-in.
- Disable after burn-in once:
  - proxy auth behavior is stable,
  - no unresolved preview auth incidents remain.
- Use targeted env updates only; do not broad-replace env configuration.
