# HAM Three-Lane Architecture

## Purpose

HAM is operated through **three lanes** that share product surfaces but own different trust, data, and execution boundaries:

1. **Web app lane** — browser-hosted command center  
2. **Desktop app lane** — local Electron application on the user’s machine  
3. **Cloud / hosted agent lane** — APIs, automation, durable services, and headless agents  

No single lane replaces the others. Mis-aligning expectations (for example “the hosted SPA alone controls my laptop”) creates support and security confusion.

---

## Lane 1 — Web app

### Positioning

- **Hosted browser command center** (for example Vercel-built frontend talking to a hosted API, often **Cloud Run**).
- Primary navigation under **`/workspace/*`**: chat, files, terminal, settings, social cockpit (including policy), operations, missions/conductor, skills, profiles, memory, and related workspace chrome.
- **Auth** (for example Clerk when configured), **workspace/session** management, and operator **visibility**: steering, approvals, review, configuration.

### Truth

- **Production-oriented**, with **beta / rough edges** (legacy redirects, evolving IA, features gated by env).
- The **browser does not magically see the user’s laptop**. **Local files**, **local browser profile**, and **machine-scoped control** require a **bridge**: configured **local runtime URL**, **desktop app**, and/or **explicit hosted automation**—not “just open the website.”

---

## Lane 2 — Desktop app

### Positioning

- **Electron** application (**`desktop/`**): **Windows-first** packaging and release workflow today.
- **Local machine surface**: local files, local browser/session context where implemented, **local-control** modules, **desktop notifications**, and **trusted local policy** (kill switch, audit hooks as designed).
- Best for **user-local** powers that must not be impersonated from a random tab on `*.vercel.app` alone.

### Truth

