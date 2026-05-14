# Spike-only preview runner image (Linux).

FROM node:22-bookworm-slim

RUN apt-get update \
    && apt-get install -y --no-install-recommends python3 python3-pip unzip ca-certificates \
    && rm -rf /var/lib/apt/lists/* \
    && pip3 install --no-cache-dir --break-system-packages google-cloud-storage \
    && mkdir -p /workspace /tmp/npm-cache \
    && chown -R node:node /workspace /tmp/npm-cache

WORKDIR /workspace

ENV NPM_CONFIG_CACHE=/tmp/npm-cache

COPY docker/preview-runner/download_preview_source.py /usr/local/bin/ham-preview-download-source.py
COPY docker/preview-runner/entrypoint.sh /usr/local/bin/ham-preview-entrypoint.sh
RUN sed -i 's/\r$//' /usr/local/bin/ham-preview-entrypoint.sh \
    && chmod 0555 /usr/local/bin/ham-preview-entrypoint.sh /usr/local/bin/ham-preview-download-source.py

USER node

ENTRYPOINT ["/usr/local/bin/ham-preview-entrypoint.sh"]
