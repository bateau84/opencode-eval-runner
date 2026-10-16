---
type: plan
title: Runner-owned evaluation input and output contracts
description: Specify, implement, and prove both evaluation input families and four output formats behind the existing runner evaluation interface.
tags: [active, plan:runner-evaluation-format-contracts, evaluation, contracts]
---

## Goal

Deliver runner-owned contracts for agent/runtime suites and skill-owned cases, and JSON, YAML, Markdown, and HTML results, through one public `eval` interface. Preserve family semantics and existing integrity-checked JSON artifact guarantees. Built-in target and judge invocations are OpenCode-only; existing `--profile` mode remains unchanged and transport-flexible. Keep evaluation orchestration and parsing/rendering host-owned; `invoke` and its image continue to perform exactly one isolated invocation per call. Built-in retry default is zero. A conforming format is rendered from verified persisted results and requires a family-owned result for every planned job; pre-result errors/not-run jobs are not fabricated into results.

**Execution-plan alignment:** This document's original task numbering and phase prose predate the current Loom Plan revision 5. The Loom Plan is the executable task graph; use its stable task IDs rather than this document's legacy numeric labels. The current graph separates `assembled-e2e`, `renderer-heading-fix`, and `design-check`, and then requires `egress-history-audit`, `docs-repair`, `html-browser-check`, and `cleanup-network` before `independent-review`, followed by `final-critic`. This local plan records scope and acceptance context, not a competing schedule or task assignment.

## Current evidence and remaining gates

This status snapshot reconciles the plan with evidence available on 2026-10-16; it is not a ship-readiness verdict.

| Work/evidence | Current disposition |
| --- | --- |
| Provider-free assembled E2E | Evidence at `/tmp/opencode/assembled-e2e-no-db-20261016T093439` records successful, same-run four-format results for agent/runtime run `4a7930d9847049cea88d364f003722a9` and skill run `ff52fc71eb2c498d8c4edd16f7fa0015`. The local deterministic provider was substituted; this proves those provider-free runs, not whole-workflow absence of network egress. |
| Safety preflight | Preflight evidence records the approved immutable local image and an inspected internal Podman network before E2E. This is bounded to the tested setup and does not resolve historical registry-transfer activity. |
| Renderer correction | Case headings were nested beneath run headings, and both saved runs were rerendered from their existing verified results at `/tmp/opencode/renderer-heading-fix-20261016T`; no evaluation rerun was needed. |
| Design validation | Static inspection of the generated Markdown/HTML passed applicable content/structure checks. Offline real-browser inspection of both HTML artifacts passed; the skill stdout view has minor horizontal overflow, but its content remains present and is not clipped. |
| Historical GHCR activity | Audit evidence confirms two earlier GHCR pull attempts transferred image blobs, config, and manifest. Whether transferred layers remain in local cache/storage and the amount of data transferred are unknown. User acceptance of this historical egress exception is pending; neither local internal-network E2E nor the audit supports a whole-workflow no-egress claim. |
| Remediation/review | BR/OC frontmatter and bundle/index/log validation are complete. The temporary internal Podman network was removed and its cleanup verified. Independent review and the final critic gate are complete; shipping remains blocked pending the user-owned decision on the historical GHCR transfer. |

## Plain-language task map

> Reader aid only. Task details, acceptance criteria, and dependencies govern if this ever differs.

### Phase 1: Ground and specify
| Task | What this actually does |
| --- | --- |
| 1.1 | Establishes current source semantics and compatibility surfaces relevant to the contracts. |
| 1.2 | Defines precise input, output, compatibility, interface, and accessible-view contracts. |

### Phase 2: Implement runner-owned paths
| Task | What this actually does |
| --- | --- |
| 2.1 | Accepts both distinct case families through `eval` and carries their meanings into evaluation results. |
| 2.2 | Produces four conforming views of verified results without changing durable JSON guarantees. |

