# Ham FastAPI for Cloud Run (and local smoke tests).
# Cloud Run sets PORT; default 8080 for local `docker run`.
FROM python:3.12-slim-bookworm

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app

COPY requirements.txt .
# Browser runtime: pip installs `playwright` but browsers are a separate download.
# --with-deps pulls Debian packages Chromium needs in slim images.
RUN pip install --no-cache-dir -r requirements.txt \
    && python -m playwright install --with-deps chromium

# TTS and other top-level `models.*` imports (src.api.tts_endpoint, src.api.audio_upload)
COPY models/ models/

COPY src/ src/

# Repo instruction files optional but improve context-engine text if present in image.
COPY AGENTS.md SWARM.md VISION.md ./

# Operator skills + subagent rule stubs for chat system prompt + control-plane GET routes.
COPY .cursor/skills .cursor/skills
COPY .cursor/rules .cursor/rules

EXPOSE 8080

CMD exec uvicorn src.api.server:app --host 0.0.0.0 --port "${PORT:-8080}"
