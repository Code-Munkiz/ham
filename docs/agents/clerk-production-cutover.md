# Clerk production cutover (Builder stabilization lane)

Ops note: auth and env changes are **not** performed from this document. This captures a **product/engineering decision** and rollout reminders only.

## 1. Current issue

- The live **production** Vercel bundle for `ham-nine-mu.vercel.app` has been observed using a Clerk publishable key classified as **`pk_test`** (development-style browser key).
- **Target:** Vercel **Production** `VITE_CLERK_PUBLISHABLE_KEY` should use Clerk **Production** publishable material (**`pk_live_…`**) for stable production session behavior.

## 2. Backend issuer alignment

- Cloud Run **`CLERK_JWT_ISSUER`** must match the **Clerk Frontend API issuer** for whatever Clerk application issues the browser session JWT (JWKS verification).
- **No backend issuer change is expected** when moving Vercel Production from **`pk_test`** to **`pk_live`** **if** both keys belong to the **same** Clerk application (e.g. instance slug **`sharing-gobbler-70`**) so issuer/JWKS stay aligned.

## 3. Data continuity and Clerk `sub`

HAM ties operator identity to Clerk’s JWT **`sub`** (user id) across:

- Workspace ownership / membership
- Chat sessions (when Clerk-scoped)
- Connected Tools / BYOK-style credential rows where keyed by user
- Voice / composer preferences and similar per-user stores

Clerk **production** users (and **`pk_live`** flows) can yield **different `sub` values** than **development/test** users—even for the same human email—depending on how identities were created and which Clerk environment issued sessions.

**Implication:** After a production Clerk cutover, **dev-era Firestore/workspace/chat/BYOK/prefs rows may not appear** for the “same” person if their **`sub` changed**. That is a **data identity** issue, not a JWT typo.

## 4. Current decision (greenfield)

For the **current Builder stabilization** phase:

- Treat production Clerk cutover as **greenfield** for hosted data visible under the new production identities.
- **No user/workspace migration job** now.
- **No Firestore mutation** now for continuity.
- Existing dev-era continuity is **explicitly not guaranteed** unless we reverse this decision later.

## 5. Later migration trigger

Build a deliberate **`sub` / user_id mapping or ETL** only if we **must** preserve existing dev-Clerk workspaces, chat history, BYOK secrets, or prefs across the cutover. Until then, assume operators may see an empty slate under production identities.

## 6. Rollback note

Rolling authentication back (e.g. returning to **`pk_test`** on Production) **does not restore prior associations**:

- Rows written under a **new production `sub`** do not automatically attach to an **old dev-era `sub`**.
- Treat rollback as **auth configuration rollback**, not implicit **data remap**.

## 7. Safe rollout checklist (human-operated)

1. **Clerk Dashboard:** confirm **`https://ham-nine-mu.vercel.app`** (and any required preview hosts) are allowed for **Production** origins / redirects per your Clerk integration settings.
2. **Vercel:** update **`VITE_CLERK_PUBLISHABLE_KEY`** for **Production** to the **`pk_live_…`** value from Clerk **Production** for the intended app (do not commit secrets; do not paste keys into tickets/chat logs).
3. **Preview:** keep **Preview** deployments on **`pk_test`** **unless** you intentionally standardize on **`pk_live`** for previews too (split env scopes if policies differ).
4. **Redeploy** Vercel **Production** so Vite rebuilds with inlined `VITE_*` values.
5. **Verify** the live production bundle still classifies as **`pk_live`** (prefix-only checks; never publish full keys).
6. **Smoke** signed-in flows at status endpoints only as needed: e.g. **`/api/me`**, workspace list/create, chat, Builder—report HTTP status / structured error codes without tokens.
