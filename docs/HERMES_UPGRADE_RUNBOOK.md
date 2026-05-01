# HAM / Hermes Upgrade Runbook

Purpose: give Cursor a repeatable, safe path to upgrade the Hermes gateway used by HAM without breaking chat, vision, attachments, sessions, or Cloud Run configuration.

## Current known architecture

HAM does **not** run Hermes inside the `ham-api` Cloud Run container. HAM calls a separate Hermes gateway over HTTP.

```txt
HAM Webapp
  → ham-api Cloud Run
  → HERMES_GATEWAY_BASE_URL=http://10.138.0.2:8642
  → hermes-api-vm user-systemd Hermes gateway
```

Current known Hermes target:

```txt
GCP project: clarity-staging-488201
VM: hermes-api-vm
Zone: us-west1-a
Private IP: 10.138.0.2
Gateway port: 8642
Install path: /home/user/.hermes/hermes-agent
Config path: /home/user/.hermes/config.yaml
Service: /home/user/.config/systemd/user/hermes-gateway.service
Restart command:
sudo -u user env XDG_RUNTIME_DIR=/run/user/1000 systemctl --user restart hermes-gateway
```

Current successful upgrade baseline:

```txt
Hermes version/tag: v2026.4.23
Hermes peeled commit: bf196a3fc0fd1f79353369e8732051db275c6276
Previous commit before upgrade: 1ffcb7b39eedf6439d655a44e2355ebce4321335
Rollback branch used: backup/pre-v2026.4.23-flip-20260430-234100
Config backup pattern: /home/user/.hermes/config.yaml.pre-v<version>-<timestamp>
```

HAM-side persistence is separate from Hermes:

```txt
HAM chat sessions: Firestore
HAM attachments: GCS
Hermes local ~/.hermes data: Hermes-internal, not HAM’s source of truth
```

Therefore, a Hermes app upgrade should not delete HAM chat history or attachments, as long as the upgrade does not touch HAM Firestore/GCS/Cloud Run persistence settings.

---

## Hard safety rules

Do not:

- Print API keys, tokens, PATs, `.git-credentials`, `auth.json`, or secret values.
- Replace all Cloud Run env vars.
- Change HAM Cloud Run env unless explicitly required.
- Change `HERMES_GATEWAY_BASE_URL` unless intentionally migrating gateways.
- Touch HAM frontend/backend code during a Hermes-only upgrade.
- Touch Cursor SDK bridge, mission SSE, Cloud Agent launch, or repo policy.
- Use `git pull`, merge, rebase, or reset blindly on the Hermes VM.
- Carry local fork commits forward unless owner explicitly approves.
- Restart production Hermes until dry-run probes pass.
- Treat `/api/upload` as part of the Hermes upgrade. It is unrelated.

Always:

- Confirm the true gateway target first.
- Capture rollback information before mutation.
- Dry-run the target Hermes version if practical.
- Run authenticated text, stream, and multimodal probes.
- Smoke HAM after upgrade.
- Roll back immediately if text chat, streaming, or `/api/hermes-hub` breaks.

---

## Standard decision labels

Use these labels in reports:

```txt
HERMES_TRUE_GATEWAY_TARGET_FOUND
HERMES_UPGRADE_NO_PERSISTENCE_TOUCH_CONFIRMED
HERMES_RELEASE_TARGET_RECONCILED
HERMES_CUSTOM_COMMITS_CLASSIFIED
HERMES_DRY_RUN_PLAN_READY
HERMES_V<version>_DRYRUN_PASSED
HERMES_PRE_FLIP_BACKUP_CAPTURED
HERMES_ROLLBACK_REF_CAPTURED
HERMES_PROD_CHECKOUT_<version>
HERMES_PROD_GATEWAY_RESTARTED
HERMES_PROD_HEALTH_PASSED
HERMES_PROD_CHAT_PASSED
HERMES_PROD_STREAMING_PASSED
HERMES_PROD_MULTIMODAL_PASSED
HERMES_UPGRADED_TO_<version>
HAM_TEXT_CHAT_PASSED_AFTER_HERMES_UPGRADE
HAM_VISION_CHAT_PASSED_AFTER_HERMES_UPGRADE
HAM_ATTACHMENTS_PASSED_AFTER_HERMES_UPGRADE
HAM_SESSION_RECALL_PASSED_AFTER_HERMES_UPGRADE
HERMES_UPGRADE_ROLLED_BACK
HERMES_UPGRADE_NOT_SAFE_YET
```

