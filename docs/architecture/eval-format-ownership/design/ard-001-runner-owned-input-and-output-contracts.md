---
title: Runner-owned input and output contracts
type: Architecture
description: Reconciles the generic evaluation engine with runner ownership of two semantically distinct input families and four output representations.
tags: [evaluation, input-contracts, output-contracts, architecture]
---

**Status:** Proposed architecture; no implementation or migration is authorized by this artifact.

## Derived from

- [BR-001 — Accept both input contract families without collapsing semantics](../../../requirements/eval-format-ownership/br-001-accept-both-input-contract-families.md)
- [BR-002 — Own output contracts across named formats](../../../requirements/eval-format-ownership/br-002-own-output-contracts-across-named-formats.md)
- [BR-003 — Provide one user-facing evaluation interface](../../../requirements/eval-format-ownership/br-003-provide-one-user-facing-evaluation-interface.md)
- [OC-001 — Evaluation case input conformance](../../../requirements/eval-format-ownership/oc-001-evaluation-case-input-conformance.md)
- [OC-002 — Evaluation output conformance](../../../requirements/eval-format-ownership/oc-002-evaluation-output-conformance.md)
- [Evaluation format ownership handoff](../../../eval-format-ownership-handoff.md)

## Satisfies

This architecture maps the accepted requirements to the following realization:

| Requirement | Architectural realization |
| --- | --- |
| BR-001 / OC-001 | Runner-host input boundary selects and validates a runner-owned contract for the agent/runtime suite or skill-owned case family. Family identity and semantic adapter remain explicit through evaluation; invalid or ambiguous inputs do not reach execution as accepted cases. |
| BR-002 / OC-002 | One runner-owned evaluation result is rendered through format-specific JSON, YAML, Markdown, or HTML producers. A format changes representation only. Existing integrity-checked JSON artifacts remain the durable evaluation record. |
| BR-003 | The existing public `eval` command is the single user-facing path for selecting either family, configuring/running evaluation, and selecting an output representation. |

Requirements establish behavior; [ARS-001](../specifications/ars-001-runner-eval-contract.md) now defines the host interface, result projection, output formats/destination and failure contract. This artifact still does not establish historical compatibility, polished-report scope, or a formal accessibility conformance-level claim.

## Problem and verified current state

The current public `eval` command requires `--profile MODULE:ATTRIBUTE`. `runner.eval_api.EvalProfile` discovers and normalizes cases and owns fixtures, invocation construction, checks, judging, and semantic meaning. The runner owns selection, attempts, scheduling, generic classification, JSON artifact storage, and summaries. The current `NormalizedCase` carries an opaque `project_data` field but no required family identity or built-in input contract. ARS-001 adds explicitly selected built-in modes and requires the existing profile spelling and no-new-flags behavior to remain unchanged; no migration or removal is authorized.

`runner/eval_artifacts.py` owns versioned JSON envelopes (`eval-run/v1`, `eval-artifact/v1`, paired artifact v1), strict shape validation, canonical JSON integrity IDs, and filesystem persistence. The architecture document describes these artifact schemas as internal/on-disk contracts rather than stable external APIs; it also excludes an input-JSON API and says profiles own discovery/normalization. These boundaries conflict with the new requirements and must be reconciled in a future implementation/doc update, not treated as limiting requirements.

The Containerfile's runtime images contain the transport runtime and `container/invoke.py`, and are launched as a one-invocation entrypoint. The host CLI constructs orchestration and calls `invoke`; no evidence in the inspected Containerfile supports putting suite parsing, evaluation planning, artifact writing, or output rendering in the image.

The handoff's commit-pinned Loom source summary establishes two different semantic inputs:

1. **Agent/runtime suite:** versioned suite/cases with execution mode and possible agent/runtime/action/tool-result assertions, output expectations, and fixture content.
2. **Skill-owned case:** prompt and expectations, optional negative/must-not conditions and trap information, evaluated through the pinned baseline/candidate ablation lifecycle.