### Phase 3: Integrate and prove
| Task | What this actually does |
| --- | --- |
| 3.1 | Proves both assembled family paths and same-run format views end-to-end. |
| 3.2 | Independently validates real Markdown and HTML views against the approved design baseline. |
| 3.3 | Independently checks implementation and evidence against approved contracts before shipping. |
| 3.4 | Performs the final critic gate after reviewer findings have a verified disposition. |
| 3.5 | Reconciles architecture, runner, responsibility, and usage documentation with ARD-001/ARS-001. |

### Important task relationships
- Task 1.1 informs specification; it does not decide compatibility/report scope for the user.
- Tasks 2.1/2.2 can parallelize only after a stable shared result contract and disjoint write surfaces; Task 3.1 integrates after both.
- Skill ablation retains baseline/candidate comparison meaning, not merely ordinary pass/fail.
- The current Loom Plan's `independent-review` and `final-critic` tasks are separate gates; documentation reconciliation belongs to `docs-repair`. This local plan's original numeric labels are not live Loom task identities.

### Whole plan in one sentence

Inventory sources → specify contracts and gate user-owned choices → implement both families and four formats behind host `eval` → reconcile docs → prove and independently review → final critic gate.

## Assumptions

- **[ASSUMPTION]** Approved requirements and ARD-001 bind scope and architecture; detailed schema and serialization are for the specification task.
- **[ASSUMPTION]** Baseline Markdown/HTML are functional views of the same result, not a polished report; ARS-001 disclaims a WCAG conformance-level claim and richer report scope.
- Historical input migration and external v1 consumer compatibility remain unpromised. The existing `--profile` mode remains additive and transport-flexible; built-in target/judge transport is OpenCode-only by user decision.

## Out of scope

Polished report beyond functional baseline views; image-side orchestration; universal assertion language or semantic conversion; unauthorized historical input migration/external artifact compatibility promises; provider/spend compatibility claims; simultaneous output of multiple formats.

## Sources

| Source | Status and use |
| --- | --- |
| [Requirements bundle](../requirements/eval-format-ownership/index.md): BR-001–003, OC-001–002 | Approved: two distinct inputs, four output formats, one interface, invalid/ambiguous rejection and same-result representations. Exact schemas and historical compatibility remain open. |
| [ARD-001](../architecture/eval-format-ownership/design/ard-001-runner-owned-input-and-output-contracts.md) | Critic-approved for planning; governs host family adapters/shared orchestration, verified result/rendering, v1 artifact integrity, one-invocation boundary and accessibility. Detailed compatibility/content remain open. |
| [Handoff](../eval-format-ownership-handoff.md) | Intent and pinned Loom source provenance: `f0e1a78ce2e2171d9b9a755e5d1f323e02994bab`. |
| [Old engine architecture](../eval-engine-architecture.md), [runner contracts](../eval-engine-runner-contracts.md), [responsibility inventory](../loom-eval-runner-responsibility-inventory.md), [eval usage](../eval-usage.md), [invocation usage](../invocation-usage.md) | Existing docs to reconcile, not authority narrowing new requirements. Paths verified; detailed content inventory belongs to Task 1.1. |
| [runner/eval_api.py](../../runner/eval_api.py), [runner/eval_artifacts.py](../../runner/eval_artifacts.py) | Inspected current profile API and artifact persistence/validation; current run/artifact/paired v1 envelopes and integrity are preserved unless authorized otherwise. |
| Designer report guidance (conversation) | Markdown/HTML are accessible views of the same result; polished report optional/user-owned. |
| Architecture bundle log | Critic reported a nonblocking malformed-entry caveat in `get_log`; no impact on approved ARD and no assumption of a defect. |

## Obligation map

