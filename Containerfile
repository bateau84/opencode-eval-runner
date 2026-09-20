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

# The runtime root filesystem is intentionally read-only. Point all normal
# user/XDG state at /tmp, which the runner mounts as a writable tmpfs.
# container/invoke.py creates these directories and seeds auth/models there
# for normal eval execution; the image-level defaults also make direct
# OpenCode/Copilot commands safe in an interactive debug shell.
ENV HOME=/tmp/runtime/home \
    XDG_CONFIG_HOME=/tmp/runtime/config \
    XDG_DATA_HOME=/tmp/runtime/data \
    XDG_CACHE_HOME=/tmp/runtime/cache \
    OPENCODE_DISABLE_AUTOUPDATE=1

COPY container /opt/opencode-eval-runner/container
WORKDIR /workspace
ENTRYPOINT ["python3", "/opt/opencode-eval-runner/container/invoke.py"]

FROM runtime-base AS opencode
COPY --from=opencode-builder /opencode /usr/local/bin/opencode
RUN opencode --version

FROM runtime-base AS copilot
COPY --from=copilot-builder /opt/copilot/bin/copilot /usr/local/bin/copilot
RUN copilot --version