These are separate family contracts. [ARS-001](../specifications/ars-001-runner-eval-contract.md) realizes the Task 1.1 inventory's agent/runtime v1 field set, three observed skill wrappers, current assertion families, skill expectation/trap behavior and paired ablation meaning. In particular, action assertions preserve tool-only presence/absence checks, partial-evidence non-evidence, and subset semantics for `args`; selected `arg` comparators remain distinct. Optional `min_source_urls` counts unique, exact-match URLs shared by prompt and final response, with invalid supplied values rejected before invocation; `forbids` remains literal substring matching. Other historical aliases remain outside the promise.

## Constraints and forces

- Preserve the distinct agent/runtime and skill-evaluation meanings; shared field names or similar JSON syntax are not evidence of semantic equivalence.
- Keep the existing single-invocation OCI boundary and reuse its host `invoke` implementation. Do not make the runtime image an evaluation orchestrator.
- Avoid a universal assertion language or flattening skill-ablation comparison into ordinary case pass/fail.
- Produce each required format through the same public `eval` surface. Formats are selectable alternatives, not necessarily simultaneous outputs, per OC-002.
- The JSON artifacts already provide integrity-checked persistence and should be reused rather than replaced by a parallel result store.
- Markdown and HTML are human-readable views and must preserve accessible access to the same result: meaningful semantic structure and reading order, and no information conveyed by color or visual treatment alone. Any HTML interaction included later must be operable without a pointer. The precise accessibility conformance target and test criteria remain for design/specification.
- Existing `EvalProfile` behavior is an additive coexistence requirement: built-in flags must not alter profile-mode behavior. This does not establish a time-bounded compatibility guarantee or migration policy beyond retaining the current path.
- External consumers of the v1 JSON artifacts may exist; no external tolerance guarantee for added integrity-covered `project_metadata.runner_eval` is accepted.
- Exact output content, HTML purpose, report requirements, historical compatibility and migration are product-facing unresolved decisions. Structural design must not silently decide them.

## Invariants and guarantees

| Guarantee | Precondition | Owner / enforcement | Falsification point |
| --- | --- | --- | --- |
| Input is evaluated under one explicitly identified family contract. | A submitted input is presented to built-in `eval`. | Host input loader requires explicit `--family`, validates only that contract and binds immutable family identity to normalized evaluation. | An invalid input invokes a model, or one family is silently reinterpreted as the other. |
| Family semantics survive the shared orchestration path. | Input passed its family-specific contract. | Family adapter maps source values into execution operations while retaining family-specific assertions/context; the engine shares mechanics only. | Runtime/action/tool-result assertions are dropped/treated as skill expectations, or skill baseline/candidate meaning is treated as a normal agent-suite check. |
| Built-in invocations preserve the pinned Loom phase meaning while using one runner-owned executor and OpenCode transport. | Caller selects a valid input and required target model. | ARS-001 fixes OpenCode-only target/judge transport, OpenCode provider/model configuration, reasoning/timeout precedence, retry default 0, role-specific workspace/prompt behavior, family-specific judge gates, and four skill-ablation phase construction; adapters produce specs and invoke existing host `invoke`. A non-OpenCode built-in transport request is rejected before invocation. | A non-OpenCode target/judge invocation occurs, an implicit target model is selected, an unrequested retry occurs, role-decision prompt/workspace changes, a normal deterministic non-pass triggers its judge, paired sides share mutable state, or skill comparison semantics drift. |
| Built-in OpenCode invocations use only the caller-selected, locally verified immutable image and cannot pull. | A built-in target or judge phase is invoked. | Host preflight requires `OPENCODE_EVAL_RUNNER_OPENCODE_IMAGE` to contain a full local image ID or supported digest-qualified identity; it performs local metadata inspection only, checks the declared OpenCode version and invocation-adapter contract against the runner release, and rejects absent, mutable, nonlocal, unknown, or mismatched selections before OCI `run`. The accepted exact identity is preserved in every target/judge spec and each OCI `run` uses pull-never. Existing profile-mode image resolution remains unchanged. | Missing/mismatched identity reaches OCI `run`, a fallback/rewrite occurs, compatibility metadata is absent or unchecked, the selected identity changes between preflight and invocation, or any run can pull. |
| Output format changes representation, not result, and successful output is eligible only when every planned case-iteration job has a verified family result. | Evaluation result is complete and format requested. | Host output layer consumes the same verified result model / durable JSON artifact and applies one renderer; it checks result presence for every planned job before reporting conforming-output success. | Cross-format semantic comparison shows changed case identity, family, classifications, attempts, or relevant source semantic outcome; or execute/render reports success with a planned job lacking a family result. |
| Existing invocation remains one isolated attempt. | An evaluation phase requests execution. | Host engine calls existing `invoke` path; image handles one transport invocation and `result/v1` plus runtime-evidence production only. | A container image performs case iteration, retry, evaluation, or output-format orchestration. |