| Obligation | Satisfier / owner | Verification | Disposition |
| --- | --- | --- | --- |
| BR-001 / OC-001: distinct agent/runtime and skill contracts, reject invalid/ambiguous input before evaluation, preserve each meaning | ARD-001; Task 1.2 specifies, 2.1 implements | Contract tests; E2E-001/002 with real files and execution | Implement |
| BR-002 / OC-002: all four conforming formats represent same result; failed production not successful | ARD-001; Task 1.2 specifies, 2.2 implements | Local parity and E2E-001/002 each compare all four separately obtained representations against one completed, verified source result; corruption/output-failure checks | Implement |
| BR-003: both families, evaluation and format selection via one public interface | ARD-001 existing `eval`; Tasks 1.2/2.1/2.2; Task 3.1 proves | Same public entry in both E2E scenarios | Implement |
| Family provenance/semantics survive shared orchestration | ARD-001 family-tagged result; Task 2.1 | Local adapter and vertical input-to-durable-record proof; E2E | Implement |
| One-call invocation boundary; host owns orchestration/retries/artifacts/rendering | ARD-001 and invocation architecture; Task 2.1/3.1 | Invocation regression and E2E with real host/image | Implement |
| Preserve current integrity-checked JSON artifacts; no silent v1 reinterpretation | ARD-001; Tasks 1.2/2.2 | v1 schema/integrity regressions and corrupt-record E2E | Implement |
| Accessible Markdown/HTML (structure/order, non-color status, keyboard access to any interaction) | ARD-001; Task 1.2 specifies criteria | Renderer tests and real generated-document check in 3.1 | Implement |
| Exact contract fields, interface grammar, semantic mapping | Task 1.2 realizes ARD-001 | Spec review becomes implementation/test baseline | Implement |
| Historical input aliases/migration and external v1 consumers | User/product owner | No compatibility claim until decided | No alias/migration/external-reader compatibility promise; preserve existing profile mode and its transport flexibility |
| Polished report beyond accessible baseline | User/product owner | No richer-report claim absent authorization | Out of scope by agreement in BR-002 baseline; deferred |

## Risk boundaries

- **Source drift:** Task 1.1 checks pinned Loom formats/features against handoff before contract scope is finalized; no undocumented aliases or silent narrowing.
- **Compatibility:** Until user decisions, preserve v1 structure/integrity and make no historical/migration claim. If spec cannot satisfy preservation plus new contracts, pause only affected scope and return to user/architect authority.
- **Semantic loss:** Opaque metadata alone is not proof. Task 2.1 proves real source input to family-tagged verified result, including both ablation sides/comparison.
- **Representation/accessibility drift:** Task 2.2 compares views with verified durable facts; Task 3.1 checks actual Markdown/HTML against specified criteria.
- **Image boundary:** Suite orchestration stays host-side; actual `invoke` remains one isolated invocation per call.

## End-to-end proof

### E2E-001: Agent/runtime suite to four faithful views
- Outcome: Valid agent/runtime suite runs under its own execution/assertion meaning through public `eval`; every selectable format conforms and represents that result. Invalid/ambiguous input is rejected pre-invocation.
- Entry point: Public host `eval` command.
- Product-owned path: Real suite file → host family validation → agent/runtime adapter → shared evaluator → host `invoke` and real one-invocation image → runtime evidence → integrity-checked durable record → JSON/YAML/Markdown/HTML projection.
- External substitutions: Model/provider may use authorized deterministic endpoint/sandbox; retain real host invocation adapter/image. No evaluator, verifier or renderer mock.
- State provenance: Input semantics come from submitted suite; attempts/evidence/artifact from this run; views from verified durable record.
- Externally meaningful assertion: Same interface; family semantics retained; all four outputs conform and preserve identity/classification/attempts/assertions. Invalid input causes no invocation.
- Failure/recovery: Test invalid/ambiguous rejection, integrity rejection and no false success on render failure; no new retry promise.
- Human design check: Required for actual Markdown/HTML structure/order, non-color status and keyboard access for controls, per Task 1.2 criteria.
- Executes in: Task 3.1.

