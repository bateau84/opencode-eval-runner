# Eval-engine runner contract and invariant matrix

Issue: #58 — Task 1 worker B  
Scope: runner-contract inventory only; no eval-engine implementation or final architecture selection.

## Source snapshot

This inventory was validated against:

- `bateau84/opencode-eval-runner` `main` at PR #45 merge commit `fd9da10cbe2a8182fc8910ec199a221250deb3ca` (final reviewed PR head `25478106773969870931af3fb34e7b2586746606`), including:
  - `runner/cli.py`
  - `container/invoke.py`
  - `docs/invocation-usage.md`
  - `docs/runtime-evidence-contract.md`
  - `action.yml`
- `bateau84/loom` branch `functionality-anchor-requirements-coherance`, `scripts/run-evals.py` blob `30f2ae87764be180173a9e5b4b609ee79b2f063d`.

PR #45 is merged. The integration branch `eval-engine/01-architecture` matches `main` at merge commit `fd9da10cbe2a8182fc8910ec199a221250deb3ca`, so the final Task 1 synthesis can consume this inventory against the landed runner contract.

## Boundary in one sentence

`opencode-eval-runner invoke` is a **single isolated invocation boundary**. It executes one target or judge call and returns one validated `opencode-eval-runner/v1` result containing the authoritative `runtime_evidence/v1` object. Cases, retries, iterations, target/judge sequencing, assertions, semantic grading, thresholds, aggregation, and final `pass | fail | non-evidence` policy belong above this boundary.

## Contract / invariant matrix