## Options considered

### A. Runner-owned family adapters over shared engine; one canonical result and renderers — selected

Host-side family-specific contract readers/validators and semantic adapters feed a shared orchestration core for the mechanics it already owns. The adapters retain their own assertion/evaluation models, and the engine result includes an explicit family discriminator plus family-specific outcome/context. A format dispatcher in the host emits one selected representation from the same result/artifact model.

- **Benefits:** Puts ownership where public `eval`, selection, artifact storage, and `invoke` orchestration already live; uses existing mechanics and artifact integrity; avoids duplicate public runners; explicit separation prevents false semantic equivalence; each format producer is independently testable.
- **Costs:** Adds a maintained contract and adapter per input family and output renderer per format. Some source semantics cannot be represented by the existing generic `EvaluationResult` alone; those require an explicit extension or paired lifecycle rather than opaque metadata alone.
- **Failure modes:** Over-normalization can erase family-specific meaning; rendering from a pre-persistence object can diverge from durable artifacts. Bind family identity, use explicit family-owned outcome payloads, and render from verified persisted records to constrain both risks.
- **Operational/security/coupling effects:** All input parsing and report generation run in the host process; images remain small and invocation-scoped. Host trust boundary is unchanged, subject to existing trusted-checkout profile.

### B. Two separately implemented end-to-end evaluators sharing only invoke

Each input family gets its own full planning, execution, persistence, and reporting path, with a common top-level command dispatching to one.

- **Benefits:** Semantic separation is visually direct and family-specific lifecycle code can evolve independently.
- **Costs:** Duplicates selection, retries, runtime evidence, integrity, summaries, and error handling already owned by generic engine; multiplies opportunities for inconsistent behavior and output contracts.
- **Failure modes:** The same evaluation feature or safety fix may be applied to one path but not the other; outputs may drift even for shared mechanics.
- **Operational/coupling effects:** More components and maintenance than the requirements demand; no demonstrated need for isolated engines.

### C. Push evaluation and multi-format reporting into transport images

Images accept suite files, execute cases, and return family-specific or rendered outputs.

- **Benefits:** Self-contained execution bundle and potentially fewer host-side dependencies.
- **Costs:** Breaks the existing one-invocation image boundary, duplicates host orchestration and policy, and complicates access to mounted workspaces/credentials and durable host artifact ownership.
- **Failure modes:** Hidden retries or evaluation behavior inside a container undermine attempt accounting and host artifact verification; output could be reported successful without host validation.
- **Operational/security/coupling effects:** Larger image responsibilities and increased coupling of eval behavior to transport runtime. There is no requirement or demonstrated risk that justifies this.

## Decision

Choose **Option A**. Keep the host `eval` command as the sole user-facing entry point and introduce host-owned contract boundaries for the two input families and the four output representations. Reuse the existing generic engine for common orchestration and the existing OpenCode invocation implementation for each actual target/judge call. Built-in target and judge transport is fixed to OpenCode, with provider/model configuration remaining through OpenCode; reject any built-in request selecting another transport before invocation. Built-in image selection is fail-closed to the caller's immutable local identity, verified through local OCI metadata for OpenCode version and invocation-adapter compatibility, and executed with pull-never; the existing `--profile` path retains its image behavior. The compatibility declaration uses image metadata checked against the runner release's supported contract; it does not introduce an image resolver service or permit registry access. Do not extend the image entrypoint beyond one invocation.

The architectural boundary is:

