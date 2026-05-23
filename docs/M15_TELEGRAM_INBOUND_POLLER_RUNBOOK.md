# M15 Telegram Inbound Poller — Operator Runbook

> **OPERATOR-ONLY EXECUTION BOUNDARY**
>
> Workers do not execute the `gcloud` commands in this runbook.
> All `gcloud run jobs create`, `gcloud scheduler jobs create`,
> `gcloud run jobs execute`, and `gcloud projects add-iam-policy-binding`
> commands are operator responsibilities executed outside the mission scope.
> Workers commit the code and this runbook; the operator activates the
> Cloud Run Job after each deploy.

---

## Overview

The Telegram inbound poller is a **Cloud Run Job** (`telegram-inbound-poller`)
that runs on a schedule.  It calls the bounded `getUpdates` collector once,
persists transcript rows and the updated offset to Firestore, then exits.

The poller reuses the existing `ham-api` container image (`Dockerfile` at the
repo root).  No new Dockerfile or image is created.  The root `Dockerfile`
must `COPY scripts/social_telegram_inbound_poll.py` into the image (Mission
19 M1 packaging fix).  The operator overrides the default `uvicorn` entrypoint
at job-creation time by passing `--command` and `--args` to
`gcloud run jobs create`.

---

## Prerequisites

Before activating the poller, the operator must confirm:

- The `ham-api` image has been built and pushed to Artifact Registry for
  the current commit (the same image used by the `ham-api` Cloud Run service).
- The following env vars are set on the job revision (or via `--set-secrets` /
  `--set-env-vars`):
  - `TELEGRAM_BOT_TOKEN` — Secret Manager-backed; the bot token.
  - `HAM_TELEGRAM_TRANSCRIPT_BACKEND=firestore` — store transcript rows to Firestore.
  - `HAM_TELEGRAM_OFFSET_BACKEND=firestore` — persist the getUpdates offset to Firestore.
  - `HAM_FIRESTORE_PROJECT_ID=clarity-staging-488201` — Firestore project.
  - `PYTHONPATH=/app` — already set in the Dockerfile.
- The job's service account holds `roles/datastore.user` on
  `clarity-staging-488201` (see IAM section below).

---

## Step 1 — IAM Grants

Grant the required IAM roles on the GCP project.  These commands are
**operator-only**; workers do not execute them.

### Firestore access (`roles/datastore.user`)

The Cloud Run Job service account needs read/write access to Firestore
(Cloud Datastore) to persist transcript rows and the poll offset.

```sh
gcloud projects add-iam-policy-binding clarity-staging-488201 \
  --member="serviceAccount:ham-api-sa@clarity-staging-488201.iam.gserviceaccount.com" \
  --role="roles/datastore.user" \
  --project=clarity-staging-488201
```

### Cloud Scheduler → Cloud Run invoker (`roles/run.invoker`)

Cloud Scheduler needs permission to execute (invoke) the Cloud Run Job.
Grant `roles/run.invoker` to the Cloud Scheduler service account on the job.

```sh
# Replace SCHEDULER_SA with the Cloud Scheduler service account email.
gcloud projects add-iam-policy-binding clarity-staging-488201 \
  --member="serviceAccount:SCHEDULER_SA@PROJECT_ID.iam.gserviceaccount.com" \
  --role="roles/run.invoker" \
  --project=clarity-staging-488201
```

---

## Step 2 — Create the Cloud Run Job

The following command creates the `telegram-inbound-poller` job using the
existing `ham-api` image.  The `--command python3` and `--args` flags
override the default `uvicorn` CMD to run the poller entrypoint instead.

Workers do not execute this command.

```sh
# Set IMAGE_URL to the Artifact Registry image used by ham-api
# (e.g. us-central1-docker.pkg.dev/clarity-staging-488201/ham-api/ham-api:latest)
IMAGE_URL="us-central1-docker.pkg.dev/clarity-staging-488201/ham-api/ham-api:latest"
JOB_SA="ham-api-sa@clarity-staging-488201.iam.gserviceaccount.com"

gcloud run jobs create telegram-inbound-poller \
  --image="${IMAGE_URL}" \
  --command=python3 \
  --args="scripts/social_telegram_inbound_poll.py" \
  --region=us-central1 \
  --project=clarity-staging-488201 \
  --service-account="${JOB_SA}" \
  --set-secrets="TELEGRAM_BOT_TOKEN=telegram-bot-token:latest" \
  --set-env-vars="HAM_TELEGRAM_TRANSCRIPT_BACKEND=firestore,HAM_TELEGRAM_OFFSET_BACKEND=firestore,HAM_FIRESTORE_PROJECT_ID=clarity-staging-488201,PYTHONPATH=/app" \
  --max-retries=0 \
  --task-timeout=120s
```

**Key flags:**

| Flag | Purpose |
|---|---|
| `--command python3` | Overrides the Dockerfile `ENTRYPOINT` so the poller runs, not `uvicorn`. |
| `--args scripts/social_telegram_inbound_poll.py` | Runs the entrypoint at `scripts/social_telegram_inbound_poll.py`. |
| `--max-retries=0` | The poller is idempotent via the persisted offset; no retries needed. |
| `--task-timeout=120s` | Upper bound; the actual poll completes in < 10 s under normal conditions. |

---

## Step 3 — Schedule Periodic Invocation with Cloud Scheduler

Use Cloud Scheduler to trigger the job on a regular cadence.  The example
below schedules the job to run every 5 minutes.  Adjust the `--schedule`
cron expression as needed.

> **Workers do not execute these commands.**  Cloud Scheduler activation
> is an operator responsibility performed outside the mission scope.

