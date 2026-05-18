# HAM Builder GKE preview janitor — CronJob image (dry-run by default).
# Reads cluster state via kubectl, runs scripts/ham_preview_janitor.py without --apply.
# Build from repo root, e.g.:
#   DO NOT RUN until reviewed: docker build -f docker/ham-preview-janitor/Dockerfile -t ham-preview-janitor:local .

FROM python:3.12-slim-bookworm

RUN apt-get update \
    && apt-get install -y --no-install-recommends kubectl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
ENV PYTHONPATH=/app

COPY scripts/ham_preview_janitor.py /app/scripts/ham_preview_janitor.py
COPY src/ham/preview_janitor.py /app/src/ham/preview_janitor.py
COPY src/ham/gcp_preview_runtime_client.py /app/src/ham/gcp_preview_runtime_client.py

USER 65532:65532
