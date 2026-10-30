---
type: Architecture
title: Pin the OpenCode catalog through its supported file interface
description: Resolve a current registry before inference and share its bytes across built-in evaluation phases without changing model or reasoning selection.
tags: [architecture, opencode, catalog, compatibility]
timestamp: 2026-10-30T00:00:00Z
---

**Status:** Implemented and revalidated for exact OpenCode 2.2.2; provider-free assembled resolver→OCI→runtime catalog/model/variant consumption PASS, including the nullable effort-option fixture. Snapshot reuse across phases/retries also PASS. No provider inference or availability is claimed; orchestration reuse was verified with injected invocation results.

## Explanation

The runner will obtain the model registry before OpenCode selects a model, then give OpenCode that file explicitly. A built-in evaluation shares one private read-only snapshot across targets, judges, baseline, candidate, iterations and retries. For example, baseline and candidate read the same registry even if the public registry changes between their executions. Their workspaces and configuration remain isolated.

This repairs catalog delivery, not provider availability. It cannot grant credentials, resurrect an unavailable model or make an unsupported reasoning variant valid. The exact requested model and reasoning still govern the request. No per-model temporary provider configuration is part of the normal workflow.

## Derived from

- User-authorized delegated scope, 2026-10-30: resolve a current catalog through OpenCode's supported interface; reuse its snapshot across the paired run; preserve model IDs and explicit reasoning; avoid per-model temporary configuration. This is the authority for this compatibility change, not inferred behavior from code.
- [BR-003 — One evaluation interface](../../../requirements/eval-format-ownership/br-003-provide-one-user-facing-evaluation-interface.md).
- [ARS-001 — Invocation configuration](../../eval-format-ownership/specifications/ars-001-runner-eval-contract.md), section “Built-in invocation configuration.”
- [OC-002 — Output conformance](../../../requirements/eval-format-ownership/oc-002-evaluation-output-conformance.md).

## Satisfies

| Authority | Disposition |
| --- | --- |
| Authorized current-catalog and paired-snapshot outcome | Satisfied by pre-execution host acquisition and run-scoped snapshot ownership below. |
| BR-003 selection through OpenCode | Satisfied at this seam by the native registry-file interface, not runner-authored provider/model definitions. Other interface obligations remain with ARD-001/ARS-001. |
| ARS-001 reasoning precedence, isolation, one invocation per attempt, zero default retries | Preserved; only catalog ownership changes. |
| OC-002 no fabricated verdict or successful output after pre-result terminal errors | Preserved by preparation-error handling. Output production remains satisfied elsewhere by the existing output machinery. |
| Input-family, identity, assertion and report-layout requirements | Unchanged and satisfied elsewhere by existing adapters and ARD-001/ARS-001, not re-specified here. |

## Verified premises

The original implementation was researched against exact upstream tag `v2.0.23` at `0fd7e2829449b052abf0078666669302923d77af`. The runner is now pinned to `v2.2.2`, upstream commit `098aa7fd6e02b03d6fc410f0b052038c7d4c5e81`. Its registry file interface retains `OPENCODE_MODELS_PATH` and `OPENCODE_DISABLE_MODELS_FETCH`; the v1 catalog converter additionally requires model `name` and `release_date`, and provider `npm`. The runner validator and fixture now supply these fields without catalog translation or model/reasoning changes. See the dated upgrade revalidation below; earlier source citations remain evidence for the original decision.

