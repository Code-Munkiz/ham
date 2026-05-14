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
    && apt-get install -y --no-install-recommends ca-certificates curl gnupg git tini \
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

# Pinned OpenCode runtime (Mission 2.x): download verified tarball from
# github.com/anomalyco/opencode, install the Bun-compiled binary at
# /usr/local/bin/opencode, and gate the build on `opencode --version`.
ARG OPENCODE_VERSION=1.14.49
ARG OPENCODE_LINUX_X64_SHA256=0b373d64650073df36616af189c18cecaa3d5cd19ae2121300cafed1efa54b11
RUN set -eux; \
    cd /tmp; \
    curl -fsSL -o opencode.tar.gz \
        "https://github.com/anomalyco/opencode/releases/download/v${OPENCODE_VERSION}/opencode-linux-x64.tar.gz"; \
    echo "${OPENCODE_LINUX_X64_SHA256}  opencode.tar.gz" | sha256sum -c -; \
    tar -xzf opencode.tar.gz; \
    install -m 0755 opencode /usr/local/bin/opencode; \
    rm -rf /tmp/opencode /tmp/opencode.tar.gz; \
    /usr/local/bin/opencode --version | grep -Eq "(^|[[:space:]v])${OPENCODE_VERSION}([[:space:]]|$)"; \
    command -v opencode
ENV OPENCODE_DISABLE_AUTOUPDATE=1 \
    OPENCODE_DISABLE_MODELS_FETCH=1 \
    OPENCODE_DISABLE_CLAUDE_CODE=1

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

ENTRYPOINT ["/usr/bin/tini", "--"]
CMD exec uvicorn src.api.server:app --host 0.0.0.0 --port "${PORT:-8080}"