---

## Phase 0 — Confirm target and persistence separation

### 0.1 Confirm HAM Cloud Run points to the expected Hermes gateway

```bash
gcloud run services describe ham-api \
  --project=clarity-staging-488201 \
  --region=us-central1 \
  --format=yaml
```

Report only safe values:

```txt
latestReadyRevisionName
container image
HERMES_GATEWAY_MODE
HERMES_GATEWAY_BASE_URL
HERMES_GATEWAY_MODEL
HAM_CHAT_SESSION_STORE
HAM_CHAT_SESSION_FIRESTORE_PROJECT
HAM_CHAT_SESSION_FIRESTORE_DATABASE
HAM_CHAT_SESSION_FIRESTORE_COLLECTION
HAM_CHAT_ATTACHMENT_STORE
HAM_CHAT_ATTACHMENT_BUCKET
HAM_CHAT_ATTACHMENT_PREFIX
whether secret refs exist: yes/no only
```

Expected:

```txt
HERMES_GATEWAY_MODE=http
HERMES_GATEWAY_BASE_URL=http://10.138.0.2:8642
HAM_CHAT_SESSION_STORE=firestore
HAM_CHAT_ATTACHMENT_STORE=gcs
```

Label:

```txt
HERMES_UPGRADE_NO_PERSISTENCE_TOUCH_CONFIRMED
```

### 0.2 Confirm the GCE resource owning `10.138.0.2`

```bash
gcloud compute instances list \
  --project=clarity-staging-488201 \
  --filter="networkInterfaces.networkIP=10.138.0.2" \
  --format="table(name,zone,status,networkInterfaces[0].networkIP,tags.items)"
```

Expected:

```txt
hermes-api-vm
zone: us-west1-a
```

Label:

```txt
HERMES_TRUE_GATEWAY_TARGET_FOUND
```

---

## Phase 1 — Read-only current-state audit

Run these on the Hermes VM or through IAP/SSH. Do not print secrets.

```bash
sudo -u user git -C /home/user/.hermes/hermes-agent rev-parse HEAD
sudo -u user git -C /home/user/.hermes/hermes-agent describe --tags --always --dirty
sudo -u user git -C /home/user/.hermes/hermes-agent status --short --branch
sudo -u user env XDG_RUNTIME_DIR=/run/user/1000 systemctl --user status hermes-gateway --no-pager
sudo -u user env XDG_RUNTIME_DIR=/run/user/1000 systemctl --user cat hermes-gateway
```

Confirm listeners:

```bash
sudo ss -lntp | grep -E ':8642|:8000' || true
curl -sS -i http://10.138.0.2:8642/health
```

Do not use broad `cat ~/.hermes/auth.json`, `cat ~/.git-credentials`, or raw env dumps.

---

## Phase 2 — Release target reconciliation

Find the new official Hermes release tag from the authoritative source, usually the official Hermes GitHub releases.

Before fetching tags, first use a remote metadata check where possible:

```bash
git -C /home/user/.hermes/hermes-agent ls-remote --tags origin refs/tags/<target-tag>
```

If local tag metadata needs refresh, get owner approval, then:

```bash
sudo -u user git -C /home/user/.hermes/hermes-agent fetch --tags origin
```

Resolve tag carefully. Some release tags are annotated:

```bash
sudo -u user git -C /home/user/.hermes/hermes-agent rev-parse <target-tag>
sudo -u user git -C /home/user/.hermes/hermes-agent rev-parse <target-tag>^{}
```

Use the peeled commit (`<target-tag>^{}`) as the actual release commit.

Compare current branch to target:

```bash
sudo -u user git -C /home/user/.hermes/hermes-agent rev-list --count <target-tag>..HEAD
sudo -u user git -C /home/user/.hermes/hermes-agent rev-list --count HEAD..<target-tag>
sudo -u user git -C /home/user/.hermes/hermes-agent log --oneline --decorate <target-tag>..HEAD
sudo -u user git -C /home/user/.hermes/hermes-agent log --stat --oneline <target-tag>..HEAD
```

