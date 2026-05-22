# M15 Scheduled Tick — Operator Runbook

> **OPERATOR-ONLY EXECUTION BOUNDARY**
>
> Workers do not execute the `gcloud` commands in this runbook.
> All `gcloud scheduler jobs create http`, `gcloud scheduler jobs delete`,
> `gcloud run services update`, and IAM grant commands are operator
> responsibilities executed outside the mission scope.
> Workers commit the code and this runbook; the operator activates
> Cloud Scheduler after each deploy.

---

## Overview

The scheduled-tick route (`POST /api/social/autonomy/scheduled-tick`) is a
**new endpoint** on the existing `ham-api` Cloud Run service that allows
**Google Cloud Scheduler** to trigger periodic autonomous-run ticks without
a Clerk session.  The endpoint is **disabled by default** and becomes active
only when `HAM_SOCIAL_AUTONOMY_SCHEDULER_ENABLED=true` is set on the service.

The route uses a **fail-closed auth chain**:
1. **OIDC verification** (preferred): Cloud Scheduler's OIDC-signed bearer
   token, validated against a service account email allowlist and an audience
   claim.
2. **Shared bearer fallback**: a pre-shared `HAM_SOCIAL_AUTONOMY_SCHEDULER_TOKEN`
   secret for simpler integrations that cannot use Google OIDC.

Dry-run mode is the default.  Live mode requires a **triple env interlock** —
all three must be present for `dry_run=False` to reach the runner.

---

## Prerequisites

Before activating the scheduled-tick route, the operator must confirm:

- The M4 code is deployed on `ham-api` (revision includes
  `src/api/social_scheduler.py`).
- The following env vars are configured on the Cloud Run service revision
  (see the "Environment variable setup" section below):
  - `HAM_SOCIAL_AUTONOMY_SCHEDULER_ENABLED=true`
  - `HAM_SOCIAL_AUTONOMY_SCHEDULER_SERVICE_ACCOUNT` (for OIDC)
  - `HAM_SOCIAL_AUTONOMY_SCHEDULER_AUDIENCE` (for OIDC)
  - `HAM_SOCIAL_AUTONOMY_SCHEDULER_TOKEN` (for bearer fallback, if used)
  - `HAM_SOCIAL_AUTONOMY_SCHEDULER_DRY_RUN=false` + `HAM_SOCIAL_LIVE_APPLY_TOKEN`
    (only required for live mode — see triple-env interlock below)
- The Cloud Scheduler service account has `roles/run.invoker` on the
  `ham-api` Cloud Run service (see IAM section).

---

## Step 1 — Environment Variable Setup

**Workers do not execute these.** These are operator-managed via the Cloud
Console or `gcloud run services update`.

### Enable the scheduler route

```sh
gcloud run services update ham-api \
  --project clarity-staging-488201 \
  --region us-central1 \
  --set-env-vars HAM_SOCIAL_AUTONOMY_SCHEDULER_ENABLED=true
```

### OIDC auth configuration

```sh
# Replace SCHEDULER_SA with the Cloud Scheduler service account email.
# Replace https://... with the canonical full URL of the endpoint.
gcloud run services update ham-api \
  --project clarity-staging-488201 \
  --region us-central1 \
  --set-env-vars HAM_SOCIAL_AUTONOMY_SCHEDULER_SERVICE_ACCOUNT=SCHEDULER_SA@PROJECT_ID.iam.gserviceaccount.com \
  --set-env-vars HAM_SOCIAL_AUTONOMY_SCHEDULER_AUDIENCE=https://goham.space/api/social/autonomy/scheduled-tick
```

The value of `HAM_SOCIAL_AUTONOMY_SCHEDULER_AUDIENCE` **must match** the
`--oidc-token-audience` flag set when creating the Cloud Scheduler job
(see Step 3 below).

### Bearer fallback (optional)

If OIDC is not used, set a strong random secret:

```sh
gcloud run services update ham-api \
  --project clarity-staging-488201 \
  --region us-central1 \
  --update-secrets HAM_SOCIAL_AUTONOMY_SCHEDULER_TOKEN=ham-scheduler-token:latest
```

---

## Step 2 — IAM Grants

**Workers do not execute these.** These are operator-only commands.

### Cloud Scheduler → Cloud Run service invoker

Cloud Scheduler needs permission to invoke the `ham-api` Cloud Run service.
Grant `roles/run.invoker` to the Cloud Scheduler service account:

```sh
# Replace SCHEDULER_SA with the Cloud Scheduler service account email.
gcloud run services add-iam-policy-binding ham-api \
  --project clarity-staging-488201 \
  --region us-central1 \
  --member="serviceAccount:SCHEDULER_SA@PROJECT_ID.iam.gserviceaccount.com" \
  --role="roles/run.invoker"
```

> **Note:** `roles/run.invoker` grants the service account permission to
> call `ham-api`.  It does NOT grant access to other Cloud Run services or
> to Firestore.

---

## Step 3 — Create the Cloud Scheduler Job

**Workers do not execute these commands.**

The following command creates a Cloud Scheduler job that calls the
scheduled-tick endpoint once per hour using OIDC authentication.