```text
user
  -> host `eval` (one public interface)
       -> input-family selection + strict contract validation
       -> family-specific semantic adapter
       -> shared planning / invoke attempts / evidence / artifact engine
       -> verified canonical evaluation record
       -> selected JSON | YAML | Markdown | HTML renderer
            |
            +-> host artifact/output destination

shared engine -> host `invoke` -> one OCI transport invocation -> result/v1 + runtime-evidence/v1
```

The canonical record is a runner-owned semantic projection, not a claim that the two inputs have one assertion language. It has common identity/provenance/classification/attempt fields and a family-tagged payload that preserves native semantic outcomes/context. Skill case identity is assigned once during preflight normalization and remains the same in storage, all iterations, paired sides/comparison and every output. Skill baseline/candidate execution uses the existing paired evaluation capability where its lifecycle fits; the skill adapter owns comparison meaning and preserves both sides. Agent/runtime cases retain execution mode and source-specific assertions. ARS-001 specifies `eval-output/v1` as the public projection assembled from re-verified v1 records and a namespaced `project_metadata.runner_eval` payload covered by the existing v1 integrity ID. The existing durable v1 envelopes and their required fields, validation and hash semantics remain unchanged; the projection is distinct from them.

The existing v1 JSON records remain durable persistence and integrity authority. The versioned public JSON projection, YAML, Markdown, and HTML are derived output views, not replacements for v1 records. Public output eligibility requires a completed, verified evaluation with a family-owned result for every planned case-iteration job; the manifest and every required case/pair record must pass existing validation/integrity verification and family metadata must agree with record identity. A terminal pre-result orchestration/preparation error or not-run job is outside this precondition and remains without a fabricated family result/classification. When any planned job lacks a family result, execute/render cannot report successful conforming output. Every eligible output format comes from the same verified projection. ARS-001 defines execute/render modes, format selection, destination, and command failure behavior without changing the v1 checksums or making a compatibility claim about external readers.

Built-in input family is selected explicitly by `--family`; no structural or filename auto-detection is used. The family selector determines validation and provenance, not conversion. No default coercion/conversion between families is permitted.

## Structure and flows

### Host orchestration responsibilities

1. The public `eval` CLI preserves existing `--profile MODULE:ATTRIBUTE` behavior and adds execute mode (`--input`, explicit `--family`, selection and one `--format`) plus persisted-result render mode (`--render-run`, one `--format`). Built-in `--output` selects a file, otherwise the representation goes to stdout while diagnostics go to stderr. New-mode controls cannot silently redirect or replace profile mode.
2. An input boundary reads the requested family format, applies only that family's runner-owned validation, assigns and freezes canonical identity, validates supported feature semantics, and creates a typed family input. Whole-document validation completes before selection can trigger inference. Supported wrappers/versions are explicit; undocumented aliases and historical variants are not implied.
3. The built-in configuration resolver requires caller-selected `--target-model` and `OPENCODE_EVAL_RUNNER_OPENCODE_IMAGE`; it resolves target/judge models, reasoning and timeout overrides under ARS-001 precedence and records each resolved phase configuration. Image preflight verifies the exact immutable local ID or supported digest-qualified identity and image-config labels (`org.opencontainers.image.version` and `io.opencode-eval-runner.invoke-adapter`) against the expected values declared by the runner release before any OCI `run`. It uses local metadata inspection only and rejects missing, mutable, nonlocal, unreadable, or mismatched values without fallback. The exact identity is retained in all target and judge specs and OCI pull-never is set on each run. OpenCode transport is fixed; any built-in attempt to select another transport is rejected before invocation. Provider/model configuration, auth/config discovery and execution remain within existing OpenCode `invoke` responsibilities.
4. The agent/runtime adapter prepares distinct target and read-only judge projects. It preserves execution modes, the role-decision tool-denied wrapper and prompt suffix, runtime/read-only workspace rules, fixture/plugin/config setup, assertion-scoped evidence readiness and deterministic outcomes. It creates a normal judge spec only when the target is usable and every deterministic check passes. The final classifier preserves exact precedence: target failure, unready evidence, or required judge failure => non-evidence; otherwise deterministic fail => fail; otherwise deterministic non-evidence => non-evidence; otherwise semantic pass/fail decides. Thus fail outranks non-evidence among checks, but not target/readiness/required-judge failures. Both target and judge use OpenCode.
5. The runner-owned skill adapter always uses the pinned paired lifecycle for skill-family inputs: separate baseline/candidate targets and judges, baseline exclusion, candidate-only native skill, read-only phase workspaces, OpenCode native skill-load/evidence checks, and the exact skill-specific score/trap/comparison rules. All four phases use OpenCode, and a non-OpenCode transport request is rejected before invocation. Its judge gate is family-specific: non-evidence checks suppress the judge, while a behavioral fail alone does not. Pinned Loom files are source evidence only; their code is not loaded as a runtime dependency. The generic paired engine executes and validates the sides; the runner-owned adapter supplies policy.
6. The shared engine schedules jobs, calls the host `invoke` adapter once per attempt, applies existing explicit retry/replay-safety policy (built-in mode defaults to zero retries), reads authoritative runtime evidence, classifies common outcomes, and persists verified artifacts.
7. A result/output module verifies persisted v1 records and confirms that every planned case-iteration job has its family-owned result before assembling the versioned common result, validating it, and rendering the selected format. If any job lacks that result, execute/render cannot report successful conforming output. Serialization/rendering must not re-run checks, alter verdicts, fabricate family results/classifications, or reconstruct missing evidence from diagnostic fields. A separate render request reads the same completed eligible run and never invokes.