```sh
# Replace SCHEDULER_SA with the Cloud Scheduler service account.
SCHEDULER_SA="cloud-scheduler-sa@clarity-staging-488201.iam.gserviceaccount.com"
REGION="us-central1"
PROJECT="clarity-staging-488201"

gcloud scheduler jobs create http telegram-inbound-poller-schedule \
  --location="${REGION}" \
  --project="${PROJECT}" \
  --schedule="*/5 * * * *" \
  --uri="https://${REGION}-run.googleapis.com/apis/run.googleapis.com/v1/namespaces/${PROJECT}/jobs/telegram-inbound-poller:run" \
  --message-body="{}" \
  --oauth-service-account-email="${SCHEDULER_SA}" \
  --oauth-token-scope="https://www.googleapis.com/auth/cloud-platform" \
  --time-zone="UTC" \
  --attempt-deadline=300s
```

**Notes:**

- The scheduler issues an HTTP POST to the Cloud Run Jobs execution API.
- `--oauth-service-account-email` must hold `roles/run.invoker` (see Step 1).
- For a more conservative polling cadence (e.g. once per minute or once per
  hour), adjust `--schedule` accordingly.
- Cloud Scheduler is **not** a long-poll — each invocation fires the job once
  and exits; the job itself uses `timeout=0` on the `getUpdates` request.

---

## Step 4 — Update the Job After a New Deploy

When a new `ham-api` image is deployed, update the job to reference the new
image:

```sh
IMAGE_URL="us-central1-docker.pkg.dev/clarity-staging-488201/ham-api/ham-api:NEW_TAG"

gcloud run jobs update telegram-inbound-poller \
  --image="${IMAGE_URL}" \
  --region=us-central1 \
  --project=clarity-staging-488201
```

---

## Step 5 — Smoke Test

Run the following verification sequence after the job is created or updated.
**Workers do not execute these commands.**

### 5a — Manual one-shot execution

Trigger a single job run manually:

```sh
gcloud run jobs execute telegram-inbound-poller \
  --region=us-central1 \
  --project=clarity-staging-488201 \
  --wait
```

### 5b — Confirm the Firestore offset advanced

After the job completes, read the Firestore offset document to confirm that
the `update_offset` field advanced from its previous value (or was created if
running for the first time):

```sh
# Read the offset document from Firestore (presence-only check; no raw IDs).
gcloud firestore documents get \
  "projects/clarity-staging-488201/databases/(default)/documents/ham_social_telegram_poller_state/<BOT_DIGEST>" \
  --project=clarity-staging-488201
```

A successful run will show `update_offset` as a non-negative integer.  If the
bot had no new messages since the previous run, the offset is unchanged (which
is expected and correct — the poller is idempotent).

### 5c — Confirm transcript rows were written

Check that redacted transcript rows exist in the `ham_social_telegram_transcripts`
Firestore collection:

```sh
gcloud firestore documents list \
  "projects/clarity-staging-488201/databases/(default)/documents/ham_social_telegram_transcripts" \
  --project=clarity-staging-488201 \
  --limit=5
```

Each row should have `source: telegram`, `role: user`, and a redacted `text`
field.  Numeric IDs of length ≥ 6 are stripped from the text; raw chat IDs
and author IDs are stored as integers but are not masked at this layer.

### 5d — Verify no raw token or unredacted identifiers in logs

Inspect the job's Cloud Logging output to confirm:

- The literal `TELEGRAM_BOT_TOKEN` value does not appear in any log line.
- The structured exit line contains `"code": "poll_complete"` or
  `"code": "telegram_bot_token_missing"` — never the raw token value.

```sh
gcloud logging read \
  'resource.type="cloud_run_job" AND resource.labels.job_name="telegram-inbound-poller"' \
  --project=clarity-staging-488201 \
  --limit=20 \
  --format=json
```

---

## Environment Variables Reference

| Variable | Required | Default | Purpose |
|---|---|---|---|
| `TELEGRAM_BOT_TOKEN` | **Yes** | — | Bot token; absent → poller exits 1. |
| `HAM_TELEGRAM_TRANSCRIPT_BACKEND` | Yes (prod) | `file` | Set to `firestore` on Cloud Run. |
| `HAM_TELEGRAM_OFFSET_BACKEND` | Yes (prod) | `file` | Set to `firestore` on Cloud Run. |
| `HAM_FIRESTORE_PROJECT_ID` | Yes (prod) | ADC | Firestore project ID. |
| `HAM_FIRESTORE_DATABASE` | No | `(default)` | Firestore database ID. |
| `PYTHONPATH` | Yes | `/app` (Dockerfile) | Must include `/app` for module imports. |

---

## Exit Codes

| Code | Meaning |
|---|---|
| `0` | Success — poll completed (0 or more rows written). |
| `1` | `TELEGRAM_BOT_TOKEN` is absent or empty. |

---

## Rollback

To pause polling without deleting the scheduler job, use:

```sh
gcloud scheduler jobs pause telegram-inbound-poller-schedule \
  --location=us-central1 \
  --project=clarity-staging-488201
```

To resume:

```sh
gcloud scheduler jobs resume telegram-inbound-poller-schedule \
  --location=us-central1 \
  --project=clarity-staging-488201
```

---

## Related

- `scripts/social_telegram_inbound_poll.py` — the entrypoint called by this job.
- `src/ham/social_telegram_inbound_collector.py` — the bounded `getUpdates` collector (F11/F12).
- `src/ham/social_telegram_transcript_store.py` — transcript store Protocol and backends.
- `src/ham/social_telegram_offset_store.py` — offset store Protocol and backends.
- `docs/M15_SCHEDULED_TICK_RUNBOOK.md` — companion runbook for the scheduler-tick route (M4).