- **Real lane** (substantial implementation and tests), **not** a decorative stub—still **beta** relative to full product polish.
- **Windows x64** builds and **tag-driven** desktop release automation exist; **do not** imply **Linux desktop installers** or a supported **Linux desktop app** path in product copy (see operator CLI notes and desktop docs).
- **Electron** remains relevant for **Windows / Mac / shared desktop** direction where applicable; **do not** revive **Linux-specific desktop app/demo** paths as product.
- **High-autonomy local/browser behavior** should be discussed as **GoHAM mode** (see [Naming / product truth](#naming--product-truth)), not as a vague “agent mode.”
- **Shipping / downloads:** see **[`desktop/SUPPORT_MATRIX.md`](desktop/SUPPORT_MATRIX.md)** (Windows portable today; Linux/macOS packaged paths explicitly out of scope).

---

## Lane 3 — Cloud / hosted agent lane

### Positioning

- **Headless hosted automation** and **API layer**: **Cloud Run**, **Vercel** (static + rewrites), **Firestore**, **Secret Manager**, **Hermes** gateway, **Cursor / Factory / Droid-adjacent** integrations, **CI/CD**, managed missions/jobs surfaces, **audit** logs, service-account and API-driven workflows.
- Best for **durable automation**, **repo work**, **hosted agents**, and **operator-owned** cloud infrastructure.

### Truth

- **Mixed maturity**: **production** API core **plus** evolving hosted agent and mission features (some phases documented ahead of full UX parity).
- **Cloud should not pretend to be the user’s laptop.** Hosted **Playwright** or **`/api/browser*`-style** automation runs **on the API host’s environment** unless explicitly designed otherwise—it is **not** the same contract as **desktop local control** (see [`docs/capabilities/computer_control_pack_v1.md`](capabilities/computer_control_pack_v1.md) and [`docs/desktop/local_control_v1.md`](desktop/local_control_v1.md)).
- **Browser/computer control** that **requires** the end user’s **machine** and **OS context** belongs in the **desktop/local** lane **unless** the product deliberately uses **hosted** browser automation and messaging is honest about that.

---

## Cross-lane boundary table

Capability-centric view. Cells are **who leads** for that concern; **—** means “not the primary owner.” Overlap is normal; **Notes** carry the nuance.

| Capability | Web | Desktop | Cloud | Notes |
|------------|:---:|:-------:|:-----:|-------|
| **Chat / session memory** | ● | ○ | ● | **Cloud** persists sessions (for example SQLite locally for dev, Firestore/multi-instance patterns when configured). **Web** is the main UI; **desktop** embeds the same renderer with different shell/runtime hints. |
| **Workspace tenancy** | ● | ○ | ● | **Cloud** APIs and stores enforce workspace RBAC; **web** is the management UX. |
| **Browser / computer control** | ○ | ● | ○ | **Desktop** owns **local** browser-real → machine escalation per product policy. **Cloud** may expose **hosted** `/api/browser*` automation—**separate** trust boundary. **Web** does not directly drive the user’s OS without a bridge. |
| **Local files** | ○ | ● | ○ | **Desktop** has native file context; **web** reaches disk only via **configured local/API bridge** and workspace root policy—not “cloud disk = my laptop.” |
| **Social cockpit / HAMgomoon** | ● | ○ | ● | **Web**: settings-first **social cockpit** and policy UI. **Cloud**: Telegram/social automation and **HAMgomoon**-related server modules where enabled. Treat **live** social/autonomy as **explicitly scoped** operator features. |
| **Agent proposal / review queues** | ● | ○ | ● | **Web** surfaces operator queues; **cloud** implements managed missions, approvals, and feed persistence. |
| **Droid / Factory execution** | ○ | ○ | ● | Heavy execution is **subprocess/CLI/hosted** muscle; **web** steers and reviews outcomes **through HAM**, not by re-embedding vendor stacks in the browser. |
| **Hermes model gateway** | ○ | ○ | ● | Browser **never** calls Hermes directly; **cloud** adapts gateway modes (`HERMES_GATEWAY_*`) and routes. |
| **Secrets / connected accounts** | — | ○ | ● | **Cloud** uses Secret Manager / env contracts; **desktop** may hold local bridge secrets; **web** bundles must not leak raw keys. |
| **Logs / audit trails** | ○ | ● | ● | **Cloud** server audit sinks; **desktop** may append **redacted** local JSONL; **web** displays summaries where wired. |
| **Desktop release / build** | — | ● | ○ | **Desktop** + CI **Windows** packaging; not a web concern. |
| **Hosted deployment** | ○ | ○ | ● | **Vercel** frontend + **Cloud Run** (or equivalent) API patterns; see deploy docs. |
| **High-autonomy GoHAM mode** | ○ | ● | ● | **GoHAM** spans policy and APIs (`goham` planner, Ham-X autonomy modules, desktop bridge contexts). Requires **clear permission and safety docs** before marketing aggressive autonomy—**do not** conflate with generic “agent mode.” |

**Legend:** ● primary owner · ○ meaningful participant · — not a primary surface

---

## Naming / product truth

- Use **“GoHAM mode”** for **high-autonomy** behavior in product language.
- **Do not** use **“HAM Agent Mode”** for that concept—reserve clearer terminology to avoid mixing IDE marketing with HAM’s autonomy lanes.
- **HAMgomoon** names the **Telegram / social persona and automation lane** in code and ops where relevant; it is **not** a generic synonym for the whole web app.
- **“Social cockpit”** can refer to the **broader product section** (settings-first social UX) as well as server-side social features—disambiguate in runbooks when debugging.
- **Do not** claim **browser/local computer control from the hosted web app alone** without naming the **bridge**, **local runtime**, or **desktop** piece.
- **Do not** imply **Linux desktop app support** or **Linux installers** as a current shipping path unless docs and packaging explicitly say otherwise.

---

## Maturity summary

| Lane | Maturity (honest) |
|------|-------------------|
| **Web app** | **Production-oriented**, **beta / rough edges** in IA and some legacy surfaces |
| **Desktop app** | **Beta**, **Windows-first** today |
| **Cloud lane** | **Mixed**: **production** API core **plus** **evolving** hosted agent/automation |

---

## Recommended roadmap

Small, **PR-sized** follow-ups (not commitments—prioritize with the team):

1. Add a **visual three-lane diagram** once the wording stabilizes.
2. **Clarify workspace / local runtime** UX copy where users confuse Cloud Run disk with local disk.
3. ~~**Desktop shipping/support matrix** (Windows today; macOS/Linux stance explicit)~~ — **[`desktop/SUPPORT_MATRIX.md`](desktop/SUPPORT_MATRIX.md)**.
4. **Browser/computer-control boundary** one-pager cross-linking desktop local control vs hosted `/api/browser*`.
5. **Harden GoHAM permission model docs** before expanding **high-autonomy** flows.
6. **Clean up stale docs** that imply unsupported **Linux desktop** installers or paths.

---

## Related reading

- [`VISION.md`](../VISION.md), [`AGENTS.md`](../AGENTS.md) — pillars and repo index  
- [`DEPLOY_CLOUD_RUN.md`](DEPLOY_CLOUD_RUN.md), [`DEPLOY_HANDOFF.md`](DEPLOY_HANDOFF.md) — hosted deploy  
- [`desktop/SUPPORT_MATRIX.md`](desktop/SUPPORT_MATRIX.md) — Windows-first packaged desktop matrix  
- [`desktop/local_control_v1.md`](desktop/local_control_v1.md) — desktop local control product path  
- [`capabilities/computer_control_pack_v1.md`](capabilities/computer_control_pack_v1.md) — control-plane semantics  