### Image responsibilities

The Containerfile images remain transport-specific runtime images. They receive one prepared invocation and produce one low-level validated invocation result and runtime evidence. They do not parse suite/case contracts, perform family selection, construct baseline/candidate comparisons, retry, write run artifacts, calculate output format contracts, or render reports. The host remains responsible for credential/workspace mounting and artifact integrity as in the current `invoke` flow.

### Output contract relationship

Use one semantic result model and four format-specific contracts/producers. Verified v1 records plus their integrity-covered family metadata are the durable source; the new versioned public JSON projection and YAML/Markdown/HTML are alternate representations of the same completed evaluation. Each format has a separately testable conformance boundary, and shared semantic fields map consistently. ARS-001 selects run-level and case-level fact coverage needed by OC-002. This does not decide whether a richer HTML report or interaction model is wanted.

Markdown and HTML must be designed as accessible views of that result, not merely visual facsimiles: headings, relationships, and reading order must be meaningful to assistive technology, and status or other distinctions must not depend on color alone. If HTML includes interactive features, those features must have a keyboard-operable path. The design/specification must select and make verifiable the applicable accessibility conformance target; this architecture does not prescribe that target or imply a polished report.

Existing `eval-run/v1`, `eval-artifact/v1`, and paired artifact v1 remain the persistence and integrity baseline. They are not automatically declared public output contracts merely because stored as JSON. The selected realization is a distinct `eval-output/v1` public projection over verified v1 records, with family identity/outcome stored in `project_metadata.runner_eval`, a field already included in artifact integrity calculation. The v1 envelopes' schema, required fields and integrity meaning are unchanged. Whether any external consumer rejects additional project metadata is unknown; no external compatibility promise is made. Do not overwrite or reinterpret v1 fields.

## Input / operation coverage