### E2E-002: Skill cases and paired ablation to four faithful views
- Outcome: Valid skill cases run via same public `eval`, retaining expectations and (for ablation) both baseline/candidate sides and skill-owned comparison; all formats represent same result. Invalid input is not treated as valid.
- Entry point: Public host `eval` command.
- Product-owned path: Real skill-case file → host validation → skill adapter → real target/judge or paired lifecycle → host `invoke` per attempt → verified durable side/pair result and comparison → selected format.
- External substitutions: Model/provider may use authorized deterministic endpoint/sandbox; all product-owned evaluation, invoke, storage/verifier and renderer stages remain real.
- State provenance: Prompts/expectations/trap conditions and sides originate in submitted input; both outcomes/comparison are produced in this run; output derives from verified records, not injected state.
- Externally meaningful assertion: Same interface and skill meaning; sides/comparison retained; formats conform and preserve identity/classification/attempts/comparison. Invalid input is rejected pre-invocation.
- Failure/recovery: Test malformed/ambiguous input, corrupt records and no false success on render failure; no new retry promise.
- Human design check: Required for Markdown/HTML under same criteria as E2E-001.
- Executes in: Task 3.1.

## Phases

### Phase 1: Ground and specify

#### Task 1.1: Inventory current source formats and compatibility surfaces [M] → owner: researcher
Target/change surface: Read-only pinned Loom sources, `runner/eval_api.py`, `runner/eval_artifacts.py`, CLI/usage/invocation docs, old architecture/responsibility docs. No source edits.
Type: Research
Nature: Research
Applicable skill: work-decomposition, risk-driven-planning
Implements: [ARD-001](../architecture/eval-format-ownership/design/ard-001-runner-owned-input-and-output-contracts.md)
Acceptance criteria:
- [ ] Record actual shapes, optional features and semantics of both pinned Loom families; identify discrepancies with handoff/ARD.
- [ ] Inventory current `eval`/profile surfaces, in-repo v1 artifact readers/writers/consumers and affected docs; distinguish observed from unknown external consumers.
- [ ] Make no compatibility, migration or report decision; provide evidence and concrete questions to user/Task 1.2.

#### Task 1.2: Specify input/output contracts and compatibility boundary [L] → owner: architect / design-specification owner
Target/change surface: New implementation-facing contract spec, interface contract, accessibility criteria and Task 1.1 compatibility mapping; place in architecture bundle.
Type: Documentation
Nature: Documentation
Applicable skill: design-specification, architectural-spec, accessibility-design, risk-driven-planning
Implements: [ARD-001](../architecture/eval-format-ownership/design/ard-001-runner-owned-input-and-output-contracts.md)
Depends on: 1.1; user decisions only for affected promises.
Acceptance criteria:
- [ ] Specify distinct boundaries and semantics for both families, including baseline/candidate meaning when ablation applies.
- [ ] Specify one public `eval`, four selectable format contracts, shared semantic facts and rejection/output-failure behavior. For each family, define one evaluation that completes and passes verification; then obtain each representation separately through the public interface from that same completed result (for example, selecting/rendering a persisted result). Require comparisons of every representation against that source result; simultaneous emissions are not required.
- [ ] Define relation of public JSON to existing v1 envelopes without reinterpreting/weakening schema or integrity; incompatible proposals return for user/architecture decision.
- [ ] Define falsifiable Markdown/HTML accessibility checks (structure, order, non-color status, keyboard access for interactions); no richer report without authorization.
- [ ] State accepted features, excluded variants, compatibility limits and unresolved user decisions; no material choice hidden as an assumption.

### Phase 2: Implement

#### Task 2.1: Implement both family contracts through host `eval` [L] → owner: coder (runner/evaluation)
Target/change surface: Eval command, family loading/validation, semantic adapters and shared result integration around `runner/eval_api.py` and engine surfaces found in 1.1; current host invoke. Exact files follow spec.
Type: Backend
Nature: Feature
Applicable skill: software-engineering, python-how-to, python-testing, product-acceptance
Implements: [ARD-001](../architecture/eval-format-ownership/design/ard-001-runner-owned-input-and-output-contracts.md) and Task 1.2 spec
Depends on: 1.2.
Acceptance criteria:
- [ ] One public `eval` validates both families; invalid/ambiguous input is rejected before any invocation.
- [ ] Agent/runtime execution mode and applicable assertions survive without reinterpretation as skill expectations.
- [ ] Skill expectations and specified negative/trap semantics survive; ablation preserves both sides and skill-owned comparison through real paired lifecycle.
- [ ] Each actual execution uses existing host `invoke`; image gains no suite orchestration, retries, planning, artifact writing or rendering.
- [ ] Local valid/invalid contract tests and vertical proof use upstream-created input and real evaluation-produced verified persistence to show identity/meaning.

