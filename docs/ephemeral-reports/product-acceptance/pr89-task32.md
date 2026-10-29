---
type: Report
title: PR #89 Task 3.2 feasibility and evidence record
description: Records the provider-free feasibility check and unproven product-acceptance scenarios at branch HEAD 23a8a4f.
tags: [evaluation, product-acceptance, pr-89, task-3.2]
---

# PR #89 Task 3.2: feasibility and evidence

**Observation date:** 2026-10-29<br>
**Branch / source HEAD:** `feat/evaluation-format-contracts` / `23a8a4fedb79f7b0633af911a5b9006dde64b4bd`<br>
**Disposition at initial attempt:** Both E2E scenarios were **UNPROVEN**; no evaluation invocation was made. This initial feasibility finding is superseded by the provider-fixture recovery recorded in [the follow-up acceptance report](task32-2026-10-29/report.md).

## Feasibility boundary

The public CLI and local OCI engine are available. Podman has a local OpenCode invoke image, `localhost/eval-contract-opencode:guarded`, with immutable image ID `sha256:0940e9ac543098bfa51dda81cce643ed3366df1ab8a4e90bf5fcd8601c2e5e39`. Its OCI labels report OpenCode `2.0.23` and adapter `opencode-eval-runner/opencode-invoke/v1`, matching the source contract.

The OpenCode configuration inspected during this attempt had no provider names, model names, or custom base URLs. The prior conclusion that execution required live/paid-provider use was incomplete: a deterministic local provider fixture was subsequently reconstructed and exercised through the public CLI. No configured user credential was used.

## Scenario dispositions

### E2E-001 — agent/runtime through verified result

**UNPROVEN at initial attempt.** No suite was submitted during this first feasibility check. See follow-up report for the later public-path result and its deterministic-provider limitations.

### E2E-002 — combined skills, five iterations, four formats

**UNPROVEN at initial attempt.** No combined run was submitted during this first feasibility check. See follow-up report for later run IDs, source provenance, output artifacts, and validation limits.

## Evidence inventory and limits

| Item | Observation | Evidentiary meaning |
| --- | --- | --- |
| Source | `23a8a4fedb79f7b0633af911a5b9006dde64b4bd` | Exact source revision assessed for feasibility. |
| CLI | `./bin/opencode-eval-runner eval --help` | Public entry point is available; help output is not execution evidence. |
| OCI | `podman image inspect 0940e9ac5430 --format '{{.Id}} {{json .Config.Labels}}'` | Compatible local image exists; image presence does not prove any invocation. |
| Provider configuration | Read-only inspection of `OPENCODE_CLI_CONFIG_CONTENT` keys | No provider/model/base URL available; secrets were not printed. |
| Run identity/artifacts | None for this attempt | The follow-up report records distinct later run IDs and artifacts. |
| Report paths for designer | None for this attempt | The follow-up report provides actual HTML/Markdown files; browser assessment remains separate. |

The user's accepted historical GHCR image transfer remains a known non-blocking exception. This report makes no no-egress claim and does not reopen that boundary. It also makes no live-provider compatibility claim, no WCAG conformance claim, and no claim that tests substitute for the missing composed journey.

## Required next step

Provide or authorize an existing provider-free local fixture/provider route that preserves the semantics needed by real runner-side OpenCode/OCI invocation, or explicitly authorize the intended live provider and spend. Then execute both scenarios through the public CLI, verifier, persistence, and renderers; save run IDs and same-run output artifacts; and hand the actual HTML/Markdown paths to the designer for Task 3.3. Until then both scenarios remain UNPROVEN.
