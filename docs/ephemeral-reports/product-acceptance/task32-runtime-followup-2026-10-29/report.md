---
type: Report
title: PR #89 Task 3.2 runtime-evidence follow-up
description: Completes E2E-001 with a real native runtime read, assertion-scoped evidence, judge execution, and four projections from one verified run.
tags: [evaluation, product-acceptance, pr-89, task-3.2, runtime-evidence]
---

# PR #89 Task 3.2: agent/runtime evidence follow-up

**Date:** 2026-10-29<br>
**Branch / source HEAD exercised:** `feat/evaluation-format-contracts` / `39956afa262da97f82d8aad59030a6e66a9eb4d0`<br>
**Runtime run:** `dd23dedc71614b6082fcbb1cc2038c6b`<br>
**Disposition:** E2E-001 **PASS** for real native runtime execution, assertion-scoped readiness, judge reachability, durable verification, and same-run four-format projection. Semantic model quality remains unproven because the judge is fixture-controlled.

## Correction to the earlier agent-family result

The prior run `eded2c961df84df3be3fdd9d1b33dedb`, documented in the [initial deterministic-provider report](../task32-2026-10-29/report.md), used `execution=conversation-response`. It exercised the public agent/runtime-family input adapter but produced no runtime tool observation. It is **not** E2E-001 and is not used as runtime-execution evidence here. The valid two-skill × five-iteration result `f47f708d31cf42b489900c870838ea43` remains unchanged E2E-002 evidence; it was not rerun.

## Public path and observed result

The public built-in `eval` command loaded the agent/runtime suite, built an invocation with the caller-selected immutable OpenCode image, ran its actual target and judge through Podman, collected the runner-owned runtime observer stream, evaluated the deterministic assertion, persisted and verified the completed result. No runtime evidence, assertion result, or judge output was injected into the persisted run.

The suite's `fixture_files` input materialized `runtime-proof.txt` with marker `RUNTIME_READ_RESULT_7fbf89c1` in the adapter-created target workspace. The local external provider requested the real OpenCode built-in `read` tool with `path=runtime-proof.txt`. OpenCode executed that tool; the product captured the native start and successful terminal event and the actual tool result. The target then returned the observed marker.

Persisted outcome:

- Run `dd23dedc71614b6082fcbb1cc2038c6b`: `pass`, 1/1 planned job, zero fail/non-evidence/error/not-run.
- Target runtime evidence: `status=complete`, `evidence_eligible=true`, one native observation.
- Observation: `tool=read`, `input={"path":"runtime-proof.txt"}`, `outcome=success`, `start_sequence=1`, `terminal_sequence=2`; result is available and contains the marker. The matching session/message/call IDs and result are in the persisted job artifact.
- Required boundaries `native` and `code_mode_execution`: both `complete`. OpenCode 2.0.23 reports `code_mode_finality=unsupported`; that boundary was not required for this native-read case and does not invalidate its evidence.
- Deterministic check `tool_results.requires[0]`: `pass`. The judge was reached and one strict-JSON judge attempt completed with semantic status `pass`.

### Which assertion requires which observation fields

The case deliberately selects `tool_results.requires[0]`, not a generic “some runtime tool happened” check. `AgentRuntimeAdapter.target_evidence_requirement` adds `runtime_semantics` for `execution=runtime`, requiring `tool`, `input`, `outcome`, `start_sequence`, and `terminal_sequence`. The selected `tool_results` assertion additionally requires the terminal `result_or_error` field. Therefore the union that must be observed for this case is exactly:

```text
tool, input, outcome, start_sequence, terminal_sequence, result_or_error
```

The actual successful observation supplied `result` (the success-side representation of `result_or_error`) as available; `error` was explicitly not applicable. This ties the readiness fix to the accepted assertion contract rather than claiming every runtime case requires every possible field. Source references: `runner/eval_builtin.py:336-361`, `runner/eval_evidence.py:227-283`, `runner/eval_assertions.py:211-257`, and repository plan Task 2.1.

## Formats from this same verified run

After the one evaluation completed, all four outputs were separately requested through the public `eval --render-run` interface against the same persisted run directory. No evaluation, provider request, or container was used for rendering.

| Representation | Artifact | SHA-256 |
| --- | --- | --- |
| JSON | `renders/agent-runtime.json` | `b18e0f88bdf992abe0a5d2a2e24061b5e35737aa9198f74c211755e8e3a9f40c` |
| YAML | `renders/agent-runtime.yaml` | `c0dbe2b13613ca98cdbce946069010da31d413c2a4a7e607d9c4aeba1430c859` |
| Markdown | `renders/agent-runtime.markdown` | `db633d050a92b30ef6a8f4bd9eac9180bebfd3ef7340fd878d379cba52795416` |
| HTML | `renders/agent-runtime.html` | `29f3aa8da69abd09b2b5dec74a78d067ee18747a7148ec2117fce810ebd80093` |

