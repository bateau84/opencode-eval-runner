# opencode-eval-runner

Reusable OCI isolation for behavioral evals that invoke OpenCode or GitHub Copilot CLI.

The runner intentionally does **not** own an eval corpus, grading semantics, or agent policy. Those stay in the repository being evaluated. This project owns the execution boundary:

- one fresh container per model invocation;
- separate target and judge containers;
- fresh HOME/XDG/OpenCode state per invocation;
- explicit provider configuration and authentication;
- read-only workspace by default;
- host-owned result/artifact files;
- the same invocation model locally and in GitHub Actions.

## Why

Behavioral eval evidence becomes weak when the target or judge can inherit host sessions, plugins, global agents, caches, or mutable provider configuration.

The unit of isolation here is one invocation:

```text
eval harness
  |
  +-- target -> fresh OCI container -> result.json
  |
  +-- judge  -> different fresh OCI container -> judgment.json
```

The caller may use the same model for both, but they do not share OpenCode session state or filesystem state.

## Transports

### `opencode`

Use this for real OpenCode runtime behavior, including project-local agents, skills, plugins, and tool assertions.

Authentication is seeded from the normal OpenCode credential file:

```text
~/.local/share/opencode/auth.json
```

An optional model-catalog seed may be supplied explicitly for custom/private-provider cases. Normal public-provider runs do not inherit the host model cache.

The auth seed and any explicit model-catalog seed are mounted read-only and copied into fresh container-local XDG directories. Sessions, history, the rest of the cache, and the global config tree are not inherited.

An OpenCode config is **not** inherited automatically. The container constructs a minimal config unless you explicitly pass one with `--config` or `OPENCODE_EVAL_RUNNER_CONFIG`.

This avoids importing host MCPs, plugins, agent defaults, or provider overrides into behavioral evidence. Only explicit seed files are mounted; the host OpenCode config directory, data directory, cache, and sessions are never mounted.

OpenCode V2 does not document a manual model-catalog refresh command. The runner therefore does not run the legacy `opencode models --refresh` path. Each invocation starts a fresh OpenCode process with a fresh writable cache and lets V2 resolve the requested model through its normal catalog/provider startup path. If an explicit models catalog is supplied, it is available as a seed for custom/private-provider cases.

Known API-key environment variables are passed when present:

- `OPENAI_API_KEY`
- `ANTHROPIC_API_KEY`
- `OPENROUTER_API_KEY`

Additional variables require explicit `--env NAME`.

### `github-copilot-cli`

Use this for pure model/role/judge execution when OpenCode runtime tools are not required.

Authentication precedence matches GitHub Copilot CLI:

1. `COPILOT_GITHUB_TOKEN`
2. `GH_TOKEN`
3. `GITHUB_TOKEN`

The container uses fresh `COPILOT_HOME` and `COPILOT_CACHE_HOME`, disables auto-update, prompt-mode extensions, repo hooks, MCPs, remote operations, and model tools.

This transport reuses the trust-boundary pattern already proven in `nrkno/mats-opencode-setup`.

## Local usage

Build the transport you need:

```bash
podman build -f Containerfile --target opencode -t opencode-eval-runner:opencode-local .
podman build -f Containerfile --target copilot -t opencode-eval-runner:copilot-local .
```

The published runtime images are split by transport and do not contain Node/npm. The build stages may use Node or curl to obtain the pinned native executables, but only the native binary and the minimal Python runtime land in the final image.

Prepare a prompt:

```bash
printf '%s\n' 'Respond with the production decision for this scenario.' > /tmp/prompt.txt
```

Run a real OpenCode invocation:

```bash
PYTHONPATH=. python3 bin/opencode-eval-runner invoke \
  --engine podman \
  --image opencode-eval-runner:opencode-local \
  --transport opencode \
  --workspace /path/to/evaluated/project \
  --model openai/gpt-5.3-codex-spark \
  --agent reviewer \
  --prompt-file /tmp/prompt.txt \
  --output /tmp/target.json
```

The wrapper automatically mounts the normal OpenCode `auth.json` when it exists. OpenCode config and model-catalog seeds are explicit-only:

```text
--auth /path/to/auth.json
--models-catalog /path/to/models.json
--config /path/to/opencode.json
```

or:

```text
OPENCODE_EVAL_RUNNER_AUTH=/path/to/auth.json
OPENCODE_EVAL_RUNNER_MODELS=/path/to/models.json
OPENCODE_EVAL_RUNNER_CONFIG=/path/to/opencode.json
```

