FROM node:24-bookworm-slim

ARG OPENCODE_VERSION=2.0.11
ARG COPILOT_VERSION=1.0.83

RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates git python3 \
    && rm -rf /var/lib/apt/lists/* \
    && npm install --global "@opencode/cli@${OPENCODE_VERSION}" "@github/copilot@${COPILOT_VERSION}" \
    && opencode --version \
    && copilot --version

COPY container /opt/opencode-eval-runner/container

WORKDIR /workspace
ENTRYPOINT ["python3", "/opt/opencode-eval-runner/container/invoke.py"]