**Renderer refresh (2026-10-29):** Markdown and HTML were regenerated through `eval --render-run` from this same persisted run after PR #89 Task 3.3 corrections. The verified run, JSON/YAML projections, and execution evidence are unchanged; no evaluation or provider call was made. Current Markdown/HTML sizes and SHA-256 digests are in `evidence.json` (`renderer_refresh` records this derivation; `format_projection.outputs` is authoritative). Human design reassessment remains pending.

Parsed JSON and YAML are identical. Both readable reports identify run `dd23dedc71614b6082fcbb1cc2038c6b`, pass status, the runtime case, and its observed marker. The saved `run.json`, job artifact, all four outputs, exact input, logs, image/network inspection, and hashes are retained in this report directory and indexed by `evidence.json`.

## Boundary, substitution, and limitations

Product-owned stages remained real: public input loader and validation, `AgentRuntimeAdapter`, actual OpenCode 2.0.23 OCI invocation, actual native `read` tool, runner runtime observer, assertion evaluator/readiness gate, judge adapter, persistence/verifier, and renderers. The runtime plugin was the actual local Loom source at Git revision `2d321780a485dd9c8cf4093c32f3c35f2349e50c`; its installed `@opencode/plugin` package version was `2.0.29`. A small fixture entrypoint exports that installed plugin source because the runner materializes that entrypoint for its v2.0.23 isolated config root; it is not a stub. The fixture's local `node_modules` tree was made available under the mounted config root so the real plugin could load.

Only the external provider was substituted. The local deterministic OpenAI-compatible provider container returned one actual OpenCode tool call, a response based on the returned tool result, and the judge's required strict JSON. Its judge response is fixture-controlled and reports all authored positive/forbidden entries; consequently this PASS proves the product-owned runtime/evidence/assertion/judge/persistence/render path, not independent semantic grading or live-provider behavior. No paid/live provider or user credential was used. The only logged requests were three `POST /v1/chat/completions` calls to the fixture on Podman network `task32-runtime-followup-20261029`, inspected `internal=true`; request bodies were not logged. No network-egress claim is made about the earlier GHCR transfers.

## Reproduction and provenance

The exact public evaluation command was run from the isolated project directory with the environment recorded in `fixtures/provider-config.json` and `evidence.json`:

```sh
python3 <repo>/bin/opencode-eval-runner eval \
  --input fixtures/agent-runtime-input.json --family agent-runtime \
  --cases runtime-read-result --target-model fixture/mock \
  --network task32-runtime-followup-20261029 --engine podman \
  --timeout-seconds 90 --container-timeout 150 \
  --artifact-dir <run-dir> --format json --output <initial-json>
```

`--transport-retries` was omitted and remained at its default `0`. `OPENCODE_EVAL_RUNNER_CONFIG` named the local provider config; `OPENCODE_EVAL_RUNNER_OPENCODE_IMAGE` selected `sha256:0940e9ac543098bfa51dda81cce643ed3366df1ab8a4e90bf5fcd8601c2e5e39`. `XDG_DATA_HOME` pointed to a fresh isolated directory, `database_seed=None`, and `CONTAINERS_STORAGE_CONF` preserved the original local Podman store. Provider credentials and ambient `OPENCODE_EVAL_RUNNER_*` values were scrubbed; the archived config redacts its dummy API key.

Each renderer was then requested separately:

```sh
python3 <repo>/bin/opencode-eval-runner eval --render-run <run-dir> \
  --format json|yaml|markdown|html --output <distinct-output-path>
```

The earlier combined-skill proof remains at [the initial report](../task32-2026-10-29/report.md), with its persisted run and its own four same-run projections. This follow-up adds only the missing nonempty runtime evidence proof; it does not rerun or alter that skill result.

## Cleanup and remaining checks

After copying the immutable image/network/container inspection records and provider request log, this task's provider container and internal Podman network were removed and absence verified. The pre-existing network and local images were left intact. Focused local checks for invalid input preflight, duplicate combined identities, and corrupt persisted-result rendering passed; exact command/output are in `fixtures/focused-negative-tests.log`.

Task 3.2's two journey proofs are now present. Task 3.3's human/browser review, independent review, and PR readiness are separate and remain open. The historical GHCR layer-transfer status remains unresolved; no whole-workflow no-egress claim is made.