#### Task 2.2: Implement four output contracts from verified results [L] → owner: coder (runner/output)
Target/change surface: Output dispatch/renderers, result access and artifact-verification integration; exact files follow spec. Avoid family-adapter/CLI edits except agreed interface.
Type: Backend
Nature: Feature
Applicable skill: software-engineering, python-how-to, python-testing, accessibility-implementation
Implements: [ARD-001](../architecture/eval-format-ownership/design/ard-001-runner-owned-input-and-output-contracts.md) and Task 1.2 spec
Depends on: 1.2; shared result contract from 2.1 (renderer module work may start after 1.2; public wiring waits for 2.1).
Acceptance criteria:
- [ ] JSON/YAML/Markdown/HTML are selectable through public `eval` and conform to specified contracts.
- [ ] Each reflects same verified durable result including family/case/run identity, classification, attempts and family/paired outcomes; rendering cannot rerun evaluation or alter verdicts.
- [ ] Local parity evidence starts with one completed evaluation whose durable result has passed verification, obtains JSON, YAML, Markdown, and HTML separately through the public interface from that same result, and compares each representation against the source result. It does not rely on four separate evaluation runs or require simultaneous emissions.
- [ ] Existing v1 validation/persistence/integrity meaning is preserved; corrupt state cannot be reported as successful output.
- [ ] Output failure is not success; Markdown/HTML meet accessibility criteria and any interactive HTML is keyboard-operable.
- [ ] Local parity/conformance tests compare against verified records and cover corrupt/invalid source and output failure.

### Phase 3: Integrate and prove

#### Task 3.1: Prove assembled paths [L] → owner: integrator (runner/product acceptance)
Target/change surface: Public built-in eval paths, verified run records, renderers, ARS and evidence. Documentation reconciliation is the separate `docs-repair` task in the current Loom Plan.
Type: Testing
Nature: Enhancement
Applicable skill: product-acceptance
Implements: [ARD-001](../architecture/eval-format-ownership/design/ard-001-runner-owned-input-and-output-contracts.md) and Task 1.2 spec
Depends on: 2.1 and 2.2.
Acceptance criteria:
- [ ] Reconcile old profile-owned discovery/normalization and input-JSON exclusion with new ownership; retain accurate invocation/evidence boundaries; do not rewrite requirements.
- [ ] Usage docs describe one interface, both families/four formats, `eval` vs one-call `invoke`, and only authorized compatibility/report claims.
- [ ] Execute E2E-001/002 through actual interface using real product-owned loaders, evaluators, invoke adapter/image, verifier and renderers; record external substitutions/limits.
- [ ] For each scenario, run evaluation once to completion and verify its durable result; then obtain each of JSON, YAML, Markdown, and HTML separately through the public interface from that same result (for example, by selecting/rendering the persisted result). Compare every representation against that source result. Do not substitute separate evaluation runs as parity evidence; simultaneous emissions are not required.
- [ ] Each proves provenance and invalid-input no-invocation; corruption/render failure cannot claim success.
- [ ] Check generated Markdown/HTML against accessibility criteria and evidence one-invocation boundary. Record entry/path, build/config, action, outcome, gaps and evidence; no unexecuted PASS.

#### Task 3.2: Validate actual human-readable output [M] → owner: designer
Target/change surface: Generated Markdown and HTML outputs against ARS-001's structure, order, textual status and interaction baseline. Read-only validation; no report redesign or WCAG-level claim.
Type: Testing
Nature: Assessment
Applicable skill: design-validation
Depends on: 3.1.