1. [CLI server-process.ts, lines 107–111](https://github.com/anomalyco/opencode/blob/0fd7e2829449b052abf0078666669302923d77af/packages/cli/src/server-process.ts#L107-L111) passes `OPENCODE_MODELS_PATH` as the registry file and `OPENCODE_DISABLE_MODELS_FETCH` as the inverse fetch switch. This is a native CLI integration surface, though the current public V2 CLI page does not document these variables. No cross-version stability guarantee is claimed.
2. [core/models-dev.ts](https://github.com/anomalyco/opencode/blob/0fd7e2829449b052abf0078666669302923d77af/packages/core/src/models-dev.ts) uses configured file first; otherwise KV cache and bundled snapshot precede a blocking fetch. Background refresh is forked, not a model-selection readiness barrier. It does not read legacy XDG `cache/opencode/models.json`. File-read failure is swallowed and can fall back to the bundle: runner prevalidation is essential. File population ignores KV cache. Disabling fetching prevents background registry refresh.
3. That source defaults to **`https://models.opencode.ai/api.json`**, not the general models.dev API. Its normalizer consumes provider `id/name/env/npm/models`, model `id/limit` and `reasoning_options`. Use this endpoint's bytes, without translating another catalog generation.
4. A read-only GET on 2026-10-30 returned 5,951,397 bytes, SHA-256 `75dc597a3000fe7bcc42c545f55812dd690d63333f81ce8a99c0a414d310142c`. OpenAI `gpt-6.1-sol` contained effort values `low/medium/high/xhigh/max` in `reasoning_options`. This demonstrates the current compatible shape, not a catalog to ship or permission to change caller effort.
5. Repository `runner/cli.py:65–67,327–350` discovers the legacy host cache and mounts `/seed/models.json`; `container/invoke.py:406–407` copies it to the obsolete cache location. The reported premise is confirmed. Repair delivery rather than adding aliases or waiting longer for refresh.
6. `container/invoke.py:736–750` appends explicit reasoning as `#variant`, rejects an embedded variant plus separate reasoning, preserves embedded variants, and leaves an unset selection at provider default. [V2 models documentation](https://opencode.ai/v2/docs/models) confirms run variants and unknown-variant rejection. Preserve this and ARS-001's phase-specific inheritance rules.

Source retrieval used webfetch-mcp first; exact-tag source was also downloaded read-only to `/tmp/opencode/catalog-architecture-20261030/` after an initial guessed source path failed. No inference, live evaluation, service mutation or external skills-repository modification occurred.

## Decision question

How can isolated invocations consume a current catalog before selection, while paired phases see the same bytes and model/reasoning policy stays in OpenCode?

## Drivers and constraints

- Automatic resolution cannot depend on obsolete implicit host cache, bundle age or background timing.
- Preserve explicit `--models-catalog` and `OPENCODE_EVAL_RUNNER_MODELS`, in that precedence order. Explicit snapshots remain caller-controlled, not certified fresh or silently replaced.
- No provider/model rewriting, alias creation, variant synthesis, automatic effort downgrade, config normalization or skills migration.
- Preserve credential inventory/redaction, immutable local image selection and pull-never. A registry metadata GET is not an OCI image pull and does not relax the image boundary.
- Use a run-local file, not a cache service, daemon, database migration or new public-result schema.

## Options considered

| Option | Benefits | Costs, failure modes and disposition |
| --- | --- | --- |
| Continue cache seeding and sleep/retry for refresh | Small apparent patch | Wrong interface; stale boot selection and paired divergence remain. Reject: fails the confirmed compatibility and snapshot requirements. |
| Host raw snapshot + native file path, fetching disabled | Direct native 2.0.23 interface; deterministic input; existing read-only mount and credential inventory suffice | One bounded network acquisition by default; version compatibility needs focused tests. **Choose.** |
| Local HTTP registry via native URL option | Can serve pinned bytes | Needs server/network lifecycle, while URL alone still permits bundled boot data. Extra machinery without benefit over file input. Reject. |
| Translate catalog into per-model config | Can expose a missing model | Duplicates normalization, package selection and reasoning controls; conflicts with accepted workflow. Reject. |

## Decision

### Acquisition and lifetime

The host owns resolution and snapshot lifetime. Direct OpenCode `invoke` resolves within its temporary invocation lifetime before OCI launch. Built-in `eval` resolves once **after complete input/selection validation and before scheduling any phase**; retain the file until all lanes/attempts finish. Supply that same path through every existing `InvocationSpec.models_catalog`. Adapters do not acquire catalogs. All four ablation phases, selected cases/iterations and authorized retries share the bytes. This run-level boundary is simpler and stronger than acquisition per pair.

Precedence: explicit catalog path > `OPENCODE_EVAL_RUNNER_MODELS` > bounded GET from `https://models.opencode.ai/api.json`. Remove **implicit** legacy XDG-cache discovery; retain explicit opt-in to that file. Snapshot explicit inputs too, so later source edits cannot change phases. Publish only after a complete read/download, compatibility validation and existing credential inventory checks. Enforce the existing 64,000,000-byte inventory ceiling while acquiring, with a finite network timeout of 10 seconds (matching upstream). No new acquisition retries or persistent stale fallback.

Validate UTF-8 JSON and structural fields actually consumed by the pinned normalizer, including provider/model collections, IDs, required limits and container types. Current `reasoning_options` are discriminated objects (for example `{"type":"effort","values":[...]}`, `{"type":"toggle"}`, or bounded numeric options); do not reinterpret them as string arrays. Registry acquisition sends `User-Agent: opencode-eval-runner/1`, required by the observed endpoint behavior. Retain unknown metadata and original bytes. Do not filter models or infer capabilities. This is readability/compatibility validation, not another registry implementation. Do not reject a requested model merely because absent from the raw file: caller OpenCode configuration and provider integrations also contribute models.

The shared run-snapshot guarantee applies to built-in evaluation. Existing profile APIs and caller-supplied per-spec catalog choices remain available. Custom/standalone paired orchestrators can supply the same explicit snapshot; this change does not make separately launched processes one transaction or impose new provider policy on external profiles.

### Runtime integration

Keep `/seed/models.json` read-only. Set **`OPENCODE_MODELS_PATH=/seed/models.json`** and **`OPENCODE_DISABLE_MODELS_FETCH=1`** in the isolated process environment before plugin preflight or invocation starts. Do not copy into obsolete cache storage or mutate KV/database registry state. Runner-controlled values must override inherited/forwarded host values. Both preflight and actual invocation receive them. Retain `/seed/models.json` in the existing runtime credential-source inventory; no catalog contents are exported merely to prove delivery.

### Failures and semantic preservation

Unreadable explicit source, acquisition timeout/HTTP error, oversized input, invalid/incompatible JSON or failed credential inventory is a host preparation/infrastructure error **before inference**, with a bounded actionable diagnostic. No silent bundled/stale fallback, replacement model, paid retry or fabricated family outcome. Existing eval terminal-preparation/error and output-eligibility rules apply; direct invocation uses its existing `RunnerError` command path.

After delivery, native model/provider/variant errors remain transport failures under existing classification and explicit replay-safe retry rules. Unknown explicit effort must not become provider default. Preserve model strings, phase reasoning precedence/inheritance, `#variant` construction and recorded reasoning source exactly. No new public-output field or schema change is required.

## Implementation-facing change surface

Ownership/interface guidance, not a delivery task sequence:

- `runner/cli.py`: shared resolution, direct snapshot lifetime, read-only mount, removal of implicit legacy default. A small shared host module such as `runner/model_catalog.py` can separate acquisition from OCI construction; no service is warranted.
- `runner/eval_cli.py` and `runner/eval_builtin.py`: one built-in snapshot outside worker lanes, supplied in all phase specs. Reuse `runner/eval_types.py`'s catalog field and preserve `runner/eval_execute.py`'s one-spec/one-invoke boundary.
- `container/invoke.py`: native file/fetch environment and obsolete-copy removal; preserve sanitizer and reasoning resolver.
- `tests/test_invoke.py`, `tests/test_eval_builtin_cli.py` and focused catalog tests: acquisition, environment, identity, failure and unchanged selection coverage.
- Implementation owner updates current-behavior claims in `docs/invocation-usage.md`, `docs/eval-usage.md` and any README catalog-default description when the fix ships; this decision-only investigation does not claim they already changed.

## Consequences

Default runs need a successful registry metadata GET; explicit snapshot selection remains the offline route. This is deliberate: silently using an older implicit file cannot fulfill automatic current-catalog resolution. “Current” means fetched at run preparation, not continuously refreshed during inference. Future runs may see updates; a paired run cannot split across versions.

Upstream remains the trusted catalog authority, including package/base-URL metadata. No custom URL forwarding or catalog rewrite authority is added. Private temporary snapshots need no new public artifact contract. Persisted catalog archival is outside scope.

## OpenCode 2.2.2 revalidation (2026-10-30)

- Exact `@opencode/cli@2.2.2` was built into the runner OCI image; image version label and executable both report 2.2.2. Image ID: `bc34c7eaa69a98d2da07a89e3fd6b396c4ee20cae797a34d17e65f4472fc3f57`.
- Provider-free native observer acceptance PASS on 2.2.2, including matched start/terminal identity, results/errors, ordering, and no observer retry. Code Mode inner-call acceptance PASS on 2.2.2 for correlation, identity, input/order and explicit unsupported caller-finality. No paid or external provider inference occurred.
- Catalog consumption retained the native file path, fetch-disabled setting, unchanged model IDs and exact variants. Fixture now satisfies 2.2.2's required catalog fields. Snapshot orchestration tests retain one read-only snapshot across phases and retries.
- Provider-free runtime-evidence acceptance passes all 11 scenarios on the exact image ID above using rootless Podman: `/tmp/opencode/runtime-acceptance-20261030-final5/summary.json`. The initial failure was a harness boundary issue: `clean_env()` isolated `XDG_DATA_HOME`, which also changed Podman's rootless image store. The harness now scopes the host `XDG_DATA_HOME` to Podman only, keeps runner/OpenCode XDG state temporary, inspects the local image before execution, passes its immutable `sha256:` ID to every scenario, and adds `--pull=never` to Podman runs. No host application credentials or database location is exposed to the runner. The timeout scenario allows eight seconds for runtime/plugin startup but the fixture operation takes ten seconds, ensuring the timeout occurs during the real tool call rather than before tool dispatch.
- Independent engine-context check under isolated XDG: graphroot resolved to `/home/n23790/.local/share/containers/storage`, image inspection returned `bc34c7eaa69a98d2da07a89e3fd6b396c4ee20cae797a34d17e65f4472fc3f57`, and `--pull=never --network=none` reported `opencode v2.2.2`. The native-success acceptance case exercised only the local deterministic provider fixture; no paid or real provider inference occurred.
- Exact 2.2.2 nullable-catalog assembled probe: `/tmp/opencode/runtime-acceptance-20261030/catalog-probe/nullable.stdout` confirms resolver snapshot SHA-256 `e4ad4763778c52add9a22ac7f5c389f8a35e68bb5330fa78d117e2751f90c84a`, preservation of nullable `effort.values`, custom nested model `openai/review/nested/catalog-only`, variants `low` and `review-ultra`, and selection of `#review-ultra`. The native `opencode.models.dev` plugin was active. Probe ran with network disabled and a metadata-only entrypoint; it did not submit prompts, create sessions, or invoke providers. The broader matrix independently verifies plugin-backed runtime observation in its local-provider scenarios.
- Code Mode `code_mode_finality` remains unsupported. The plugin execution/exception adjustment does not establish final script-visible values/errors and is not promoted to evidence.

## Confirmation and reconsideration

- Fake-HTTP unit proofs: one acquisition per built-in run; explicit/env precedence without HTTP; application User-Agent; no implicit legacy-file use; timeout, non-2xx, invalid/truncated/oversized/unreadable inputs stop before invocation. Snapshot survives source edits and changing HTTP responses.
- Environment/command proofs: file path and fetch-disable reach preflight and actual process; read-only seed; inherited conflicts lose; obsolete copy gone; credential inventory remains effective and diagnostics do not leak credentials.
- Injected non-spending built-in orchestration proof: all four ablation specs, parallel cases, iterations and an authorized retry share a digest. No acquisition on render-only, list-only, rejected input/selection or direct Copilot invocation. External profile explicit catalog remains usable.
- Reasoning regressions: nested-slash model IDs, exact explicit effort, embedded variant, conflicts, unset provider-default and family-specific judge inheritance. Unavailable explicit variant stays an error, never synthesized or downgraded.
- Load-bearing runtime proof: independent reviewer evidence `/tmp/opencode/catalog-review-20261030/followup/nullable-assembled-probe.log` reports the nullable-effort fixture consumed through resolver→OCI→runtime→exact OpenCode 2.0.23, with expected variants and snapshot cleanup. The exact-version image was credential-free and network-disabled; no prompts or provider calls were made. `/tmp/opencode/catalog-review-20261030/followup/final-validator.log` confirms missing `effort.values` is rejected before OCI without fabricating a result and the current catalog validates. `/tmp/opencode/catalog-review-20261030/followup/agent-orchestration.log` reports shared snapshot behavior across lanes/retries using injected invocation results; this does not prove inference or provider availability.
- Recommend independent critique and implementation review before reliance. Revisit on supported-version/file-interface change, incompatible upstream catalog shape, or demonstrated need for external multi-process snapshot coordination.

## Open questions

No blocking user-owned decision remains for this bounded fix. Exact-version provider-free catalog consumption and catalog snapshot orchestration are verified within the boundaries above. Provider inference/availability, historical registry-format support, external profile cross-process coordination, durable catalog archival and new provider/reasoning policies remain outside the authorization.
