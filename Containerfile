FROM node:24-bookworm-slim@sha256:0e0ff40c39bc087845bfb27465a0df4ea419520094bc35842ff83dd8cbe6f9b6 AS opencode-builder
ARG OPENCODE_VERSION=2.0.15
RUN npm install --global "@opencode/cli@${OPENCODE_VERSION}" \
    && resolved="$(readlink -f "$(command -v opencode)")" \
    && test -x "$resolved" \
    && cp "$resolved" /opencode \
    && /opencode --version

FROM debian:bookworm-slim@sha256:3783cc01769c7b2b1b83a5c5ad96c815348e28ed7da68e2e3687004faa906251 AS copilot-builder
ARG COPILOT_VERSION=1.0.83
ARG TARGETARCH
RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates curl \
    && rm -rf /var/lib/apt/lists/* \
    && case "$TARGETARCH" in \
         amd64) asset="copilot-linux-x64.tar.gz"; expected="ffbe1c429664b8a05efed67ecdb467123e40fcaa3c6c14ef9a98ba74da4687b7" ;; \
         arm64) asset="copilot-linux-arm64.tar.gz"; expected="213b3a267042dbac3cd8ae22c82f5ea04ff3cabc008108c0f895055d46be4473" ;; \
         *) echo "unsupported TARGETARCH: $TARGETARCH" >&2; exit 1 ;; \
       esac \
    && url="https://github.com/github/copilot-cli/releases/download/v${COPILOT_VERSION}/$asset" \
    && curl -fsSL "$url" -o /tmp/copilot.tar.gz \
    && echo "$expected  /tmp/copilot.tar.gz" | sha256sum -c - \
    && mkdir -p /opt/copilot/bin \
    && tar -xzf /tmp/copilot.tar.gz -C /opt/copilot/bin \
    && rm -f /tmp/copilot.tar.gz \
    && chmod +x /opt/copilot/bin/copilot \
    && /opt/copilot/bin/copilot --version

FROM python:3.12-slim-bookworm@sha256:392307d22300de8b5986851a12d9176dfc0fc073e65bf6523ebd7dcbeb23564e AS runtime-base
RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates git \
    && rm -rf /var/lib/apt/lists/* \
    && groupadd --gid 1000 evalrunner \
    && useradd --uid 1000 --gid 1000 --no-create-home --home-dir /tmp/runtime/home --shell /usr/sbin/nologin evalrunner \
    && mkdir -p /seed /input /output /workspace

# The runtime root filesystem is intentionally read-only. Point all normal
# user/XDG state at /tmp, which the runner mounts as a writable tmpfs.
ENV HOME=/tmp/runtime/home \
    XDG_CONFIG_HOME=/tmp/runtime/config \
    XDG_DATA_HOME=/tmp/runtime/data \
    XDG_CACHE_HOME=/tmp/runtime/cache \
    XDG_STATE_HOME=/tmp/runtime/state \
    OPENCODE_DB=opencode.db \
    OPENCODE_DISABLE_AUTOUPDATE=1

COPY container /opt/opencode-eval-runner/container
WORKDIR /workspace
ENTRYPOINT ["python3", "/opt/opencode-eval-runner/container/invoke.py"]

# Runtime inference never needs root. UID/GID 1000 are paired with Podman's
# keep-id mapping by the host runner so private host seed files remain readable.
USER 1000:1000

FROM runtime-base AS opencode
COPY --from=opencode-builder /opencode /usr/local/bin/opencode
RUN opencode --version

FROM runtime-base AS copilot
COPY --from=copilot-builder /opt/copilot/bin/copilot /usr/local/bin/copilot
RUN copilot --version
