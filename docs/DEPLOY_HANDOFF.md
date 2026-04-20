# Deploy handoff: Vercel UI + Cloud Run (your steps)

The repo already includes CORS support (`HAM_CORS_ORIGINS`, `HAM_CORS_ORIGIN_REGEX`), an example API env file, and a verify script. **You** wire secrets and host-specific URLs in each provider.

## 1. Cloud Run (Ham API)

1. **Build and push** the image (see `docs/DEPLOY_CLOUD_RUN.md`).
2. Create `.gcloud/ham-api-env.yaml` (gitignored) by copying  
   **`docs/examples/ham-api-cloud-run-env.yaml`** and editing:
   - Replace `https://your-app.vercel.app` with your **production** Vercel URL (and any custom domain as `https://…`).
   - Keep **`HAM_CORS_ORIGIN_REGEX`** if you use **Vercel preview** deployments (`*.vercel.app`); remove it only if you want a strict allow-list.
   - **Real chat (OpenRouter):** set **`HERMES_GATEWAY_MODE=openrouter`** and **`OPENROUTER_API_KEY`** (Secret Manager recommended on Cloud Run). Optional: **`DEFAULT_MODEL`** / **`HERMES_GATEWAY_MODEL`** (OpenRouter slug, e.g. `openai/gpt-4o-mini`). See **`docs/HERMES_GATEWAY_CONTRACT.md`**.
   - **Hermes HTTP gateway:** **`HERMES_GATEWAY_MODE=http`**, **`HERMES_GATEWAY_BASE_URL`**, **`HERMES_GATEWAY_API_KEY`** as needed.
3. Deploy with **`--env-vars-file`** (not `--set-env-vars` for comma-separated lists).
   - **Secrets from `.env` (recommended):** merge local `.env` into your template without committing keys:
     ```bash
     ENV_FILE=$(python scripts/render_cloud_run_env.py)
     gcloud run deploy ham-api-staging \
       --image us-west1-docker.pkg.dev/PROJECT_ID/ham/ham-api:staging \
       --region us-west1 --platform managed --allow-unauthenticated \
       --env-vars-file "$ENV_FILE" --project PROJECT_ID
     rm -f "$ENV_FILE"
     ```
   - Or edit **`.gcloud/ham-api-env.yaml`** directly (gitignored) and use that path — do **not** put `OPENROUTER_API_KEY` in tracked files.
4. Note the **service URL** (no trailing slash), e.g. `https://ham-api-….run.app`.

5. **Verify** (use the **exact** browser origin you will open — production or a preview URL):

   ```bash
   chmod +x scripts/verify_ham_api_deploy.sh
   ./scripts/verify_ham_api_deploy.sh 'https://YOUR-SERVICE.run.app' 'https://YOUR-VERCEL-HOST.vercel.app'
   ```

   If this fails on OPTIONS or missing `Access-Control-Allow-Origin`, the API env does not allow that `Origin`.

## 2. Vercel (dashboard frontend)

The **React dashboard** is built and served only from Vercel (see root `vercel.json`). The **Cloud Run image** (`Dockerfile`) ships **FastAPI only** — it does not contain `frontend/dist`. If you redeploy the API but not Vercel, new **UI** routes (e.g. **Skills** at `/skills`) will not appear until you trigger a **new Vercel production deployment** from the commit that includes those files.

1. Project → **Settings → Environment Variables**:
   - **`VITE_HAM_API_BASE`** = your Cloud Run URL (no trailing slash).
   - Scope: enable for **Production** and **Preview** (previews need it too).
2. **Redeploy** after any change to `VITE_*` (Vite inlines them at **build** time), and after merging **frontend** changes (new pages, nav, etc.).

## 3. Quick sanity checks

- Browser **Network** tab: `POST …/api/chat` must go to **`…run.app`**, not `127.0.0.1`.
- If chat fails with a network error but `curl` works: almost always **CORS** — wrong preview hostname or missing regex / origin list on Cloud Run.

## Reference

- `docs/DEPLOY_CLOUD_RUN.md` — GCP commands and smoke `curl`
- `docs/examples/ham-api-cloud-run-env.yaml` — API env template
- `frontend/.env.example` — local vs production env notes
