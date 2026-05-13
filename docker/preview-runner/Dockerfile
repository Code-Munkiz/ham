# Spike-only preview runner image (Linux).

FROM node:22-bookworm-slim

RUN groupadd --gid 1000 hamnode \
    && useradd --uid 1000 --gid hamnode --shell /bin/bash --create-home hamnode \
    && mkdir -p /workspace /tmp/npm-cache \
    && chown -R hamnode:hamnode /workspace /tmp/npm-cache

WORKDIR /workspace

ENV NPM_CONFIG_CACHE=/tmp/npm-cache

COPY docker/preview-runner/entrypoint.sh /usr/local/bin/ham-preview-entrypoint.sh
RUN chmod 0555 /usr/local/bin/ham-preview-entrypoint.sh

USER hamnode

ENTRYPOINT ["/usr/local/bin/ham-preview-entrypoint.sh"]