Classify any local custom commits:

```txt
KEEP_REQUIRED_FOR_HAM_GATEWAY
KEEP_OPTIONAL_GOVERNANCE
DROP_DEMO_DOCS
DROP_HERMES_NATIVE_VOICE
DROP_RISKY_OPERATIONAL_JUNK
NEEDS_OWNER_DECISION
```

Default strategy from the v2026.4.23 upgrade:

```txt
RESET_TO_TAG_NO_LOCAL_PORTS
```

Meaning: use the official release tag cleanly and do not carry old local demo/voice/trust commits forward unless owner explicitly decides otherwise.

---

## Phase 3 — Isolated dry run before production flip

Use a separate worktree and isolated runtime home. Do not touch production service.

### 3.1 Create worktree

```bash
sudo -u user mkdir -p /home/user/.hermes/dryruns

sudo -u user git -C /home/user/.hermes/hermes-agent worktree add \
  /home/user/.hermes/dryruns/hermes-agent-<target-tag> \
  <target-tag>

sudo -u user git -C /home/user/.hermes/dryruns/hermes-agent-<target-tag> rev-parse HEAD
sudo -u user git -C /home/user/.hermes/dryruns/hermes-agent-<target-tag> describe --tags --always --dirty
```

### 3.2 Isolated venv if possible

**Prerequisite:** ensure the VM has free space on `/` before creating a second venv (`df -h /`). On this image, `python3 -m venv` can fail if **`python3-venv` / `ensurepip`** is missing (common on minimal Debian) or if `/` is **100% full**.

Preferred:

```bash
sudo -u user python3 -m venv /home/user/.hermes/dryruns/venv-<target-tag>
sudo -u user /home/user/.hermes/dryruns/venv-<target-tag>/bin/pip install -U pip
sudo -u user /home/user/.hermes/dryruns/venv-<target-tag>/bin/pip install -e /home/user/.hermes/dryruns/hermes-agent-<target-tag>
```

If VM disk/ensurepip blocks this, fallback is allowed for dry-run only:

```txt
Use production venv without mutating it.
Load release code through PYTHONPATH pointing at isolated worktree.
Label this fallback explicitly.
```

### 3.3 Isolated HERMES_HOME

Use tmpfs so temporary copied secrets are wiped easily:

```bash
rm -rf /dev/shm/home-<target-tag>
mkdir -p /dev/shm/home-<target-tag>
chmod 700 /dev/shm/home-<target-tag>
```

Copy minimum runtime config without printing contents:

```bash
cp /home/user/.hermes/config.yaml /dev/shm/home-<target-tag>/config.yaml
chmod 600 /dev/shm/home-<target-tag>/config.yaml

if [ -f /home/user/.hermes/auth.json ]; then
  cp /home/user/.hermes/auth.json /dev/shm/home-<target-tag>/auth.json
  chmod 600 /dev/shm/home-<target-tag>/auth.json
fi

if [ -f /home/user/.hermes/.env ]; then
  cp /home/user/.hermes/.env /dev/shm/home-<target-tag>/.env
  chmod 600 /dev/shm/home-<target-tag>/.env
fi
```

If `.env` controls the API host/port, force it to temp bind only:

```txt
API_SERVER_HOST=127.0.0.1
API_SERVER_PORT=18643
```

Hermes loads **`.env` after / alongside `config.yaml`**: if production `.env` still has `API_SERVER_PORT=8642`, the temp gateway can try to bind **`8642`** and fail while production holds that port. Prefer editing **only the isolated** `/dev/shm/home-<target-tag>/.env` copy (never production) so **`API_SERVER_HOST=127.0.0.1`** and **`API_SERVER_PORT=18643`** match the temp listen.

### 3.4 Start temp gateway

Do not use `--replace`.
Do not bind to `0.0.0.0`.
Do not touch `10.138.0.2:8642`.

Example fallback command:

```bash
HERMES_HOME=/dev/shm/home-<target-tag> \
API_SERVER_ENABLED=true \
API_SERVER_HOST=127.0.0.1 \
API_SERVER_PORT=18643 \
PYTHONPATH=/home/user/.hermes/dryruns/hermes-agent-<target-tag> \
/home/user/.hermes/hermes-agent/venv/bin/python \
-m hermes_cli.main gateway run
```