#### Task 3.3: Independent contract/release-readiness review [M] → owner: reviewer
Target/change surface: Final diff, requirements/ARD/spec, inventory, local/vertical/E2E evidence, reconciled docs. Read-only review; findings routed to implementation owner.
Type: Testing
Nature: Maintenance
Applicable skill: product-acceptance, design-validation
Implements: [ARD-001](../architecture/eval-format-ownership/design/ard-001-runner-owned-input-and-output-contracts.md)
Depends on: `assembled-e2e`, `design-check`, `renderer-heading-fix`, `egress-history-audit`, `docs-repair`, `html-browser-check`, and `cleanup-network` in the current Loom Plan.
Acceptance criteria:
- [ ] Independently trace each BR/OC and ARD invariant to implementation/evidence, probing semantic loss, output drift, false success, v1 regressions and image-boundary violations.
- [ ] Review every output path for conformance and accessibility; unit tests are not accepted as E2E proof.
- [ ] Record each finding with owner and disposition; implementation owners resolve findings and rerun affected checks, while any proposed acceptance of a blocking finding is explicitly decided by the relevant authority. No ship-ready claim while mandatory guarantees remain unproven.

#### Task 3.4: Final critic gate [M] → owner: critic
Target/change surface: Final implementation diff, approved requirements/ARD/specification, Task 3.1 E2E evidence, Task 3.2 review and finding dispositions. Read-only adversarial plan/implementation/evidence review.
Type: Testing
Nature: Maintenance
Applicable skill: product-acceptance, risk-driven-planning
Implements: [ARD-001](../architecture/eval-format-ownership/design/ard-001-runner-owned-input-and-output-contracts.md)
Depends on: Task 3.3 and an external prerequisite that all blocking reviewer findings have verified resolution or explicit authority acceptance; the critic gate does not own implementation fixes or acceptance decisions.
Acceptance criteria:
- [ ] Confirm reviewer findings are resolved with affected evidence rerun, or explicitly accepted by the relevant authority; unresolved blocking findings return to implementation/authority and stop the gate.
- [ ] Adversarially check that each family’s four representations come from one completed, verified evaluation result via the public interface, with each compared against that same source result; separate evaluation runs do not count as parity proof.
- [ ] Confirm all mandatory BR/OC and ARD guarantees have actual implementation and evidence, and no unresolved blocker or unsupported ship-ready claim remains.

## Dependency and ownership graph

The table and detailed legacy task text below retain some of the original local plan's numbering. For live scheduling, use the current Loom Plan revision 5 and its task IDs stated above; documentation repair, browser inspection, and network cleanup are separate remediation tasks, not part of assembled E2E proof.

```text
1.1 inventory [researcher] -> 1.2 specification [architect/design-spec owner]
                                  |-> 2.1 input families/host eval [runner coder] --\
                                   |-> 2.2 output formats [output coder] -----------+-> 3.1 E2E proof [integrator] -> 3.2 human-view validation [designer]
                                        (public wiring depends on 2.1)                  |-> 3.5 docs reconciliation [integrator]
                                                                                        +-> independent-review [reviewer]
                                                                                             -> final-critic [critic]
```

| Task | Owner | Read surfaces | Write surfaces | Dependencies |
| --- | --- | --- | --- | --- |
| 1.1 | Researcher | Loom sources, runner API/artifacts/CLI, old docs | Inventory only | None |
| 1.2 | Architect/design-spec owner | Requirements, ARD, inventory, user decisions | Contract spec | 1.1; applicable user decisions |
| 2.1 | Runner coder | Spec, eval/engine/invoke | Family loaders/adapters and integration | 1.2 |
| 2.2 | Output coder | Spec, result contract, verifier | Dispatch/renderers/tests | 1.2; 2.1 for public wiring |
| 3.1 | Integrator | Implementation, spec/evidence | Assembled E2E evidence | 2.1, 2.2 |
| 3.2 | Designer | Generated Markdown/HTML, ARS-001 | Human-view validation report | 3.1 |
| `independent-review` | Reviewer | Diff, docs and evidence | Independent review findings | E2E, design check, renderer fix, egress audit, docs repair, browser check, network cleanup |
| `final-critic` | Critic | Final diff, requirements/ARD/spec, E2E evidence, review dispositions | Final gate findings only | `independent-review` plus prerequisite: all blocking findings resolved or explicitly accepted |
| `docs-repair` | Documentation owner | Implementation, docs, ARD/spec | Reconciled plan and required metadata | Remediation; independent review depends on it |

