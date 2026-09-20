FROM node:24-bookworm-slim AS opencode-builder
ARG OPENCODE_VERSION=2.0.11
RUN npm install --global "@opencode/cli@${OPENCODE_VERSION}" \
    && resolved="$(readlink -f "$(command -v opencode)")" \
    && test -x "$resolved" \
    && cp "$resolved" /opencode \
    && /opencode --version

FROM debian:bookworm-slim AS copilot-builder
ARG COPILOT_VERSION=1.0.83
RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates curl \
    && rm -rf /var/lib/apt/lists/* \
    && mkdir -p /opt/copilot \
    && curl -fsSL https://gh.io/copilot-install \
       | VERSION="v${COPILOT_VERSION}" PREFIX=/opt/copilot bash \
    && /opt/copilot/bin/copilot --version

FROM python:3.12-slim-bookworm AS runtime-base
RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates git \
    && rm -rf /var/lib/apt/lists/* \
    && mkdir -p /seed /input /output /workspace

COPY container /opt/opencode-eval-runner/container
WORKDIR /workspace
ENTRYPOINT ["python3", "/opt/opencode-eval-runner/container/invoke.py"]

FROM runtime-base AS opencode
COPY --from=opencode-builder /opencode /usr/local/bin/opencode
RUN opencode --version

FROM runtime-base AS copilot
COPY --from=copilot-builder /opt/copilot/bin/copilot /usr/local/bin/copilot
RUN copilot --version