Probe via IAP tunnel if running from local machine.

When driving `gcloud`/SSH from **Windows PowerShell**, avoid pasting multi-line `bash` chains with `&&` inside a single `--command=...` unless quoted for the remote shell—split steps or use `sudo -u user bash -lc '...'`.

### 3.5 Authenticated probes

Use API key only in process env. Do not print it.

Probe temp gateway:

```txt
GET /health
GET /v1/models
POST /v1/chat/completions non-stream
POST /v1/chat/completions stream:true
POST /v1/chat/completions multimodal image_url with image >10x10
```

Expected:

```txt
health 200
models 200
chat.completion shape
SSE data: chunks with choices[0].delta.content
[DONE]
multimodal envelope accepted or clean provider limitation
```

Labels if pass:

```txt
HERMES_<target>_HEALTH_PASSED
HERMES_<target>_MODELS_PASSED
HERMES_<target>_CHAT_PASSED
HERMES_<target>_STREAMING_PASSED
HERMES_<target>_MULTIMODAL_PASSED
```

Stop temp process and clean temp home:

```bash
rm -rf /dev/shm/home-<target-tag>
```

Confirm production untouched:

```bash
curl -sS -i http://10.138.0.2:8642/health
curl -sS https://ham-api-vlryahjzwa-uc.a.run.app/api/hermes-hub
```

---

## Phase 4 — Production flip

Only after dry run passes and owner approves.

### 4.1 Backup

```bash
sudo -u user git -C /home/user/.hermes/hermes-agent rev-parse HEAD
sudo -u user git -C /home/user/.hermes/hermes-agent describe --tags --always --dirty
sudo -u user git -C /home/user/.hermes/hermes-agent status --short --branch
```

Create backup branch:

```bash
sudo -u user git -C /home/user/.hermes/hermes-agent branch backup/pre-<target-tag>-flip-$(date +%Y%m%d-%H%M%S) HEAD
```

Backup config:

```bash
sudo cp /home/user/.hermes/config.yaml /home/user/.hermes/config.yaml.pre-<target-tag>-$(date +%Y%m%d-%H%M%S)
```

Save previous commit marker:

```bash
sudo -u user git -C /home/user/.hermes/hermes-agent rev-parse HEAD | sudo tee /home/user/.hermes/hermes-agent.pre-<target-tag>-commit.txt
```

Labels:

```txt
HERMES_PRE_FLIP_BACKUP_CAPTURED
HERMES_ROLLBACK_REF_CAPTURED
```

### 4.2 Checkout release

```bash
sudo -u user git -C /home/user/.hermes/hermes-agent checkout <target-tag>
sudo -u user git -C /home/user/.hermes/hermes-agent rev-parse HEAD
sudo -u user git -C /home/user/.hermes/hermes-agent describe --tags --always --dirty
```

Expected: release tag / peeled commit.

If Git warns **`unable to rmdir 'ham': Directory not empty`**, that indicates a **nested checkout** present on disk (untracked / separate tree). It does not block the flip; treat it as **cleanup debt** (see maintenance notes).

### 4.3 Restart gateway

```bash
sudo -u user env XDG_RUNTIME_DIR=/run/user/1000 systemctl --user restart hermes-gateway
sudo -u user env XDG_RUNTIME_DIR=/run/user/1000 systemctl --user status hermes-gateway --no-pager
```

Inspect logs only for errors. Redact if necessary:

```bash
sudo -u user env XDG_RUNTIME_DIR=/run/user/1000 journalctl --user -u hermes-gateway -n 80 --no-pager
```

Labels:

```txt
HERMES_PROD_CHECKOUT_<target>
HERMES_PROD_GATEWAY_RESTARTED
```

---

## Phase 5 — Post-flip probes

Run authenticated probes against production gateway:

```txt
http://10.138.0.2:8642
```

Required:

```txt
GET /health
GET /v1/models
POST /v1/chat/completions non-stream
POST /v1/chat/completions stream:true
POST /v1/chat/completions multimodal image_url >10x10
```