```sh
# Replace SCHEDULER_SA with the Cloud Scheduler service account email.
# Adjust --schedule to the desired cron expression.
gcloud scheduler jobs create http ham-social-autonomy-scheduled-tick \
  --project clarity-staging-488201 \
  --location us-central1 \
  --schedule "0 * * * *" \
  --uri "https://goham.space/api/social/autonomy/scheduled-tick" \
  --http-method POST \
  --message-body '{"dry_run": true}' \
  --headers "Content-Type=application/json" \
  --oidc-service-account-email SCHEDULER_SA@PROJECT_ID.iam.gserviceaccount.com \
  --oidc-token-audience https://goham.space/api/social/autonomy/scheduled-tick \
  --time-zone UTC \
  --description "Periodic GoHAM Social autonomy tick (dry-run mode)"
```

Key flags:
- `--oidc-token-audience` **must match**
  `HAM_SOCIAL_AUTONOMY_SCHEDULER_AUDIENCE` set on the Cloud Run service.
- `--oidc-service-account-email` **must match**
  `HAM_SOCIAL_AUTONOMY_SCHEDULER_SERVICE_ACCOUNT`.
- `--schedule` uses standard cron syntax. `"0 * * * *"` = once per hour.
  Adjust as needed (e.g. `"*/15 * * * *"` for every 15 minutes).

### Alternative: Bearer-Token Mode

If OIDC is not available or not desired, Cloud Scheduler can pass the
pre-shared `HAM_SOCIAL_AUTONOMY_SCHEDULER_TOKEN` secret as a static
`Authorization` header instead.

> **Workers do not execute this command.**

```sh
# Replace SCHEDULER_TOKEN_VALUE with the value of HAM_SOCIAL_AUTONOMY_SCHEDULER_TOKEN.
# Keep the token in a Secret Manager reference — do not hard-code values.
gcloud scheduler jobs create http ham-social-autonomy-scheduled-tick \
  --project clarity-staging-488201 \
  --location us-central1 \
  --schedule "0 * * * *" \
  --uri "https://goham.space/api/social/autonomy/scheduled-tick" \
  --http-method POST \
  --message-body '{"dry_run": true}' \
  --headers "Content-Type=application/json,Authorization=Bearer SCHEDULER_TOKEN_VALUE" \
  --time-zone UTC \
  --description "Periodic GoHAM Social autonomy tick (bearer-token mode)"
```

Key differences from OIDC mode:
- No `--oidc-service-account-email` / `--oidc-token-audience` flags.
- The token is passed as a static header value — rotate it via Secret Manager
  and update the scheduler job header when rotating.
- `HAM_SOCIAL_AUTONOMY_SCHEDULER_SERVICE_ACCOUNT` and
  `HAM_SOCIAL_AUTONOMY_SCHEDULER_AUDIENCE` are **not required** on the service
  when using the bearer-only path; only `HAM_SOCIAL_AUTONOMY_SCHEDULER_TOKEN`
  is needed.
- Prefer OIDC in production; use bearer mode for simpler integrations or
  local development testing only.

---

## Triple-Env Interlock for Live Mode

By default, the scheduled-tick endpoint operates in **dry-run mode**.
Live mode (which can cause real Telegram sends, subject to the usual
autonomy gates) requires **all three** of the following environment
variables to be configured on the Cloud Run service:

| Env variable | Required value | Effect |
|---|---|---|
| `HAM_SOCIAL_AUTONOMY_SCHEDULER_ENABLED` | `true` | Enables the route |
| `HAM_SOCIAL_AUTONOMY_SCHEDULER_DRY_RUN` | `false` | Opts in to live-send mode |
| `HAM_SOCIAL_LIVE_APPLY_TOKEN` | (non-empty) | Live-send credential present |

**If any one of these three is missing or has the wrong value, the route
forces `dry_run=True` regardless of the request body.**

This means:
- Only `HAM_SOCIAL_AUTONOMY_SCHEDULER_DRY_RUN=false` set → still dry-run
- Only `HAM_SOCIAL_LIVE_APPLY_TOKEN` set → still dry-run
- All three set + `{"dry_run": false}` body → live mode enabled

> **Safety:** The triple interlock is defense-in-depth against accidental
> live sends from misconfigured scheduler jobs.  Even if a job sends
> `{"dry_run": false}`, the route will force dry-run unless the operator
> has deliberately configured all three envs.

---

## Step 4 — Smoke Test

**Workers do not execute the curl command against production.**
This sequence is for operator verification after deploy.

### 4a — Verify the route is disabled by default (before enabling)

Before setting `HAM_SOCIAL_AUTONOMY_SCHEDULER_ENABLED=true`, the route
should return 503:

```sh
curl -fsS https://goham.space/api/social/autonomy/scheduled-tick \
  -X POST -H "Content-Type: application/json" -d '{}' \
  | python3 -m json.tool
# Expected: {"detail": {"error": {"code": "AUTONOMY_SCHEDULER_DISABLED", ...}}}
```

### 4b — Smoke test via bearer token (dry-run; expected 200 response shape)

