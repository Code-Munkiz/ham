# Deploy handoff: Vercel UI + Cloud Run (your steps)

The repo already includes CORS support (`HAM_CORS_ORIGINS`, `HAM_CORS_ORIGIN_REGEX`), an example API env file, and a verify script. **You** wire secrets and host-specific URLs in each provider.

**Staging source of truth (GCP):** project **`clarity-staging-488201`**, region **`us-central1`**, Cloud Run service **`ham-api`**. Commands and examples in **`docs/DEPLOY_CLOUD_RUN.md`** use these defaults. Production should live in a separate GCP project when your org requires it.

## 1. Cloud Run (Ham API)

1. **Build and push** the image (see `docs/DEPLOY_CLOUD_RUN.md`).
2. Create `.gcloud/ham-api-env.yaml` (gitignored) by copying  
   **`docs/examples/ham-api-cloud-run-env.yaml`** and editing:
   - Replace `https://your-app.vercel.app` with your **production** Vercel URL (and any custom domain as `https://…`).
   - Keep **`HAM_CORS_ORIGIN_REGEX`** if you use **Vercel preview** deployments (`*.vercel.app`); remove it only if you want a strict allow-list.
   - **Real chat (OpenRouter):** set **`HERMES_GATEWAY_MODE=openrouter`** and **`OPENROUTER_API_KEY`** (Secret Manager recommended on Cloud Run). Optional: **`DEFAULT_MODEL`** / **`HERMES_GATEWAY_MODEL`** (OpenRouter slug, e.g. `minimax/minimax-m2.5:free`). See **`docs/HERMES_GATEWAY_CONTRACT.md`**.
   - **Hermes HTTP gateway (e.g. private GCE VM):** **`HERMES_GATEWAY_MODE=http`**, **`HERMES_GATEWAY_BASE_URL`** (internal IP/DNS + port, no `/v1`), **`HERMES_GATEWAY_MODEL`**, and **`HERMES_GATEWAY_API_KEY`** via **Secret Manager**. Networking: **Direct VPC egress** preferred; **Serverless VPC Access connector** as fallback — see **`docs/DEPLOY_CLOUD_RUN.md`** (“Private Hermes on GCE”).
3. Deploy with **`--env-vars-file`** (not `--set-env-vars` for comma-separated lists). For **Cursor Cloud Agents**, also pass **`--set-secrets=CURSOR_API_KEY=ham-cursor-api-key:latest`** after creating the secret in **Secret Manager** (see **`docs/DEPLOY_CLOUD_RUN.md`** § “Cursor Cloud API key”).
   - **Secrets from `.env` (recommended):** merge local `.env` into your template without committing keys:
     ```bash
     ENV_FILE=$(python scripts/render_cloud_run_env.py)
     gcloud run deploy ham-api \
       --image us-central1-docker.pkg.dev/clarity-staging-488201/ham/ham-api:staging \
       --region us-central1 --platform managed --allow-unauthenticated \
       --env-vars-file "$ENV_FILE" --project clarity-staging-488201 \
       --set-secrets=CURSOR_API_KEY=ham-cursor-api-key:latest
     rm -f "$ENV_FILE"
     ```
   - Or edit **`.gcloud/ham-api-env.yaml`** directly (gitignored) and use that path — do **not** put `OPENROUTER_API_KEY` or `CURSOR_API_KEY` in tracked files.
4. Note the **service URL** (no trailing slash), e.g. `https://ham-api-….run.app`.

   **Dashboard project registry:** `POST /api/projects` and `GET /api/projects/{id}/agents` use a file-backed store on the API container (`~/.ham/projects.json`). With **Cloud Run scale-to-zero and multiple instances**, registration from the browser may land on instance A while the next request hits instance B, which returns **PROJECT_NOT_FOUND** until the project exists there. Mitigations: set **minimum instances = 1** for the API service, or accept that Agent Builder may need a **Retry** after deploy; local/single-process APIs do not see this.

5. **Verify** (use the **exact** browser origin you will open — production or a preview URL):

   ```bash
   chmod +x scripts/verify_ham_api_deploy.sh
   ./scripts/verify_ham_api_deploy.sh 'https://YOUR-SERVICE.run.app' 'https://YOUR-VERCEL-HOST.vercel.app'
   ```

   If this fails on OPTIONS or missing `Access-Control-Allow-Origin`, the API env does not allow that `Origin`.  
   If chat succeeds but the script fails with **mock-mode** detection, the API is still on **`HERMES_GATEWAY_MODE=mock`** (or miswired `http`). Set **`HAM_VERIFY_ALLOW_MOCK=1`** only when you **intentionally** verify a mock deployment.

## 2. Vercel (dashboard frontend)

The **React dashboard** is built and served only from Vercel. **If the Vercel project Root Directory is the repo root**, use root `vercel.json` (build + `outputDirectory` + SPA rewrite). **If Root Directory is `frontend`**, Vercel reads **`frontend/vercel.json`** for SPA rewrites — without that, direct visits to **`/agents`** (or refresh) can 404. The **Cloud Run image** (`Dockerfile`) ships **FastAPI only** — it does not contain `frontend/dist`. If you redeploy Vercel but not the API, pages like **Agent Builder** may load but fail with a clear error until **GET `/api/projects/{id}/agents`** exists on the API host. If you redeploy the API but not Vercel, new **UI** routes will not appear until you trigger a **new Vercel production deployment** from the commit that includes those files.

1. Project → **Settings → Environment Variables**:
   - **`VITE_HAM_API_BASE`** = your Cloud Run **origin** only, e.g. `https://ham-api-xxxxx.run.app` — **no trailing slash**, **no `/api` suffix** (the app requests `/api/...` itself; `…/api` + `/api/...` → 404).
   - Scope: enable for **Production** and **Preview** (previews need it too).
2. **Redeploy** after any change to `VITE_*` (Vite inlines them at **build** time), and after merging **frontend** changes (new pages, nav, etc.).

## 3. Quick sanity checks

- Browser **Network** tab: `POST …/api/chat` must go to **`…run.app`**, not `127.0.0.1`.
- If chat fails with a network error but `curl` works: almost always **CORS** — wrong preview hostname or missing regex / origin list on Cloud Run.

## Reference

- `docs/DEPLOY_CLOUD_RUN.md` — GCP commands and smoke `curl`
- `docs/examples/ham-api-cloud-run-env.yaml` — API env template
- `frontend/.env.example` — local vs production env notes