No shared mutable test state is specified in inspected sources [unverified]. Disclose shared artifact dirs, provider accounts, ports or generated surfaces before parallelizing. Tasks 2.1/2.2 overlap only with stable interfaces and disjoint writes; otherwise serialize CLI/schema integration. Live task identities and dependencies are those in Loom Plan revision 5.

## Execution waves

1. The current rev5 graph's `assembled-e2e` has provider-free same-run evidence for both families; `renderer-heading-fix` and static `design-check` are reported complete.
2. Remediation checks are complete: BR/OC frontmatter validation passed; offline browser inspection passed with minor horizontal overflow in skill stdout (content remains and is not clipped); and the temporary internal Podman network was removed. `egress-history-audit` established that two earlier GHCR attempts transferred image blobs/config/manifest, while layer retention remains unknown and user acceptance of that exception is pending.
3. `independent-review` and its findings disposition are complete; the final critic gate is also complete. The critic blocks shipping pending the user-owned decision on the historical GHCR transfer.
4. Shipping remains blocked pending that user-owned transfer decision. No whole-workflow no-egress claim is supported.

## Open questions

| Question | Owner | Blocks |
| --- | --- | --- |
| Are historical built-in input aliases/migration or external v1 artifact consumers supported? | User/product owner | Blocks only those compatibility claims; existing `--profile` behavior, including transport flexibility, remains preserved and is not a migration decision. |
| Are v1 run/artifact/paired JSON envelopes externally consumed, and what compatibility/migration applies to new public JSON? | User/product owner, informed by 1.1 | Blocks changing/versioning envelopes or making compatibility claims. Until resolved preserve v1 integrity/schema and do not reinterpret fields. |
| Is a polished report beyond accessible Markdown/HTML baseline required; for whom and what must it communicate? | User/product owner | Blocks richer report only; baseline formats proceed without report promise. |

Specialist-owned source-feature boundaries, fields, semantic mapping, interface grammar and accessibility verification belong to Task 1.2. If a detail drops a material source capability, changes user meaning, or conflicts with compatibility, return to user/architect authority instead of assuming.

## Plan checks

1. **Authorities:** Requirements, approved ARD, handoff, current code/docs and designer guidance are reconciled; architecture log caveat recorded as nonblocking, not presumed defective.
2. **Obligations:** BRs/OCs, semantics, accessibility, JSON integrity and invocation boundary all have owners, satisfiers, proof and disposition; compatibility/report are explicitly user-owned.
3. **Decisions:** Only user compatibility/migration/report matters remain; specialist details assigned to Task 1.2 with escalation for material scope changes.
4. **Foundations:** Inventory → spec → implementation → composition proof → independent review/findings disposition → final critic gate.
5. **Graph:** The current rev5 task identities and dependencies are authoritative; this legacy local task list is not a count or schedule for that graph.
6. **Mechanisms:** Adapters, verified record, selectable renderers, accessibility, one-call image boundary trace to BR/OC and ARD-001.
7. **Repo claims:** Current implementation/evidence claims remain limited to inspected files and recorded artifacts; external consumers remain unknown unless separately evidenced.
8. **Session fit:** Inventory, specification, family integration, output integration, composition/docs and review are bounded natural scopes; implementation splits at semantic seam, not by file.
9. **Vertical proofs:** Task 2.1 proves input-to-runner durable state; 2.2 proves verified-state-to-format and integrity rejection.
10. **E2E:** Two discriminating scenarios cover both distinct families, same interface, ablation, four formats, failure paths and actual accessible output using real product-owned stages. Within each scenario, one completed and verified evaluation supplies all four separately selected representations, each compared against that same source result.
11. **No unsupported pass/n/a:** Provider-free E2E, renderer correction, static design inspection, offline browser inspection, BR/OC frontmatter validation, and temporary-network cleanup have evidence; independent review and final critic are complete. Two earlier GHCR attempts transferred image blobs/config/manifest; layer retention is unknown and the user-owned decision on this historical transfer is pending, so shipping remains blocked. No whole-workflow no-egress claim is supported.