| Input/operation | Required architectural path | Boundary that rejects silent wrong meaning |
| --- | --- | --- |
| Valid agent/runtime suite | Suite-specific validation -> agent/runtime adapter -> shared mechanics -> family-tagged result | Required suite identity/version and its own execution/assertion semantics survive through artifact/output. |
| Agent/runtime invocation configuration | Caller-selected target model plus resolved phase overrides -> target/judge specs | No implicit target model; role mode, workspaces, timeout/reasoning precedence, and judge gate match ARS-001. |
| Invalid agent/runtime suite | Rejected before evaluation as valid | Suite contract validator; no invocation begins for the rejected input. |
| Valid skill case set | Skill contract validation -> skill adapter -> baseline/candidate paired lifecycle -> family-tagged result | Prompt/expectation and baseline/candidate context remain skill-oriented; no agent-suite assertion is fabricated. |
| Invalid skill case set | Rejected before evaluation as valid | Skill contract validator; no invocation begins for rejected input. |
| Ambiguous input | Explicit family selection required or observable rejection | Family resolver must never choose an interpretation silently. |
| Built-in request selects non-OpenCode target or judge | Rejected before any invocation | Fixed OpenCode built-in boundary; no silent rerouting. Existing `--profile` transport behavior is unchanged. |
| Built-in image is missing, mutable/tag-only, nonlocal, or has unknown/mismatched OpenCode version or invocation adapter | Local-only preflight rejects before OCI `run`; no fallback or pull | Required caller identity, local image metadata compatibility check, identity preservation across phases, and per-run pull-never enforcement. Existing `--profile` image behavior is unchanged. |
| Each of JSON/YAML/Markdown/HTML | Same verified completed evaluation -> selected renderer | Output contract validator; format choice does not change evaluation result; success is not reported on production failure. |
| Pre-result terminal orchestration/preparation error or not-run planned job | Preserve terminal state without family result/classification -> no successful conforming public output | Eligibility check requires one verified family result for every planned case-iteration job; execute/render may not fabricate a result or claim success. |
| Retry / incomplete runtime evidence | Existing host orchestration and runtime-evidence rules | `invoke` remains one attempt; renderer is downstream and cannot make missing evidence pass. |
| Paired skill ablation | Two explicit side evaluations -> skill-owned comparison -> paired result | Existing paired API can preserve side records; adapter supplies comparison meaning, engine does not invent score/threshold. |
| Skill ablation invocation configuration | Four isolated target/judge phase specs and side-specific prepared projects -> paired engine | Separate baseline/candidate workspaces/configs, candidate-only skill/methodology and native-load/readiness semantics are preserved. |

## Failure and recovery

- Invalid or ambiguously identified inputs are rejected before the first model invocation. Exact diagnostic strings and valid-sibling continuation behavior are not specified by OC-001.
- A family adapter exception or contract validation failure is a host evaluation error, not a behavioral FAIL. It must not be converted into a passing/failed assertion.
- Artifact integrity or renderer conformance failure prevents success reporting for the requested output. The exact cleanup and retry behavior for partial output is not specified; do not infer retries from generic invoke retry policy.
- A pre-result terminal orchestration/preparation error or not-run job leaves its planned job without a family-owned result and makes public-format eligibility fail. The runner preserves the error/not-run state without fabricating a family result or behavioral classification; execute and render paths cannot report conforming-output success.
- If one representation can be written but a later requested representation fails in a future multi-format mode, atomic all-or-nothing semantics are not established. Current requirement selects one representation per invocation, reducing this case; if simultaneous output is adopted, define partial-output semantics first.
- Durable JSON is the repair/debug authority. Derived formats should be reproducible from its verified result; they must not be treated as evidence that overrides it.

## Security / trust boundaries

Input files, fixtures, prompts, and expected output data are supplied to the trusted host runner. Contract validation protects semantic correctness and input shape; it is not hostile-plugin isolation. Continue the established trusted-checkout model. Do not load executable family plugins from input files or move file parsing into a broader-privilege runtime image. The image continues to receive only invocation-scoped inputs under the existing mount, credential, timeout, and isolation controls.

## Verification and composition

The architecture is proven only when the assembled public `eval` path demonstrates:

