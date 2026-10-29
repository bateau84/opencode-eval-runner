---
type: Report
title: PR #89 Task 3.2 feasibility and evidence record
description: Records the provider-free feasibility check and unproven product-acceptance scenarios at branch HEAD 23a8a4f.
tags: [evaluation, product-acceptance, pr-89, task-3.2]
---

# PR #89 Task 3.2: feasibility and evidence

**Observation date:** 2026-10-29<br>
**Branch / source HEAD:** `feat/evaluation-format-contracts` / `23a8a4fedb79f7b0633af911a5b9006dde64b4bd`<br>
**Disposition:** Both E2E scenarios **UNPROVEN**. No evaluation invocation was made.

## Feasibility boundary

The public CLI and local OCI engine are available. Podman has a local OpenCode invoke image, `localhost/eval-contract-opencode:guarded`, with immutable image ID `sha256:0940e9ac543098bfa51dda81cce643ed3366df1ab8a4e90bf5fcd8601c2e5e39`. Its OCI labels report OpenCode `2.0.23` and adapter `opencode-eval-runner/opencode-invoke/v1`, matching the source contract.

The OpenCode configuration injected into the process has no provider names, model names, or custom base URLs. No approved provider-free fixture/provider route was found among the available configuration. A real evaluation would need to make provider requests; a configured user credential is not authorization to incur live/paid-provider use. Therefore execution stopped before any `eval` run. No fallback, mock, injected runtime evidence, or test fixture was used as product proof.

## Scenario dispositions

### E2E-001 — agent/runtime through verified result

**UNPROVEN.** No suite was submitted to a real model invocation. No OCI phase was run, runtime evidence was not produced, and no verified persisted result or output format was generated. Thus the assertion-scoped evidence readiness and prescribed judge gate were not exercised in the assembled product.

### E2E-002 — combined skills, five iterations, four formats

**UNPROVEN.** No combined run was submitted. There is no run ID, provenance-bearing persisted result, five-iteration multi-skill report, or same-run JSON/YAML/Markdown/HTML projection from this attempt. Consequently no actual Markdown or HTML artifact is available for Task 3.3 browser/design validation.

## Evidence inventory and limits

| Item | Observation | Evidentiary meaning |
| --- | --- | --- |
| Source | `23a8a4fedb79f7b0633af911a5b9006dde64b4bd` | Exact source revision assessed for feasibility. |
| CLI | `./bin/opencode-eval-runner eval --help` | Public entry point is available; help output is not execution evidence. |
| OCI | `podman image inspect 0940e9ac5430 --format '{{.Id}} {{json .Config.Labels}}'` | Compatible local image exists; image presence does not prove any invocation. |
| Provider configuration | Read-only inspection of `OPENCODE_CLI_CONFIG_CONTENT` keys | No provider/model/base URL available; secrets were not printed. |
| Run identity/artifacts | None | No run ID or result artifacts were created. |
| Report paths for designer | None | No generated HTML/Markdown exists; browser assessment cannot proceed. |

The user's accepted historical GHCR image transfer remains a known non-blocking exception. This report makes no no-egress claim and does not reopen that boundary. It also makes no live-provider compatibility claim, no WCAG conformance claim, and no claim that tests substitute for the missing composed journey.

## Required next step

Provide or authorize an existing provider-free local fixture/provider route that preserves the semantics needed by real runner-side OpenCode/OCI invocation, or explicitly authorize the intended live provider and spend. Then execute both scenarios through the public CLI, verifier, persistence, and renderers; save run IDs and same-run output artifacts; and hand the actual HTML/Markdown paths to the designer for Task 3.3. Until then both scenarios remain UNPROVEN.