Labels:

```txt
HERMES_PROD_HEALTH_PASSED
HERMES_PROD_CHAT_PASSED
HERMES_PROD_STREAMING_PASSED
HERMES_PROD_MULTIMODAL_PASSED
```

HAM control-plane probes:

```bash
curl -sS https://ham-api-vlryahjzwa-uc.a.run.app/api/status
curl -sS https://ham-api-vlryahjzwa-uc.a.run.app/api/hermes-hub
```

---

## Phase 6 — Webapp smoke

Open:

```txt
https://ham-nine-mu.vercel.app
```

Test:

```txt
Text-only chat streams
Image attachment uploads
Image/vision works or returns clean provider limitation
No generic 409
Existing chat session recall works
GCS-backed attachment reload works
Voice transcription still works
```

Labels:

```txt
HAM_TEXT_CHAT_PASSED_AFTER_HERMES_UPGRADE
HAM_VISION_CHAT_PASSED_AFTER_HERMES_UPGRADE
HAM_ATTACHMENTS_PASSED_AFTER_HERMES_UPGRADE
HAM_SESSION_RECALL_PASSED_AFTER_HERMES_UPGRADE
HAM_VOICE_PASSED_AFTER_HERMES_UPGRADE
HERMES_UPGRADE_ROLLOUT_COMPLETE
```

---

## Rollback

If health, chat, stream, or HAM smoke breaks:

```bash
PREV_COMMIT="$(cat /home/user/.hermes/hermes-agent.pre-<target-tag>-commit.txt)"

sudo -u user git -C /home/user/.hermes/hermes-agent checkout "$PREV_COMMIT"

sudo -u user env XDG_RUNTIME_DIR=/run/user/1000 systemctl --user restart hermes-gateway

curl -sS -i http://10.138.0.2:8642/health
curl -sS https://ham-api-vlryahjzwa-uc.a.run.app/api/hermes-hub
```

Only reinstall dependencies if rollback startup clearly requires it.

Label:

```txt
HERMES_UPGRADE_ROLLED_BACK
```

---

## Maintenance notes

### Boot disk full / growing the root filesystem

If `df -h /` shows **`/` at or near 100%** before a dry-run venv or `pip install`:

1. Identify the VM **boot disk** from `gcloud compute instances describe` (`disks[0].source`).
2. Prefer a **snapshot** first, then **`gcloud compute disks resize DISK_NAME --zone=ZONE --size=NN`** (size is numeric GB).
3. Inside the VM, confirm **`lsblk`** shows the **disk** larger than the **root partition**.
4. If the partition did not auto-expand, grow it:
   - **ext4:** install **`cloud-guest-utils`** (`growpart`) if missing, then **`sudo growpart /dev/DEVICE PARTITIONNUM`** (often `/dev/sda 1`) and **`sudo resize2fs /dev/sda1`** (adjust device to match **`df` / `lsblk`**—do not guess NVMe vs SCSI naming).
   - **xfs:** **`sudo xfs_growfs /`**
5. Confirm **`df -h /`** reflects the new capacity.

Hermes **`hermes-gateway`** usually survives an online filesystem grow **without restart**; only restart if health checks fail.

### Untracked / junk in the Hermes repo directory

The Hermes VM previously had untracked artifacts:

```txt
/home/user/.hermes/hermes-agent/ham/
/home/user/.hermes/hermes-agent/push_trust.py
/home/user/.hermes/hermes-agent/push_trust_model.py
```

These are not part of the upgrade path.

**Credential hygiene:** if any helper script contained a **plaintext GitHub PAT** or similar, **rotate that credential in GitHub** and remove the scripts in a coordinated cleanup—do not paste token material into logs or commits.

Clean them in a separate maintenance task only after verifying they are not used by `hermes-gateway.service`.

Label:

```txt
HERMES_VM_UNTRACKED_ARTIFACTS_CLEANUP_REQUIRED
```

---

## Final report template

```txt
Decision labels:
Old Hermes commit:
New Hermes tag:
New Hermes commit:
Backup branch:
Config backup path:
Dry-run result:
Production restart result:
Hermes probes:
HAM smoke:
Rollback needed:
Known issues:
Next maintenance item:
```