| Area | Post-#45 runner contract | Obligation on a future eval orchestrator | Must not be inferred or moved into `invoke` |
| --- | --- | --- | --- |
| Invocation cardinality | One `invoke` command performs one isolated transport invocation. | Treat every target attempt and every judge attempt as a separate invocation/result. | Hidden retry loops, multi-case execution, target+judge pairing, iterations. |
| Public command | Only `opencode-eval-runner invoke` exists. | Build orchestration on top of this boundary or an internal equivalent that preserves the same semantics. | A public `eval` CLI in Task 1. |
| Input API | No input-JSON request schema exists. Inputs are CLI/Action fields plus UTF-8 prompt/system/config seed files. | Normalize project cases into explicit invocation inputs. | An invented `invocation/v1` JSON request contract. |
| Supported transports | `opencode` and `github-copilot-cli`. | Select transport explicitly for each target/judge invocation. | Assuming equal runtime-observation capability across transports. |
| Isolation | Fresh OCI process, read-only root, tmpfs `/tmp`, dropped caps, no-new-privileges, explicit workspace/mount mode, fresh transport state. | Preserve runner-owned isolation by using the supported host boundary. | Direct transport-container entrypoint as a public contract. |
| Workspace default | `--workspace-mode ro` by default; `rw` is explicit. | Project/profile decides whether a case needs a writable workspace. | A global assumption that evals may mutate the source checkout. |
| Network default | No runner network override unless `--network` is supplied. | Project/profile opts into `host` or another mode when required. | Implicit host networking. |
| Result schema | Each official invocation emits one JSON object with `schema: "opencode-eval-runner/v1"`. | Persist the result as the low-level invocation result and preserve its provenance. | Treating model prose or workspace files as the result contract. |
| Runtime evidence | Every official result must include `runtime_evidence.schema == "opencode-eval-runner/runtime-evidence/v1"`. | Validate and use this object for runtime-evidence readiness. | Any second authoritative observer/evidence projection. |
| Evidence authority | `runtime_evidence/v1` is the only authoritative runtime-evidence object. | Make runtime assertions only from eligible facts in this object. | Backfilling from `tools`, `actions`, `tool_result_evidence`, stdout/stderr, Session/model text, or workspace files. |
| Evidence top-level status | `complete | incomplete | unsupported | invalid`. | Block PASS for all runtime assertions on overall `incomplete` or `invalid`; interpret `unsupported` by required scope. | Treating product success as proof that evidence is complete. |
| Evidence boundaries | `native`, `code_mode_execution`, `code_mode_finality`. | Each runtime assertion declares the boundary/boundaries it requires. | A single global boolean as sufficient evidence-readiness policy. |
| Exact field states | `available | redacted | omitted | unsupported`. | Exact-value assertions require `available`. | Treating redacted/omitted/unsupported values as negative facts or empty values. |
| Unknown coverage | Unknown is never converted to zero. | Keep unknown/unsupported distinct from observed absence. | Passing an absence assertion because a count is missing. |
| Native authority | Direct/native calls include authoritative identity, tool, actor, Session/message/CallID, executable input, ordering, terminal outcome, ancestry. | Consume only fields needed by project assertions. | Reconstructing invocation identity from order, tool name, input equality, or model output. |
| Code Mode execution | Inner call identity/tool/input/parent/outcome/ordering are supportable at `code_mode_execution`. | Assertions over these facts require that boundary to be `complete`. | Assuming exact final caller-visible value/error is known. |
| Code Mode finality | Exact script-visible final value/error is `unsupported` on stock OpenCode 2.0.23. | Mark an assertion requiring this boundary as unsupported/non-evidence. | Converting transformed-handler result/error into final caller evidence. |
| Product vs evidence outcome | `result.exit_code`, timeout, and behavioral/product success are separate from evidence eligibility. | Evaluate transport/product health and evidence readiness independently. | `exit_code == 0` => evidence complete, or evidence complete => behavioral PASS. |
| Inner timeout | `--timeout-seconds`, default 240s, limits the transport invocation inside the container. OpenCode timeout can still emit a structured result with `exit_code: 124`, `timed_out: true`, and timeout-aware runtime evidence. | Treat timeout as target/judge transport failure/non-evidence unless project policy explicitly says otherwise; retain the result artifact when available. | Retrying inside `invoke` or calling timeout a behavioral FAIL. |
| Outer timeout | `--container-timeout`, default 300s, limits the OCI process from the host wrapper. A host-side timeout makes the CLI return infrastructure failure and may leave no result file. | Orchestration owns whether an explicit retry policy applies; record the failed attempt. | Assuming every failed `invoke` has a result JSON. |
| CLI exit vs result exit | Host CLI exit reflects whether the isolated runner/container completed its contract; `result.exit_code` reflects the invoked product/transport result. They are not interchangeable. | Inspect both process outcome and result fields when classifying an attempt. | Using host exit code alone to decide target success. |
| Output parsing | Host requires container stdout to parse as a JSON object. | Treat missing/invalid JSON as infrastructure/non-evidence. | Parsing arbitrary stdout fragments as a successful result. |
| Output validation | Container validates `runtime_evidence` before stdout serialization; host validates it again before writing `--output`. | Reject missing/malformed authoritative evidence rather than degrading to diagnostics. | Assuming the host currently schema-validates every top-level `result/v1` field; its hard validator is specifically the object shape plus `runtime_evidence/v1`. |
| Host/image compatibility | Current host requires official/custom image output to include valid `runtime_evidence/v1`; legacy images without it are rejected. | Treat host+image as a compatibility pair and record selected image/transport configuration. | Silent fallback to an older result shape. |
| OpenCode reviewed runtime | Runtime-observer capability is reviewed against stock OpenCode 2.0.23. | An OpenCode upgrade requires capability/acceptance revalidation. | Assuming later OpenCode versions preserve the same observation boundaries. |
| Copilot runtime evidence | Copilot emits valid result shape but `runtime_evidence.status = unsupported` because no OpenCode runtime observer exists. | Copilot can be used for pure model/judge work where OpenCode runtime assertions are not required. | Runtime tool assertions from Copilot convenience output. |
| Expected plugin | OpenCode-only zero-inference preflight can fail before inference when required plugin activation is unavailable. | Treat preflight failure as infrastructure/non-evidence. | Behavioral FAIL for missing runner/runtime prerequisites. |
| Skills | `--skill` records skill-under-test intent; it does not force-load a skill. `skills_loaded` is observed convenience data. | Project-owned assertions decide whether the intended skill was used and which evidence they require. | Runner-owned skill PASS/FAIL semantics. |
| Reasoning | Optional explicit reasoning; otherwise provider default. OpenCode maps to model variant, Copilot to effort. | Preserve requested reasoning and result-reported source. | Guessing provider defaults or silently substituting effort. |
| GitHub Action modes | Three modes: repository `command` (highest precedence), direct single invocation when `model` is set, or setup-only. | Use command/setup mode when full orchestration or full CLI surface is needed. | Treating Action direct mode as a suite/eval engine. |
| Action surface | Direct mode exposes a subset of CLI options. It does not directly expose network, expected-plugin, seed/config paths, arbitrary env forwarding, or print-result. | Full-feature orchestration should use the host CLI after setup or Action `command` mode. | Designing engine semantics around Action-input limitations. |
| Behavioral semantics | Runner docs explicitly exclude cases, suites, assertions, judge semantics, thresholds, and final verdicts. | Project/profile extension code owns these semantics. | Universal assertion DSL or runner-owned domain rubric. |
| Trust scope | Normal profile is trusted-checkout with reviewed same-process instrumentation. | Preserve documented trust profile in artifacts/config. | Claiming protection from deliberately hostile same-process evaluated plugins. |

