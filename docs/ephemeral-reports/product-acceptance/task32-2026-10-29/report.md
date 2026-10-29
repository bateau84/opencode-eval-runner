---
type: Report
title: PR #89 Task 3.2 deterministic-provider acceptance evidence
description: Records public eval execution and same-run output checks for one agent-runtime case and a two-skill five-iteration run.
tags: [evaluation, product-acceptance, pr-89, task-3.2, deterministic-provider]
---

# PR #89 Task 3.2: deterministic-provider acceptance

**Date:** 2026-10-29<br>
**Branch / source HEAD:** `feat/evaluation-format-contracts` / `636f637613a19120f8f533eff50127326bb95dff`<br>
**Disposition:** Public-path integration and output-projection claims **PASS** within the limits below. This is not live-provider compatibility or semantic-model-quality evidence.

## Scenarios and observed results

| Scenario | Public path | Run | Result |
| --- | --- | --- | --- |
| Agent/runtime suite (conversation-response only) | `eval --input ... --family agent-runtime` → real built-in adapter, invocation adapter, OpenCode image, verifier, persistence | `eded2c961df84df3be3fdd9d1b33dedb` | 1/1 job pass; completed persisted run, but **not** the runtime-execution scenario E2E-001 requires |
| Combined skills | Two explicit `--input`/`--skill` pairs → skill paired baseline/candidate execution and comparisons, verifier, persistence | `f47f708d31cf42b489900c870838ea43` | 10/10 paired jobs pass: two distinct skills × one selected case × five iterations |

Both runs used the same selected immutable local OpenCode image, `sha256:0940e9ac543098bfa51dda81cce643ed3366df1ab8a4e90bf5fcd8601c2e5e39` (OpenCode `2.0.23`, adapter label `opencode-eval-runner/opencode-invoke/v1`). The runner-created target/judge OCI containers, evaluation adapters, evidence collection, verifier, persistence, and renderers were product-owned real implementations. No product stage was mocked.

The skill run used the actual configured input files `skills/python-testing/evals/evals.json` and `skills/python-error-handling/evals/evals.json`; the selected case in each was authored case `1`. Each side's runtime evidence recorded successful native `skill` tool calls with the expected skill ID and actor, and the pair comparison was persisted. Inputs are separately archived and hashed in `fixtures/` and `evidence.json`.

## Output parity from the same verified runs

Each representation was independently requested with the public `eval --render-run <same-run>` command after evaluation. The render path loaded and verified the persisted run; no model or container was invoked for rendering.

| Family | Run | JSON | YAML | Markdown | HTML |
| --- | --- | --- | --- | --- | --- |
| Agent/runtime | `eded2c961df84df3be3fdd9d1b33dedb` | `renders/agent.json` | `renders/agent.yaml` | `renders/agent.markdown` | `renders/agent.html` |
| Skill | `f47f708d31cf42b489900c870838ea43` | `renders/skill.json` | `renders/skill.yaml` | `renders/skill.markdown` | `renders/skill.html` |

For each family, parsed JSON and YAML values were identical. The skill Markdown and HTML expose both skill groups and all five individual iterations for each. SHA-256 digests, sizes, run manifests, persisted job artifacts, command logs, source hashes, image/network metadata, and provider request metadata are recorded in `evidence.json` and the adjacent evidence directories. The Markdown/HTML files are the actual generated outputs and are available for Task 3.3 design/browser validation; this report does not claim a browser check.

**Renderer refresh (2026-10-29):** The skill Markdown and HTML were regenerated via `eval --render-run` from the unchanged persisted combined-skill run after PR #89 Task 3.3 corrections. No eval/provider execution occurred; JSON/YAML, run manifests, and job artifacts were not modified. Updated output sizes and SHA-256 digests are in `evidence.json`; the original execution source provenance remains unchanged. Reassessment is pending.

- `renders/skill.markdown`: 1,683,692 bytes; SHA-256 `755eba381518dca5de4819bc22e6692ed682a08007088b8b7d3e6fe1a691fc5d`
- `renders/skill.html`: 1,790,681 bytes; SHA-256 `317cbf532d3dbaf067f2a40fa4c2d0c6ffeb305851859ee22dbdedae00701abb`

## Deterministic external substitution and limits