After enabling the scheduler route and setting a bearer token, verify the
endpoint accepts a valid token and returns a 200 with the dry-run tick result.

> **Workers do not execute this against production.**
> Replace `<HAM_SOCIAL_AUTONOMY_SCHEDULER_TOKEN_VALUE>` with the
> pre-shared token value (never log or print the real value).

```sh
curl -fsS https://goham.space/api/social/autonomy/scheduled-tick \
  -X POST \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer <HAM_SOCIAL_AUTONOMY_SCHEDULER_TOKEN_VALUE>" \
  -d '{"dry_run": true}' \
  | python3 -m json.tool
```

Expected 200 response shape (exact values depend on profile and autonomy
gate state):

```json
{
  "ran": false,
  "dry_run": true,
  "actions_considered": [],
  "actions_taken": [],
  "blocked_reasons": ["autonomy_profile_missing"],
  "next_run_summary": null,
  "profile_status": "draft"
}
```

Or, if a running profile is configured and the tick was allowed through all
gates in dry-run mode:

```json
{
  "ran": true,
  "dry_run": true,
  "actions_considered": ["telegram:message"],
  "actions_taken": ["telegram:message"],
  "blocked_reasons": [],
  "next_run_summary": "Next run eligible after cadence window elapses.",
  "profile_status": "running"
}
```

A 200 response confirms:
- The scheduler route is active (`HAM_SOCIAL_AUTONOMY_SCHEDULER_ENABLED=true`).
- The bearer token was accepted.
- The tick ran (or was gated for expected reasons such as cadence/profile state).
- The endpoint returned the canonical `SocialAutonomyTickResult` shape.

### Verify OIDC auth (after enabling)

After enabling the scheduler and configuring OIDC envs, the Cloud
Scheduler job can be manually triggered to verify:

```sh
gcloud scheduler jobs run ham-social-autonomy-scheduled-tick \
  --project clarity-staging-488201 \
  --location us-central1
```

Check the Cloud Run logs for successful tick invocation:

```sh
gcloud logging read 'resource.type="cloud_run_revision" AND resource.labels.service_name="ham-api" AND "social-autonomy-scheduled-tick"' \
  --project clarity-staging-488201 \
  --limit 20 \
  --format "table(timestamp,textPayload)"
```

### Verify scheduler-state store was updated

After a successful tick, the scheduler-state Firestore document should
reflect `last_scheduled_tick_at` and `last_tick_summary`:

```sh
# Read the scheduler state via the HAM API (Clerk-authed GET)
curl -fsS https://goham.space/api/social/autonomy \
  -H "Authorization: Bearer <CLERK_JWT>" \
  | python3 -m json.tool | grep -A5 "scheduler"
```

---

## Operational Notes

### Disabling the scheduler

To disable the scheduled-tick route without removing the Cloud Scheduler
job:

```sh
gcloud run services update ham-api \
  --project clarity-staging-488201 \
  --region us-central1 \
  --set-env-vars HAM_SOCIAL_AUTONOMY_SCHEDULER_ENABLED=false
```

The Cloud Scheduler job will continue to run on schedule but receive
`503 AUTONOMY_SCHEDULER_DISABLED` responses.

### Deleting the Cloud Scheduler job

```sh
gcloud scheduler jobs delete ham-social-autonomy-scheduled-tick \
  --project clarity-staging-488201 \
  --location us-central1
```

### No-op on normal gates

The scheduled-tick endpoint is subject to all the same autonomy gates
as the Clerk-gated `/tick` route: cadence, emergency stop, daily cap,
quiet hours, content guards, etc. A successful 200 response does not
necessarily mean any action was taken — check `blocked_reasons` in the
response body.

### Audit trail

Each scheduled tick writes an audit envelope with
`actor="social-autonomy-scheduled-tick"` (distinct from the Clerk-gated
route's `"social-autonomy-tick"` actor), making it easy to filter scheduled
ticks in the audit log:

```sh
find .ham/_audit/social_autonomy -name '*.json' -exec \
  grep -l '"actor": "social-autonomy-scheduled-tick"' {} \;
```

---

## Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| 503 `AUTONOMY_SCHEDULER_DISABLED` | `HAM_SOCIAL_AUTONOMY_SCHEDULER_ENABLED` not set | Set env var to `true` on the revision |
| 401 `SCHEDULED_TICK_TOKEN_MISSING` | No `Authorization` header | Cloud Scheduler OIDC config missing |
| 401 `SCHEDULED_TICK_TOKEN_INVALID` | Wrong SA email or audience | Check `HAM_SOCIAL_AUTONOMY_SCHEDULER_SERVICE_ACCOUNT` and `HAM_SOCIAL_AUTONOMY_SCHEDULER_AUDIENCE` |
| 503 `SCHEDULED_TICK_AUTH_RUNTIME_MISSING` | `google-auth` not in image | Rebuild from Dockerfile at repo root |
| 200 but `ran=false, blocked_reasons=[...]` | Autonomy gates blocked the tick | Normal; check `blocked_reasons` for details |
| Dry run when live was expected | Triple interlock not fully set | Verify all three envs are present and correct |