## Evidence-readiness decision procedure

The future eval layer must preserve the post-#45 consumer rule exactly enough that runtime evidence cannot be upgraded by orchestration:

1. Require a valid `runtime_evidence/v1` object.
2. If overall status is `incomplete` or `invalid`, no runtime assertion may produce PASS.
3. For each runtime assertion, project/profile code declares the required boundary set.
4. Every required boundary must be `complete`.
5. If the assertion requires an exact field, that field must be `available`.
6. `redacted` or `omitted` means the exact-value assertion lacks complete evidence.
7. `unsupported` means the required fact/boundary is unsupported.
8. Never fill an authoritative gap from diagnostic/convenience fields.

The eval layer may generalize the mechanics of applying a declared evidence requirement, but the **choice of required facts and what they mean behaviorally remains project-owned**.

## Timeout and failure handling

There are three distinct failure planes and they must remain separate.

### 1. Invocation/product failure

Examples:

- model/provider returns non-zero;
- OpenCode invocation times out internally and returns `exit_code: 124`;
- assistant text is empty or unusable for a project-required judge/target step.

This can produce a valid `result/v1` artifact. It is not automatically a behavioral failure.

### 2. Evidence-readiness failure

Examples:

- overall runtime evidence is `incomplete` or `invalid`;
- a required boundary is not `complete`;
- a required exact field is redacted, omitted, or unsupported;
- Code Mode finality is required on stock 2.0.23.

This is non-evidence for the affected assertion, even if the product invocation exited successfully.

### 3. Runner/infrastructure failure

Examples:

- outer OCI timeout;
- invalid/non-object JSON from the container;
- invalid/missing `runtime_evidence/v1`;
- workspace/config/preflight failure.

This is non-evidence. The orchestrator may apply an explicit retry policy, but `invoke` must not retry internally.

## Retry invariant and Loom reference behavior

The low-level runner has **no retry loop**. This is a hard boundary for the eval-engine extraction.

Current Loom puts retry policy in `invoke_container_with_retry()`, above `invoke_container()`:

- default: 2 retries (3 total attempts);
- accepted range: 0–5 retries;
- each attempt calls the runner boundary again;
- successful retries attach attempt count and prior errors to the returned result;
- exhausted retries retain all prior errors;
- backoff is bounded exponential (1s, then 2s);
- retries are only considered for the narrow provider-routing failure containing both `provider.no-route` and `model unavailable`;
- no retry is allowed after observable tools/actions, because replay could duplicate side effects.

This Loom policy is a useful proven orchestration policy, **not** a low-level runner contract. Task 1's final architecture may generalize the policy mechanism, but any retry must remain explicit, artifact-visible, and outside `invoke`.

