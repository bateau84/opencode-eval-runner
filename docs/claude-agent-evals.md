# Claude Agent evaluation profile (opt-in; qualification pending)

The historical runner image remains OpenCode 2.2.2. This adds a **separate**
`claude-agent` image with OpenCode 2.2.6 and official Claude Code 2.1.318.
The model still runs through stock OpenCode tooling and the runner's existing
skill-loading observer, not a proxy that reuses a Claude OAuth bearer token.

## Build and identify the image

```sh
podman build -f Containerfile --target claude-agent -t skills-claude-agent:local .
podman image inspect skills-claude-agent:local --format '{{.Id}}'
```

Use the **full resulting image ID** for `--image`, not the mutable tag.
The runner verifies local image identity, OpenCode 2.2.6, Claude Code 2.1.318
and the runner's existing invoke-adapter label before any model request.

## Dedicated login (manual, no automated account mutations)

Use a **new, dedicated** Claude Code configuration directory. Do not mount
`~/.claude`, your normal HOME, or a personal account's broader config tree.
Sign in with the official Claude Code binary on the host:

```sh
mkdir -p "$HOME/.claude-eval-profile"
chmod 700 "$HOME/.claude-eval-profile"
CLAUDE_CONFIG_DIR="$HOME/.claude-eval-profile" claude auth login
CLAUDE_CONFIG_DIR="$HOME/.claude-eval-profile" claude auth status --json
```

Require an actual subscription login (the native status command must report
`loggedIn: true`, `authMethod: claude.ai` and a nonempty `subscriptionType`).
The runner never parses or forwards OAuth token values; it mounts the **explicit
directory** for the official executable to use and refresh its own credentials.
**Because this mount is read/write and the evaluated tools share its container
namespace, credential confidentiality against a compromised evaluated agent
is not proven.** Use only a disposable dedicated profile, deny arbitrary
shell/reads in evaluated agents, and do not run untrusted tool-capable tasks
until an independent isolation review establishes that boundary. No host
credential is mounted by default.

Disable paid extra usage in Claude account settings. Native login indicates the
chosen account type but is *not* an authoritative provider-enforced assertion
that additional charges are impossible. No automatic quota fallback is enabled.

## One explicitly authorized invocation

```sh
printf 'Explain what a skill improves.\n' >/tmp/claude-skill-prompt.txt
python3 bin/opencode-eval-runner invoke \
  --transport opencode --engine podman \
  --image '<FULL_LOCAL_IMAGE_ID>' \
  --model 'claude-agent/<EXACT_CLAUDE_MODEL_ID>' \
  --claude-config-dir "$HOME/.claude-eval-profile" \
  --workspace /path/to/disposable-project --workspace-mode ro \
  --prompt-file /tmp/claude-skill-prompt.txt \
  --output /tmp/claude-invocation.json
```

This makes a **real** model request and draws from the signed-in account's
allowance. Only run once credential and billing policy have been checked.
The runner rejects implicit Claude credentials, provider-env overrides,
custom Claude provider settings, a mismatched model/profile, unqualified
images, and missing native subscription status *before inference*.

## What remains unqualified

No networked Claude provider request or subscription/billing assertion has been
executed in CI. Provider registration, exact model discovery, automatic token
refresh under parallel invocation, credential exposure through tools, independent
skill-loading evidence, model/judge parity, and provider rate limits require
explicit installed-host tests on the exact image. A green unit test is not a
proof of these boundaries. Existing OpenCode/Copilot modes must keep passing.