### Copilot CLI locally

```bash
export COPILOT_GITHUB_TOKEN=...
PYTHONPATH=. python3 bin/opencode-eval-runner invoke \
  --engine podman \
  --image opencode-eval-runner:copilot-local \
  --transport github-copilot-cli \
  --workspace /path/to/evaluated/project \
  --model gpt-5.4 \
  --prompt-file /tmp/prompt.txt \
  --system-file /tmp/system.txt \
  --output /tmp/judge.json
```

The token value is not placed on the container command line.

## GitHub Actions

The composite action sets up the runner CLI/image and can execute a repository-owned eval command.

```yaml
permissions:
  contents: read
  copilot-requests: write

steps:
  - uses: actions/checkout@v4

  - uses: bateau84/opencode-eval-runner@main
    with:
      engine: docker
      command: |
        python3 scripts/run-evals.py \
          --cases INTENT-01,WORK-01,REVIEW-01,CRITIC-01
```

When a consumer invokes the `github-copilot-cli` transport, the action exposes the workflow's built-in `GITHUB_TOKEN` to that command. The caller must grant `copilot-requests: write`. No additional Copilot secret is required when GitHub permits that token path.

For OpenCode credentials in CI, materialize a protected secret as a file before the eval and point `OPENCODE_EVAL_RUNNER_AUTH` at it. Do not commit auth files.

Example:

```yaml
- name: Materialize OpenCode auth
  shell: bash
  env:
    OPENCODE_AUTH_JSON: ${{ secrets.OPENCODE_AUTH_JSON }}
  run: |
    install -m 700 -d "$RUNNER_TEMP/opencode-auth"
    printf '%s' "$OPENCODE_AUTH_JSON" > "$RUNNER_TEMP/opencode-auth/auth.json"
    chmod 600 "$RUNNER_TEMP/opencode-auth/auth.json"
    echo "OPENCODE_EVAL_RUNNER_AUTH=$RUNNER_TEMP/opencode-auth/auth.json" >> "$GITHUB_ENV"
```

## Result contract

Each invocation writes one JSON document:

```json
{
  "schema": "opencode-eval-runner/v1",
  "transport": "opencode",
  "model": "openai/gpt-5.3-codex-spark",
  "agent": "reviewer",
  "exit_code": 0,
  "session_id": "...",
  "text": "...",
  "tools": [],
  "stderr": "",
  "stdout": "..."
}
```

The eval repository decides whether that observed behavior is PASS, FAIL, or non-evidence.

## Image versions

The transport images currently pin:

- OpenCode CLI `2.0.11`
- GitHub Copilot CLI `1.0.83`

The two CLIs are not bundled together. OpenCode's npm package is used only as a build-time native-binary selector; GitHub Copilot CLI is installed from its native release installer. Node/npm are absent from the final runtime images.

Pinning is deliberate: behavioral evidence should not silently change because a CLI auto-updated.

`main` publishes transport-specific images:

```text
ghcr.io/bateau84/opencode-eval-runner:opencode-edge
ghcr.io/bateau84/opencode-eval-runner:copilot-edge
ghcr.io/bateau84/opencode-eval-runner:opencode-sha-...
ghcr.io/bateau84/opencode-eval-runner:copilot-sha-...
```

The host runner selects the correct image from `--transport`. Override either image with:

```text
OPENCODE_EVAL_RUNNER_OPENCODE_IMAGE=...
OPENCODE_EVAL_RUNNER_COPILOT_IMAGE=...
```

Tags matching `v*` are published with `opencode-` and `copilot-` prefixes.

## Security boundary

The runner:

- drops Linux capabilities;
- enables `no-new-privileges`;
- uses a read-only container root filesystem with ephemeral `/tmp`;
- mounts the evaluated workspace read-only unless `--workspace-mode rw` is explicitly selected;
- mounts config/auth/model-catalog seed files read-only;
- on rootless Podman, disables SELinux container labeling instead of relabeling the user's repository/auth files;
- creates fresh OpenCode/Copilot state per invocation;
- passes only explicit credential environment variables;
- never treats infrastructure/provider failure as behavioral evidence.

This is an eval isolation boundary, not a sandbox for hostile arbitrary code. A deliberately malicious evaluated plugin running inside an invocation still has the network and credentials granted to that invocation.
