# Ham FastAPI for Cloud Run (and local smoke tests).
# Cloud Run sets PORT; default 8080 for local `docker run`.
FROM python:3.12-slim-bookworm

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app \
    GIT_TERMINAL_PROMPT=0

# Backend-only Cursor SDK bridge runtime (Node 22).
# git: Claude Code CLI expects a git binary for workspace introspection in headless runs.
RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates curl gnupg git \
    && mkdir -p /etc/apt/keyrings \
    && curl -fsSL https://deb.nodesource.com/gpgkey/nodesource-repo.gpg.key \
      | gpg --dearmor -o /etc/apt/keyrings/nodesource.gpg \
    && echo "deb [signed-by=/etc/apt/keyrings/nodesource.gpg] https://deb.nodesource.com/node_22.x nodistro main" \
      > /etc/apt/sources.list.d/nodesource.list \
    && apt-get update \
    && apt-get install -y --no-install-recommends nodejs \
    && rm -rf /var/lib/apt/lists/*

# Claude Agent SDK spawns the Claude Code CLI. The PyPI wheel may ship a bundled
# binary that fails in slim containers; prefer the npm CLI on PATH when present.
RUN npm install -g @anthropic-ai/claude-code \
    && command -v claude

COPY requirements.txt .
# Browser runtime: pip installs `playwright` but browsers are a separate download.
# --with-deps pulls Debian packages Chromium needs in slim images.
RUN pip install --no-cache-dir -r requirements.txt \
    && python -m playwright install --with-deps chromium

# Install backend-only Node bridge dependencies (kept isolated from frontend).
COPY src/integrations/cursor_sdk_bridge/package.json src/integrations/cursor_sdk_bridge/package-lock.json src/integrations/cursor_sdk_bridge/
RUN npm --prefix src/integrations/cursor_sdk_bridge ci --omit=dev

# TTS and other top-level `models.*` imports (src.api.tts_endpoint, src.api.audio_upload)
COPY models/ models/

COPY src/ src/

# Repo instruction files optional but improve context-engine text if present in image.
COPY AGENTS.md SWARM.md VISION.md ./

# Operator skills + subagent rule stubs for chat system prompt + control-plane GET routes.
COPY .cursor/skills .cursor/skills
COPY .cursor/rules .cursor/rules

# Claude Code probes git workspace roots; ship a repo with HEAD so rev-parse succeeds.
RUN git config --global init.defaultBranch main \
    && git init . \
    && git config user.email "ham-api-container@invalid.local" \
    && git config user.name "HAM API" \
    && git commit --allow-empty --quiet -m "ham-api:synthetic"

EXPOSE 8080

CMD exec uvicorn src.api.server:app --host 0.0.0.0 --port "${PORT:-8080}"
