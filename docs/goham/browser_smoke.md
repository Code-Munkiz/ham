# GoHAM Managed Browser Smoke Checklist

GoHAM runs only in HAM Desktop with Local Control. It uses a separate managed
Chrome profile, not the operator's default browser profile.

## Demo Prompts

- `Open https://example.com and tell me what you see.`
- `GoHAM, research MiniMax M2.5 OpenRouter free tier context window.`
- `GoHAM, start at https://openrouter.ai and find information about MiniMax M2.5. Tell me whether it has a free tier and what context window is shown.`

## Smoke Checklist

- Observe path: Chrome opens visibly, leaves `about:blank`, navigates to the
  requested URL, and posts the v0 bounded observation.
- Search-first research path: GoHAM builds a DuckDuckGo URL directly, without
  typing into a search box, then uses bounded observe / enumerate / scroll /
  click-candidate actions.
- Direct URL research path: strong research intent may start from safe search
  when target terms are specific; observe-only direct URL prompts stay on the
  direct observe path.
- Pause / Resume / Take over: controls are visible during research and resume
  the same managed browser session.
- Stop cleanup: Stop GoHAM closes the managed Chrome session.
- No unsafe actions: no generic type/key behavior, no form fill, no submit/post,
  no login/purchase/download/upload/install.
- Evidence honesty: missing terms report `insufficient_evidence` or
  `budget_without_evidence`; search-provider title/query echo is not counted as
  evidence.
- Shop safety: Shop / Skills surfaces expose no execution buttons for GoHAM.

## Evidence Scope

Research summaries may include page count, redacted URLs, titles, bounded
evidence snippets from titles / URLs / candidate text, action counts, screenshot
count, stop reason, limitations, and suggested next step. Do not paste full
HTML, cookies, secrets, or raw page dumps.