The only external substitution was a local OpenAI-compatible deterministic provider container on a Podman network inspected as `internal=true`. It used no external provider endpoint, no paid inference, and no ambient provider credentials. Its image ID was `sha256:febd0be41adb897a0ab8f1f1c693d8912669ea60c4940e076e9946b60e210ef0`; its own implementation is archived as `fixtures/deterministic-provider.py`. Configuration authority was the mounted `OPENCODE_EVAL_RUNNER_CONFIG` seed, not inferred from `OPENCODE_CLI_CONFIG_CONTENT`. The isolated XDG data directory had no OpenCode database seed (`database_seed=None`); `CONTAINERS_STORAGE_CONF` retained the original local Podman image store while that data directory was isolated.

The fixture emits deterministic target responses and strict judge JSON containing every supplied positive expectation and forbidden-rule entry. Its grade is fixture-controlled, not an independent semantic model assessment; therefore these PASS results prove the assembled runner path, native skill evidence, persistence/integrity, family projections, and same-run format parity—not that a live model follows the skills, that the judge can correctly distinguish nuanced behavior, or that another provider's responses work. The agent/runtime case is a minimal `conversation-response` case, not a runtime-tool execution proof. The skill run selects one case per skill, not every case in the source suites. The fixture is intentionally no-egress and does not preserve live-provider latency, quota, authentication, or model behavior.

**Coverage correction:** run `eded2c961df84df3be3fdd9d1b33dedb` proves only that an agent/runtime-family `conversation-response` input reaches the public path. It does not prove E2E-001: it has no native runtime execution or nonempty authoritative runtime evidence. That gap was closed separately by the [runtime follow-up report](../task32-runtime-followup-2026-10-29/report.md), which reuses this report's still-valid combined-skill run without rerunning it.

This internal-network evidence says nothing about the previously documented GHCR pull attempts. Their layer-transfer status remains unresolved; no whole-workflow no-egress claim is made.

## Reproduction

Commands were run from the isolated fixture project directory under `/tmp/opencode/task32-recovery/project` with ambient provider credentials and prior `OPENCODE_EVAL_RUNNER_*` variables scrubbed. Environment included `OPENCODE_EVAL_RUNNER_CONFIG=/tmp/opencode/task32-recovery/opencode.json`, `OPENCODE_EVAL_RUNNER_OPENCODE_IMAGE=<the immutable ID above>`, `XDG_DATA_HOME=/tmp/opencode/task32-recovery/isolated-data`, and `CONTAINERS_STORAGE_CONF=/tmp/opencode/task32-recovery/storage.conf`. The omitted command values are preserved in the command logs and the fixture config; the latter's dummy `apiKey` is redacted in the archived copy.

```sh
python3 <repo>/bin/opencode-eval-runner eval \
  --input <agent-runtime-input.json> --family agent-runtime \
  --cases fixture-case --target-model fixture/mock --engine podman \
  --network task32-recovery-1793300807 --timeout-seconds 90 \
  --container-timeout 150 --artifact-dir <agent-run-dir> --format json

python3 <repo>/bin/opencode-eval-runner eval \
  --input skills/python-testing/evals/evals.json --skill python-testing \
  --input skills/python-error-handling/evals/evals.json --skill python-error-handling \
  --family skill --ablation --cases <case-1-selector-for-each-skill> \
  --iterations 5 --runtime-parallel 2 --target-model fixture/mock \
  --engine podman --network task32-recovery-1793300807 \
  --timeout-seconds 90 --container-timeout 150 --artifact-dir <skill-run-dir>

python3 <repo>/bin/opencode-eval-runner eval --render-run <run-dir> \
  --format json|yaml|markdown|html --output <distinct-output-path>
```

## Cleanup and evidence boundaries

Only this task's provider container and temporary internal Podman network were created. They were removed after capturing inspect/log evidence; the pre-existing `combined-skill-e2e-e2e-1792179251` network and all images were left untouched. Container removal and network absence were verified. The host-only exploratory provider process was stopped. Report outputs and persisted run evidence are intentionally retained here for review.

No build/source behavior was changed for this acceptance task; the only repository changes are this evidence record, its actual outputs/run artifacts/fixtures, the prior report's supersession note, and the report index/log updates.