1. Representative valid inputs from both families pass only their respective conformance contracts and retain distinct family identity and assertions in results.
2. Built-in eval rejects a missing target model and every non-OpenCode target/judge transport request before invocation; OpenCode model/reasoning/timeout override precedence and Loom phase defaults are observable in each actual `InvocationSpec` and persisted provenance. Role-decision prompt treatment, tool denial, workspace modes, runtime plugin/config setup, judge isolation and judge skip on deterministic non-pass match ARS-001. Existing `--profile` mode retains its prior transport flexibility.
3. Automated local tests prove that missing, tag-only/mutable, nonlocal, uninspectable, wrong-version, and wrong-adapter image choices reject before OCI `run`; accepted immutable local IDs/digests preserve exact identity through all target/judge specs and command construction sets pull-never. Tests prove host preflight neither pulls nor contacts a registry, and profile-mode image selection is unchanged.
4. Malformed/nonconforming and ambiguous inputs are not invoked as valid evaluations.
5. A representative skill ablation proves separate target/judge workspaces/configs, OpenCode transport for all four phases, both sides' attempts/evidence/readiness/native skill-load checks, exact scores/delta/trap/value classification, and candidate absolute pass; the generic paired lifecycle does not invent skill policy.
6. From one public interface, request each of JSON, YAML, Markdown, and HTML in turn. Validate each against its owned output contract and compare semantic result facts (identity, family, classifications, relevant assertions/comparison, attempts) against the same durable evaluation.
7. Markdown and HTML retain meaningful structure and reading order, expose status distinctions without color-only signaling, and any HTML interactions are keyboard-operable. The precise conformance target and verification method are set by the downstream design/specification.
8. Corrupt or invalid durable JSON fails verification and is not used to produce a reported-success output; output production failure is not reported as successful.
9. A completed verified evaluation with a family result for every planned case-iteration job can produce conforming output. A pre-result terminal orchestration/preparation error and a not-run job leave no family result/classification and cannot result in a successful conforming-output claim from either execute or render mode.
10. The real image entrypoint continues to execute one invocation only; no case parsing, retry, report rendering, or suite orchestration is delegated to it.

## Consequences

- `eval-engine-architecture.md`'s profile-owned discovery/normalization rule and explicit input-JSON exclusion become superseded for the two runner-owned families. Preserve the generic engine's common-mechanics boundary but document its family adapters and output projection layer.
- `eval-usage.md` must eventually describe both built-in contract paths and a single format choice through `eval`; `invocation-usage.md` should continue to distinguish `invoke` (one attempt) from `eval` (host orchestration).
- The existing `EvalProfile` API and profile-mode command remain available with the same behavior when invoked without new built-in flags. The built-in contract is additive and does not migrate profile users.
- Existing artifact persistence and hash verification are reused, not replaced. The selected family payload is namespaced under integrity-covered `project_metadata.runner_eval`; the separate public projection has its own `eval-output/v1` schema. Do not mutate existing v1 meanings or hashes.
- No separate renderer service, database, output store, image tier, universal assertion DSL, or format conversion protocol is warranted by current requirements.
- A polished report is not in baseline scope; Markdown/HTML must be functional, contract-conforming output, but “polished” and report semantics await authority.
- Accessibility is a constraint on Markdown/HTML views, not a report-content promise. The precise accessibility conformance target and verification criteria belong to downstream design/specification and remain open here.
- The Task 1.1 responsibility inventory's statement that the normal Loom `run_case` invokes its judge after deterministic failures is stale against the pinned current `evidence_judge_adapter.py`, which returns no judge spec for any non-pass check. ARS-001 is normative for implementation; reconcile the inventory statement as a later documentation-reconciliation task rather than using it as current behavior.

## Open questions

| Question | Answering authority | Blocks |
| --- | --- | --- |
| What compatibility/migration behavior is required for current Loom inputs and runner-produced JSON artifacts, and on what timing? | User/product owner | Blocks migration commitments and cutover policy. |
| Do external consumers require strict rejection of added `project_metadata.runner_eval` data, and what compatibility is required? | User/product owner informed by consumer inventory | Blocks external-reader compatibility claim only; the existing v1 schema/integrity guarantees and new projection remain specified. |
| What precise accessibility conformance target and verification criteria apply to Markdown/HTML views? | Design/specification owner, with user/product authority if the target changes the product promise | Blocks detailed accessibility conformance claims and test criteria, not the minimum architectural constraints above. |
| What does HTML mean: a static representation, interactive exploration, or report? Is a polished report required, for whom, and distinct from HTML? | User/product owner | Blocks report/HTML product promises only. |
| Is compatibility with historical input aliases beyond ARS-001's explicit accepted wrappers required? | User/product owner | Blocks accepting additional aliases only; ARS-001's listed current contract is implementation-ready. |

These questions are not permission to delay the accepted guarantees: both families, four outputs, and one shared interface remain in scope. The future contract/specification work must close the questions that affect its exact schemas or compatibility claims.