## Public interface constraints

### Host CLI

The current host command is:

```text
opencode-eval-runner invoke [options]
```

Important constraints for the future orchestrator:

- model and prompt file are required;
- output path is required;
- one result file is written only after host validation;
- prompt/system content is file-based, not an input JSON request;
- direct container invocation is an implementation detail;
- no suite/case/iteration/judge command exists.

### GitHub Action

The Action is an adapter around the same boundary:

1. `command` set: prepare runner/images, then execute repository-owned orchestration;
2. no `command`, `model` set: one direct invocation;
3. neither set: setup only.

Therefore the future generic eval engine must not be designed as a special Action-only feature. Action `command` or setup mode can host it later without changing `invoke`.

## Explicit unsupported / out-of-scope areas

These are constraints to preserve, not gaps for Task 1 to solve:

- exact Code Mode caller-final value/error on stock OpenCode 2.0.23;
- OpenCode runtime observation for the `github-copilot-cli` transport;
- resistance to a deliberately hostile evaluated plugin sharing the trusted OpenCode process;
- input JSON request API;
- public `eval` CLI;
- universal assertion language;
- runner-owned cases/suites/judge semantics/thresholds/final verdict policy.

## Loom cross-check

The current Loom script validates several extraction assumptions.

### Correct behavior to preserve generically

- Target and judge are separate invocations.
- Transport retry is above the invocation boundary.
- Retry attempts/errors are observable in result artifacts.
- Runtime cases have independent concurrency policy from non-runtime cases.
- Transport/infrastructure errors become `non-evidence`, not behavioral failure.
- Case/iteration artifacts keep target result, judge result, deterministic failures, semantic result, timing, and classification.

### Existing Loom behavior that is not the post-#45 runner contract

These are migration facts, not reasons to weaken the new runner boundary:

- Loom still contains a direct OCI/container fallback when the `opencode-eval-runner` binary is unavailable. The post-#45 runner documentation says direct container entrypoints are implementation details, so this fallback must not become a generic eval-engine contract.
- Loom's current `target_scoring_evidence_error()` still checks legacy exactness for `text`, `tools`, `actions`, and `skills_loaded`. Post-#45 runtime assertions must instead apply `runtime_evidence/v1` boundary/field readiness. This migration belongs to later integration work, not this documentation-only worker.
- Loom has legacy observer/evidence-safety compatibility paths alongside the normal runner path. They are not additional authoritative runtime-evidence contracts after #45.
- Loom's behavioral classification names include `behavioral-fail`; issue #58's future generic engine will normalize final engine classification separately. This worker does not define that architecture.

## Invariants handed to Task 1 synthesis

The final architecture must not violate these runner-level facts:

1. **One invoke = one isolated invocation.**
2. **No hidden retries in invoke.**
3. **Retries are orchestration policy and must be artifact-visible.**
4. **`opencode-eval-runner/v1` is the single invocation result envelope.**
5. **`runtime_evidence/v1` is mandatory and authoritative for runtime facts.**
6. **Evidence readiness is assertion-scoped by required boundaries and fields.**
7. **Diagnostics cannot repair missing authoritative evidence.**
8. **Product outcome, evidence outcome, and infrastructure outcome are separate.**
9. **Timeouts exist at inner invocation and outer OCI layers.**
10. **Project/profile code owns behavioral meaning, assertions, judge semantics, and thresholds.**
11. **No universal assertion DSL is implied by the runner contract.**
12. **No input JSON API or public eval CLI exists yet.**
13. **Copilot runtime evidence is explicitly unsupported.**
14. **Code Mode final caller value/error is explicitly unsupported on stock 2.0.23.**
15. **The normal trust profile is trusted-checkout, not hostile-plugin resistance.**

This matrix is intentionally a constraint inventory. The sibling Loom-responsibility inventory and the Task 1 integration owner should use it as a non-negotiable boundary when defining the generic orchestration modules for Tasks 2–5.
