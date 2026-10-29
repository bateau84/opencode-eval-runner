---
type: plan
title: Runner-owned evaluation contracts — PR #89 completion
description: Close source-backed contract, CI, report, documentation, and product-proof gaps before deciding whether PR #89 is mergeable.
tags: [active, plan:runner-evaluation-format-contracts, evaluation, contracts, pr-89]
---

## Goal

Complete and verify the unfinished evaluation-format branch and PR #89 against the accepted runner-owned input/output contracts. Do not implement work while planning, claim mergeability before the current GitHub blocker is known, or reinterpret accepted requirements to fit the current code.

The target is both input families through the existing public `eval` interface; verified JSON/YAML/Markdown/HTML projections; preserved agent/runtime and skill-ablation semantics; readable attributed reports; and trustworthy CI and assembled-product evidence. Existing `--profile` behavior and the one-invocation image boundary remain unchanged.

**Status basis (2026-10-29):** branch `feat/evaluation-format-contracts`, HEAD `15e5cff` at the start of Task 3.1, base `1262ac8c2eebbd10af572e3e3560318f6113233b`, PR #89. The preceding implementation commits include `0c29f85` (combined skill inputs/reports), `c62295b` (combined-result projection), and `15e5cff` (readable attributed reports). Historical test runs and prior `/tmp` artifacts do not prove current product-level OCI/browser behavior.

**Execution update (2026-10-29):** Tasks 1.2 and 2.1 have implementation and local verification commits on this branch (`660da87`, `0e04355`). The existing unittest suite and the three targeted pytest modules pass locally. Task 1.2 remains open until a hosted GitHub run visibly records the pytest modules; `gh pr checks 89` reported no checks on the branch at this observation. Task 2.1's local evidence-readiness and judge-gate criteria are verified; real OCI composition remains Task 3.2.

**Task 2.2 update (2026-10-29):** Result projection changes and focused local verification are complete in this branch. V2 case provenance remains in the v2 input/case projection and artifact metadata, the closed `SkillResult.case_identity` shape is unchanged, combined Markdown/HTML display the verified run timestamp, and undeclared trap outcome fields are null. Strict conformance tests cover combined v2 provenance and the existing v1 projection path. Real invocation/persistence/report composition and human report assessment remain open under Tasks 3.2–3.3.

**Task 2.3 update (2026-10-29):** Readable attributed Markdown/HTML rendering is implemented at `15e5cff`; focused local renderer tests and projection tests cover the changed semantics. This is not evidence of the approved multi-skill/five-iteration product report in a browser. Real OCI composition and human/browser report assessment remain open under Tasks 3.2–3.3.

**Task 3.1 update (2026-10-29):** The obsolete requirements-index conflict is reconciled: ARD-001/ARS-001 specify repeated explicit skill inputs, and implementation commit `0c29f85` supports them. The user's acceptance of the historical GHCR transfer remains a bounded non-blocking exception, not a no-egress claim. Requirements are unchanged. Hosted CI evidence for Task 1.2 is now recorded below; product proof Task 3.2 remains unproven, Task 3.3 and independent review remain open, and the current GitHub `BLOCKED` state still lacks an authoritative explanation.

**Task 3.2 execution update (2026-10-29, HEAD `23a8a4fedb79f7b0633af911a5b9006dde64b4bd`): UNPROVEN.** Feasibility inspection found the compatible OpenCode 2.0.23 invoke image locally (`localhost/eval-contract-opencode:guarded`, immutable image ID `sha256:0940e9ac543098bfa51dda81cce643ed3366df1ab8a4e90bf5fcd8601c2e5e39`; expected version and adapter labels match). However, no approved provider-free local fixture/provider route is configured: the OpenCode configuration available to this process declares no providers/models/base URLs. Running the eval would therefore require selecting and potentially spending against an unapproved live provider. Per scope, no invocation was attempted. No run IDs, verified persisted results, JSON/YAML/Markdown/HTML same-run outputs, or actual HTML/Markdown report paths exist from this attempt. Neither scenario can be claimed PASS; actual combined reports and browser/design validation remain unproven. See [Task 3.2 feasibility and evidence record](../ephemeral-reports/product-acceptance/pr89-task32.md). This limitation does not reopen the accepted historical GHCR transfer boundary.

**Read-only delivery observations (2026-10-29):** GitHub run `40935434652` completed successfully for current HEAD `23a8a4fedb79f7b0633af911a5b9006dde64b4bd`; test job `Python checks` visibly collected 46 pytest cases and completed `46 passed in 2.77s`, including `tests/test_eval_input.py`, `tests/test_eval_assertions.py`, and `tests/test_eval_builtin_cli.py`. This satisfies hosted execution evidence for Task 1.2. `gh pr view 89` reports base `main` (`1262ac8c2eebbd10af572e3e3560318f6113233b`), merge state `BLOCKED`, `mergeable: MERGEABLE`, no review decision/reviews/requests, and both check runs successful. Branch-protection API returned HTTP 404 “Branch not protected.” The precise reason for GitHub's `BLOCKED` state remains unavailable from these observations; do not infer a blocker or claim ready. Task 1.1/final readiness remains unresolved pending GitHub's authoritative reason.

After the documentation-only evidence commit was pushed, `gh pr view 89` reported PR head `82fc536794ab284bce939822a86502854d65d5b6`, still `BLOCKED` and `MERGEABLE`, with no review decision and no checks yet listed for that new head. The successful hosted checks above are for parent source HEAD `23a8a4f`; they do not constitute checks on the pushed documentation commit. No merge was performed.

## Plain-language task map

> Reader aid only. Task details, acceptance criteria, and dependencies govern if this ever differs.

### Phase 1: Establish actual blockers and make CI exercise the tests

| Task | What this actually does |
| ---- | ------------------------ |
| 1.1 | Finds and records the exact current reason GitHub blocks merging PR #89, without guessing from stale check summaries. |
| 1.2 | Ensures the CI test job discovers and runs the pytest modules that currently hold evaluation-contract coverage. |

### Phase 2: Restore implementation conformance

| Task | What this actually does |
| ---- | ------------------------ |
| 2.1 | Makes runtime evidence readiness reflect the fields actually required by each assertion, preserving valid runtime evaluations. |
| 2.2 | Aligns combined-result identity, provenance, timestamp, and undeclared-trap values with the closed output contract. |
| 2.3 | Makes Markdown and HTML explain outcomes and per-iteration ablation results instead of presenting only field trees. |

### Phase 3: Reconcile documents and prove the assembled product

| Task | What this actually does |
| ---- | ------------------------ |
| 3.1 | Removes stale planning and requirements-index statements without weakening accepted requirements or mislabeling planned work as done. |
| 3.2 | Runs real agent/runtime and combined-skill evaluations and compares every format against the verified runs. |
| 3.3 | Checks the actual generated Markdown and HTML against the approved readable-report experience. |

### Phase 4: Close review and merge readiness

| Task | What this actually does |
| ---- | ------------------------ |
| 4.1 | Independently checks fixes and evidence against all accepted guarantees and the review findings. |
| 4.2 | Rechecks GitHub's current merge conditions and records a supported ready/not-ready disposition for PR #89. |

### Important task relationships

- Task 2.2 precedes 2.3 because report summaries must consume the corrected, contract-conforming result projection; the shared `runner/eval_output.py` surface also makes this a deliberate serialization boundary.
- Task 3.2 depends on implementation and documentation work. It must use real product-owned runner, invocation, persistence/verifier, and renderer paths; unit tests or injected state do not prove the user outcome.
- Task 3.3 depends on the actual reports produced by 3.2; it is separate from E2E execution because design validation has an independent owner and human-centered evidence boundary.
- Task 4.2 is a merge-readiness check, not an assumption that the blocker found in 1.1 is caused by these code findings.

### Whole plan in one sentence

Identify the actual merge blocker → repair CI and contract gaps → reconcile stale documentation → prove both real evaluation journeys and readable outputs → independently review → report current merge readiness.

## Assumptions

- **[ASSUMPTION]** The approved requirement bundle, ARD-001, ARS-001, and combined-report design below remain authority; the findings are to be corrected against them, not used to revise them.
- **[ASSUMPTION]** Existing CI policy permits adding the pinned pytest execution to the current test job; if CI ownership or policy says otherwise, task 1.2 returns that decision to the workflow owner rather than silently omitting tests.
- **[CONCERN]** The PR's actual merge-block reason is unknown. A green set of visible checks does not explain a `BLOCKED` merge state; task 1.1 is required before making a merge-readiness claim.

## Out of scope

- Implementing code or changing the PR during this planning assignment.
- New product capabilities, assertion semantics, output fields, aggregation, or compatibility promises.
- Reopening the user-accepted historical GHCR transfer as a blocker. It remains a known historical exception, not evidence of no egress and not part of this remediation.
- Claiming a live-provider compatibility, no-network-egress, WCAG conformance-level, or merge-readiness result without corresponding evidence.

## Sources

| Source | Status and use |
| --- | --- |
| [Requirements index](../requirements/eval-format-ownership/index.md), [BR-001](../requirements/eval-format-ownership/br-001-accept-both-input-contract-families.md), [BR-002](../requirements/eval-format-ownership/br-002-own-output-contracts-across-named-formats.md), [BR-003](../requirements/eval-format-ownership/br-003-provide-one-user-facing-evaluation-interface.md), [BR-004](../requirements/eval-format-ownership/br-004-present-readable-markdown-and-html-results.md), [BR-005](../requirements/eval-format-ownership/br-005-evaluate-multiple-skill-inputs-together.md), [OC-001](../requirements/eval-format-ownership/oc-001-evaluation-case-input-conformance.md), [OC-002](../requirements/eval-format-ownership/oc-002-evaluation-output-conformance.md), [QS-001](../requirements/eval-format-ownership/qs-001-readable-multi-skill-five-iteration-reports.md) | Approved product authority. Preserve both distinct families, one interface, all four representations, readable outcome narratives, combined skill attribution, and separate per-skill comparisons. The requirements index contains a stale statement that the multi-input architecture is still unresolved; reconcile its factual status without changing requirement meaning. |
| [ARD-001](../architecture/eval-format-ownership/design/ard-001-runner-owned-input-and-output-contracts.md) | Proposed architecture governing host-owned family adapters, verified persisted results, existing artifact integrity, invocation boundary, and combined-input provenance. |
| [ARS-001](../architecture/eval-format-ownership/specifications/ars-001-runner-eval-contract.md) | Proposed implementation contract. Relevant exact rules include assertion-scoped runtime readiness (§117); closed result fields and undeclared trap nulls (§§356–412); v2 provenance fields at the `RunResultV2.input.inputs[]` / `CaseResultV2` projection, not inside closed `SkillResult.case_identity` (§§414–441); `run.created_at` (§§247–267); and output eligibility (§321). |
| [Combined skill report baseline](../design/eval-format-ownership/multiskill-readable-report-baseline.md) | User-approved design authority for status-first narrative, skill → case → iteration structure, per-iteration baseline/candidate comparisons, complete same-report evidence, and narrow-viewport/keyboard checks. |
| Prior version of this plan | It recorded implementer-reported 297 pytest passes plus 123 subtests and prior provider-free runs/browser checks. Those are historical claims, not rerun here, and do not establish hosted pytest coverage or the real-OCI evidence missing for current HEAD. The prior plan also recorded two GHCR pull attempts transferring nine blobs plus config/manifest; the user accepted that known historical egress as non-blocking, while local layer retention and byte volume remained unknown. |
| [PR #89](https://github.com/bateau84/opencode-eval-runner/pull/89), reviewed diff at the stated HEAD, and reviewer finding record | PR status is unresolved; code-backed findings and evidence limits are carried forward. The review was not genuinely blind because earlier verdict excerpts were present in automatic context. |
| Current repository evidence | `runner/eval_evidence.py`, `runner/eval_builtin.py`, `runner/eval_output.py`, `.github/workflows/ci.yml`, and the test suite were reviewed for the bounded findings. Exact reviewer line references and reproductions are in the review handoff; no implementation was changed during this planning task. |

## Obligation map

| Obligation | Architectural satisfier | Owner / task | Verification path | Disposition |
| --- | --- | --- | --- | --- |
| Runtime readiness is scoped to fields needed by the selected assertion; a complete canonical runtime capture is not rejected for unrelated missing fields. | ARS-001 §117; ARD-001 host family adapter boundary | Runner implementation, 2.1 | Focused regressions for complete canonical runtime evidence and each assertion's required fields; real agent/runtime E2E in 3.2 demonstrates a valid run reaches the intended judge gate. | Implement |
| CI executes all evaluation tests, including the three pytest modules currently missed by unittest discovery. | CI/test contract is repository-owned; no product architecture change | CI owner, 1.2 | CI job evidence lists these modules as executed and fails when a regression is introduced; preserve deterministic unit tests. | Implement |
| Closed `SkillResult.case_identity` stays closed; combined input provenance is represented only in the agreed v2 projection locations. | ARS-001 §§356–441; ARD-001 provenance invariant | Runner output owner, 2.2 | Schema/conformance regressions assert exact field ownership, strict rejection of unknown fields, and source occurrence attribution after verified result round trip. | Implement |
| Run creation timestamp is present in combined human-facing outputs as required by the result contract. | ARS-001 `RunResult.created_at` §§247–267 | Runner output owner, 2.2 | Projection and renderer tests check timestamp against the same verified run; E2E report check in 3.2. | Implement |
| Undeclared trap has the contract's unavailable/not-applicable null outcome, not a fabricated observed-false/evidence value. | ARS-001 §§412; family semantics remain as specified | Runner output owner, 2.2 | Local input-to-result and strict output conformance tests distinguish undeclared trap from declared-but-not-observed trap. | Implement |
| Markdown/HTML provide readable run and per-case outcomes, attribution, iteration status and comparison, while retaining full captured detail. | ARD-001; ARS-001 §28; BR-004/BR-005; QS-001; approved report baseline | Renderer owner, 2.3 | Renderer contract tests plus generated report review against actual multi-skill/five-iteration verified run and design checks in 3.2. | Implement |
| Both input families, one interface, output parity, and skill-only paired ablation retain their accepted semantics. | ARD-001 and ARS-001 | Runner + integrator, 2.1–3.2 | Local contract/vertical tests and the two E2E scenarios below; every output derived from the same verified run. | Implement |
| Stale plan and requirements-index status is corrected; requirements and existing `--profile` promise are not rewritten. | Documentation policy; approved requirements and architecture | Documentation owner, 3.1 | Link/metadata validation; read-back confirms no accepted contract changed and planned vs executed evidence is distinguished. | Implement |
| PR #89's exact current merge blocker is identified and final merge state is truthfully reported. | External GitHub repository state | Integrator, 1.1 and 4.2 | Capture current required-check/review/branch-protection/mergeability evidence and the GitHub reason; recheck after fixes. | Implement |
| Prior review's real OCI, combined five-iteration, and current-browser/report evidence gaps are closed. | ARD-001; ARS-001; report baseline | Integrator and design reviewer, 3.2–4.1 | Real product-owned paths and produced-state provenance; record provider/image/config, artifacts, outcomes, and evidence locations. | Implement |
| Historical GHCR transfer / local retention uncertainty | No new architectural satisfier required; user accepted the known transfer as a non-blocking exception | User disposition already recorded in source plan history | Do not claim no transfer or whole-workflow no-egress; carry the known caveat only. | Out of scope by agreement |

## Risk boundaries

- **Merge-state uncertainty (blocks readiness claim only):** GitHub's precise blocked reason could be branch protection, a required check/review, or another condition. Task 1.1 records current evidence and narrows the relevant follow-up; it does not delay source-backed fixes.
- **Input-to-judge semantic boundary:** Current readiness logic can reject a valid canonical capture before the judge. Fix and test this boundary before treating unit-test status as evidence of the expected agent/runtime outcome.
- **Closed result schema boundary:** Misplacing source provenance inside a closed family payload can break strict conformance and round trips. Validate projection ownership, persistence verification, and rendering against ARS-001, not merely permissive serialization.
- **Human-readable output boundary:** A renderer can be machine-conforming yet fail BR-004/QS-001. Validate against actual produced multi-skill, five-iteration results; placeholders or injected result objects are not sufficient.
- **CI coverage boundary:** Local pytest green is not CI coverage while the workflow runs only unittest discovery. Confirm executed modules in the hosted run after changing workflow behavior.
- **Run availability:** The compatible local OCI image is present, but this environment has no configured provider-free OpenCode route. Actual OCI/OpenCode runs were not attempted absent authority for live provider use. Record both scenarios UNPROVEN; do not substitute mocks for product-owned stages or claim completion.
- **Review independence:** The prior assessment was evidence-backed but not blind. Task 4.1 must independently review the final diff and artifacts and disclose that lineage; its status must not imply an independent clean-room first assessment.

## End-to-end proof

The smallest discriminating set is two scenarios: one validates agent/runtime assertion/readiness/judging semantics; the other covers combined skill provenance, paired comparisons, five-iteration report readability and all format projections. They share infrastructure but exercise materially different family semantics.

### E2E-001: Agent/runtime canonical capture through verified result

- Outcome: A valid agent/runtime suite completes through `eval`; assertion-scoped runtime evidence readiness permits the prescribed judge decision, and its output represents the verified result without semantic loss.
- Entry point: Public `eval` command.
- Product-owned path: Real suite input → host validation/agent-runtime adapter → real OpenCode invocation adapter and OCI image → runtime evidence and assertion checks → judge when the specified readiness/gate conditions hold → durable artifact and verifier → selected output renderer.
- External substitutions: No substitution for runner, adapter, OCI image, evidence, verifier, or renderer. A genuine OpenCode-configured model/provider sandbox may replace paid/live provider service only if it preserves the needed request/response semantics; identify that limit. Do not substitute synthetic runtime evidence for evidence produced by the invocation.
- State provenance: Submitted real suite creates the case; actual OCI/OpenCode invocation produces target output and canonical runtime evidence; runner produces checks, judge result, verified artifact; formats are derived from that artifact in this run.
- Externally meaningful assertion: A canonical complete capture accepted under assertion-scoped readiness reaches the expected judge path; emitted classification and source assertions agree with the verified run; invalid inputs remain pre-invocation failures.
- Failure/recovery: Assert no false pass for incomplete required evidence or target failure, and no judge where the contract says to skip; no new retry/recovery promise.
- Human design check: Required for generated Markdown/HTML; executes in Task 3.3.
- Executes in: Task 3.2.

### E2E-002: Combined skill run through attributed five-iteration reports

- Outcome: Multiple explicitly supplied skill inputs produce a single verified run with per-skill/per-case/per-iteration ablation results and readable Markdown/HTML; JSON/YAML/Markdown/HTML all represent that same run.
- Entry point: Public built-in `eval` command, followed by its public persisted-run render mode for each selected format.
- Product-owned path: Real explicit skill input files and installed skills → whole-set validation and source provenance → actual baseline/candidate target and judge OCI/OpenCode phases → paired comparisons and durable verified records → same-run JSON, YAML, Markdown, and HTML projections.
- External substitutions: No mock for any product-owned component. A genuine external OpenCode provider may use an approved sandbox with documented limits; OCI invocation/image and runner product path stay real.
- State provenance: The real submitted input bytes and occurrence order establish every source identity/digest; actual run creates both sides, comparisons, attempts and evidence; all four separately requested representations are rendered from the same verified persisted run. No hand-injected case, comparison, evidence, or results.
- Externally meaningful assertion: Summary identifies the run outcome; each skill/case and all five iterations are separately findable with that iteration's status, baseline/candidate comparison, attempts and captured evidence. Each format matches the verified result, source attribution is retained, no cross-skill aggregate is invented, and output schema values obey ARS-001.
- Failure/recovery: Include duplicate composite identity or invalid unselected child rejection before invocation, and ensure corrupt result/output failure cannot claim successful output. No new retry promise.
- Human design check: Required; inspect actual Markdown and HTML against the approved structure, order, complete same-report detail, status text, keyboard navigation/disclosures, and 320 CSS-pixel / 200% zoom reflow requirements in Task 3.3. This is not a blanket WCAG conformance claim.
- Executes in: Task 3.2.

## Phases

### Phase 1: Establish actual blockers and CI coverage

#### Task 1.1: Identify PR #89's current merge blocker [S] → owner: integrator

Target/change surface: PR #89 current GitHub status, required checks/reviews/branch protection and mergeability; no source edits.
Type: Research
Nature: Research
Execution fit: One bounded read-only observation. It resolves a material readiness uncertainty without delaying independent source fixes; retry cost is low and proof is the recorded current reason, not an inference from stale CI text.
Applicable skill: risk-driven-planning
Implements: [ARD-001](../architecture/eval-format-ownership/design/ard-001-runner-owned-input-and-output-contracts.md)
Acceptance criteria:

- [ ] Record timestamp, PR/base/head, current merge state, exact blocking reason(s), required check/review conditions, and links or retrievable evidence.
- [ ] Distinguish GitHub's actual merge blocker from the source-backed code findings in this plan; if the blocker is unavailable/ambiguous, leave merge readiness unresolved and state what evidence is missing.
- [ ] Do not treat stale PR text or currently green checks as proof of the blocker or its resolution.

#### Task 1.2: Restore evaluation pytest coverage in CI [S] → owner: CI/workflow maintainer

Target/change surface: `.github/workflows/ci.yml`, pinned test dependencies, and CI test invocation; exact existing files verified in current diff.
Type: Infrastructure
Nature: Bug
Execution fit: One focused workflow/test-discovery change with a discrete hosted verification boundary. It does not require changes to evaluation semantics; any workflow-policy uncertainty returns to its owner.
Applicable skill: github-workflow, python-testing
Implements: [ARS-001](../architecture/eval-format-ownership/specifications/ars-001-runner-eval-contract.md)
Acceptance criteria:

- [x] CI executes the evaluation pytest modules `test_eval_input`, `test_eval_assertions`, and `test_eval_builtin_cli` that unittest discovery currently omits.
- [x] Hosted run `40935434652` visibly records pytest discovery and results for those modules; the Python checks collected 46 cases and finished `46 passed in 2.77s`.
- [x] Existing test job and full relevant CI run completed successfully; dependencies remain pinned/declared according to repository policy.

### Phase 2: Restore implementation conformance

#### Task 2.1: Fix assertion-scoped runtime evidence readiness [M] → owner: runner evaluation maintainer

Target/change surface: `runner/eval_evidence.py`, `runner/eval_builtin.py`, focused evaluation tests; reviewer findings cite `eval_evidence.py:245–258, 280–281` and builtin judge gating.
Type: Backend
Nature: Bug
Execution fit: One semantic boundary—from canonical evidence through requested readiness to judge eligibility—with focused local regressions. Keeping classifier and gate together avoids separately “fixing” a check that still prevents the required judge path; live OCI composition remains a later independent proof.
Applicable skill: software-engineering, python-how-to, python-testing, test-driven-development
Implements: [ARS-001](../architecture/eval-format-ownership/specifications/ars-001-runner-eval-contract.md) §117 and [ARD-001](../architecture/eval-format-ownership/design/ard-001-runner-owned-input-and-output-contracts.md)
Acceptance criteria:

- [x] Evidence readiness for scalar outcome and start-sequence assertions checks the fields those assertions require, not unrelated envelope fields.
- [x] A complete canonical nonempty runtime capture supporting the requested assertions is accepted and reaches the ARS-001-prescribed judge gate; required-but-missing evidence remains non-evidence.
- [x] Tests distinguish evidence readiness from assertion outcome and cover the relevant evidence boundary/field failure cases without replacing real E2E evidence.
- [x] Existing classification precedence and “judge skipped on non-pass deterministic checks” behavior remain contract-conforming.

#### Task 2.2: Align result projection and trap semantics to the closed contract [M] → owner: runner output maintainer

Target/change surface: `runner/eval_builtin.py`, `runner/eval_output.py`, result/output tests; reviewer findings cite `eval_builtin.py:940, 956–958` and `eval_output.py:286–288, 1104–1234`.
Type: Backend
Nature: Bug
Execution fit: These are coupled contract-model defects at one verified-result projection boundary: location of v2 provenance, preservation of `run.created_at`, and null semantics for undeclared trap. Local conformance tests can prove them before the separate readable-renderer work. The subsequent renderer task shares `eval_output.py` and must follow this task to avoid write collisions.
Applicable skill: software-engineering, python-how-to, python-testing, python-type-checking
Implements: [ARS-001](../architecture/eval-format-ownership/specifications/ars-001-runner-eval-contract.md) §§247–267, 356–412, 414–441 and [ARD-001](../architecture/eval-format-ownership/design/ard-001-runner-owned-input-and-output-contracts.md)
Acceptance criteria:

- [x] `SkillResult.case_identity` emits only the closed family fields; input occurrence/path/digest remain in their specified v2 input/projection fields and cases retain the correct source-occurrence attribution.
- [x] Combined human-readable reports include the `created_at` value from the same run result.
- [x] An undeclared trap is represented as not applicable/null as specified; declared-but-not-observed remains distinguishable and retains its evidence semantics.
- [x] Local strict-schema and verified-result tests cover valid v1 and v2 outputs, reject unknown keys, and prove source provenance is not lost or moved into a closed payload.
- [x] No durable v1 envelope, hash/integrity behavior, or existing profile behavior changes.

#### Task 2.3: Render readable attributed Markdown and HTML outcomes [M] → owner: runner report maintainer

Target/change surface: `runner/eval_output.py` Markdown/HTML renderer and renderer tests; actual report must follow [combined report baseline](../design/eval-format-ownership/multiskill-readable-report-baseline.md).
Type: Backend
Nature: Enhancement
Execution fit: One presentation outcome and verification boundary: turn verified result facts into narrative summaries and nested attributed details. It follows 2.2 because projection facts must first be correct; it remains separate from 2.2 because readable presentation can be independently useful and must be assessed against human-facing design, not just schema tests.
Applicable skill: software-engineering, python-how-to, python-testing, accessibility-implementation
Implements: [BR-004](../requirements/eval-format-ownership/br-004-present-readable-markdown-and-html-results.md), [BR-005](../requirements/eval-format-ownership/br-005-evaluate-multiple-skill-inputs-together.md), [QS-001](../requirements/eval-format-ownership/qs-001-readable-multi-skill-five-iteration-reports.md), [ARS-001](../architecture/eval-format-ownership/specifications/ars-001-runner-eval-contract.md), and [report baseline](../design/eval-format-ownership/multiskill-readable-report-baseline.md)
Depends on: 2.2.
Acceptance criteria:

- [x] Markdown and HTML lead with readable run outcome and then attribute skill → case → iteration; each applicable iteration includes status and its own baseline/candidate comparison, attempts, checks and evidence summary.
- [x] Human readers do not need to decode a raw field/value tree to identify outcomes; full captured answers/evidence and their redaction/truncation meaning remain in the same report.
- [x] Candidate absolute classification remains distinct from comparison decision and skill-value label; no per-skill or cross-skill aggregates are added.
- [x] Existing output escaping, semantic order, non-color status and keyboard-operable native interactions remain conformant to the approved baseline.
- [ ] Renderer tests use verified-shaped source results and assert narrative facts as well as representation parity; final browser/design proof remains Task 3.2.


Implementation evidence: renderer changes in `runner/eval_output.py`; focused CLI renderer suite `python -m pytest tests/test_eval_builtin_cli.py -q` passed (19 tests). This proves local renderer behavior only. Full five-iteration fixtures use repeated occurrences of one skill, not distinct skills; raw capture/family facts are retained in fenced JSON or escaped HTML trees. Markdown literal input labels are HTML-entity escaped. Browser/host rendering, reflow, keyboard, and actual multi-skill OCI proof remain unverified and are owned by Tasks 3.2/3.3.

### Phase 3: Reconcile documentation and prove assembled product

#### Task 3.1: Reconcile stale plan and requirements status [S] → owner: documentation maintainer

Target/change surface: `docs/plans/runner-evaluation-format-contracts.md`, `docs/requirements/eval-format-ownership/index.md`, and only affected documentation indexes/logs required by repository policy.
Type: Documentation
Nature: Documentation
Execution fit: One bounded consistency pass over statements made stale by actual implementation/review history. It explicitly excludes rewriting accepted BR/OC content; scope expansion discovered during reconciliation returns to the authority owner.
Applicable skill: documentation, okf-authoring
Implements: [ARS-001](../architecture/eval-format-ownership/specifications/ars-001-runner-eval-contract.md) and accepted [requirements bundle](../requirements/eval-format-ownership/index.md)
Depends on: 2.1, 2.2, 2.3.
Acceptance criteria:

- [x] Plan status distinguishes historical evidence, current unproven gaps, planned work, and executed verification; it makes no stale assertion that a resolved architecture question is still open or that review/critic gates passed for current HEAD.
- [x] Requirements index reconciliation removes the obsolete claim that the multi-input realization remains an unresolved architecture conflict, while preserving BR-005 and the architect's settled realization.
- [x] Links, bundle index, change log, and OKF metadata touched by this reconciliation validate and resolve; no requirement or accepted contract is rewritten to fit implementation.
- [x] User-facing usage docs remain unchanged: `docs/eval-usage.md` already documents repeated skill inputs, all four formats, verified persisted outputs, readable report hierarchy and v2 combined output as implemented in current code.

#### Task 3.2: Prove both real evaluation journeys and report design [L] → owner: product acceptance integrator

Target/change surface: public eval CLI, real host adapters, local OCI image/invoke path, artifacts/verifier, all renderers, current documentation, and recorded run evidence.
Type: Testing
Nature: Enhancement
Execution fit: This is intentionally one composition task because both scenarios share the real build/configuration, invocation and artifact provenance setup, and each independently verifies one family outcome through every representation. It is downstream of all fixes; splitting scenario setup from proof would duplicate infrastructure and risk inconsistent evidence. If prerequisites make this materially broader than one execution loop, preserve completed proof and re-slice the remaining scenario only.
Applicable skill: product-acceptance, design-validation
Implements: [ARD-001](../architecture/eval-format-ownership/design/ard-001-runner-owned-input-and-output-contracts.md), [ARS-001](../architecture/eval-format-ownership/specifications/ars-001-runner-eval-contract.md), and [report baseline](../design/eval-format-ownership/multiskill-readable-report-baseline.md)
Depends on: 2.1, 2.2, 2.3, 3.1.
Acceptance criteria:

- [ ] Execute E2E-001 and E2E-002 through the real public interface and actual product-owned adapter, OCI invocation/image, verifier, persistence, and rendering path; record exact build/HEAD, configuration, external substitution, actions, observed outcome and evidence location.
- [ ] Each scenario runs an evaluation once to a verified eligible durable result, then separately obtains all four formats from that same persisted result; compare every representation against the same result and preserve real state provenance.
- [ ] Verify pre-invocation rejection for invalid/duplicate combined inputs and verify corrupt source/output failure cannot claim success; use upstream-generated state for every behavior claimed.
- [ ] Real combined run has multiple skills and five iterations per case; reports expose the design-required run outcome and attributed per-iteration details without invented aggregates.
- [ ] If required OCI/provider/configuration is unavailable, mark the affected scenario UNPROVEN with the missing prerequisite and evidence retained; do not use a mock or injected state to close it.

#### Task 3.3: Validate generated reports against the approved design [M] → owner: designer / design-validation reviewer

Target/change surface: Actual Markdown and HTML generated by Task 3.2 and the approved [combined report baseline](../design/eval-format-ownership/multiskill-readable-report-baseline.md); read-only assessment.
Type: Testing
Nature: Assessment
Execution fit: This is a focused human-facing review of the real report outputs, separate from the integrator's product-path setup and state-provenance reasoning. It cannot be completed using renderer unit fixtures alone; failed findings route to the renderer owner and invalidate affected report evidence.
Applicable skill: design-validation, accessibility-design
Implements: [BR-004](../requirements/eval-format-ownership/br-004-present-readable-markdown-and-html-results.md), [QS-001](../requirements/eval-format-ownership/qs-001-readable-multi-skill-five-iteration-reports.md), and [report baseline](../design/eval-format-ownership/multiskill-readable-report-baseline.md)
Depends on: 3.2.
Acceptance criteria:

- [ ] Assess the actual generated reports from the verified multi-skill/five-iteration run, not a placeholder or injected fixture.
- [ ] Record evidence for summary-first hierarchy, skill/case/iteration attribution, independently findable statuses and comparisons, same-report captured details, semantic reading order, text status independent of color, keyboard links/disclosures, and 320 CSS-pixel / 200% zoom reflow.
- [ ] Report design gaps without silently redesigning accepted scope; return implementation changes to the renderer owner and mark affected acceptance evidence unproven until rechecked.
- [ ] Make no blanket WCAG conformance claim.

### Phase 4: Close review and merge readiness

#### Task 4.1: Independently review fixes and proof [M] → owner: reviewer

Target/change surface: final PR diff, accepted requirements/architecture/spec/design, CI evidence, local/vertical tests, E2E artifacts and design validation.
Type: Testing
Nature: Maintenance
Execution fit: One read-only final review across the exact contract seams and proof record. It follows implementation to avoid reviewing moving targets. Prior review lineage is disclosed; this is independent of implementation, not a claim of blind first assessment.
Applicable skill: product-acceptance, design-validation, risk-driven-planning
Implements: [ARD-001](../architecture/eval-format-ownership/design/ard-001-runner-owned-input-and-output-contracts.md)
Depends on: 1.2, 2.1, 2.2, 2.3, 3.1, 3.2, 3.3.
Acceptance criteria:

- [ ] Trace every obligation in this plan to actual code and evidence; inspect the exact runtime readiness, output schema/provenance, trap/timestamp, readable report, CI discovery, and `--profile` preservation boundaries.
- [ ] Reconcile each inherited reviewer finding and record whether fixed, still failing, or unproven; do not represent a prior verdict excerpt as fresh independent evidence.
- [ ] Any blocking finding returns to the responsible task with affected tests/E2E invalidated and rerun; no requirement is waived by green neighboring tests.

#### Task 4.2: Recheck and disposition PR merge readiness [S] → owner: integrator

Target/change surface: PR #89 required checks, reviews, branch protection and mergeability at final HEAD; no source edits.
Type: Testing
Nature: Maintenance
Execution fit: Small final external-state check, dependent on all proof and review gates. It may end in “not ready”; its purpose is a truthful disposition, not forcing merge.
Applicable skill: product-acceptance
Implements: [ARD-001](../architecture/eval-format-ownership/design/ard-001-runner-owned-input-and-output-contracts.md)
Depends on: 1.1, 1.2, 2.1, 2.2, 2.3, 3.1, 3.2, 3.3, 4.1.
Acceptance criteria:

- [ ] Record final PR head SHA, merge state, required checks/reviews and exact remaining blocker(s), with current evidence references.
- [ ] Declare ready only when all mandatory findings/guarantees have passing evidence and GitHub reports no unresolved merge blocker; otherwise list the precise outstanding owner/action.
- [ ] Do not merge, modify PR metadata, or claim the PR is unblocked as part of this task unless separately authorized.

## Dependency and ownership graph

```text
1.1 current blocker investigation ───────────────────────────────┐
1.2 CI coverage ──────────────────────────────────────────────┐  │
2.1 runtime readiness ───────────────────────────────────────┐ │  │
2.2 result projection/trap semantics ──> 2.3 readable render ─┤ │  │
                                                              v v  v
                                     3.1 docs reconcile ──> 3.2 real E2E ──> 3.3 design check
                                                                         │             │
                                                                         └──────┬──────┘
                                                                                v
                                                                            4.1 review
                                                           │
                                                           v
                                                4.2 final merge disposition
```

| Task | Owner | Read surfaces | Write surfaces | Dependencies / coordination |
| --- | --- | --- | --- | --- |
| 1.1 | Integrator | PR status, repository policy | Evidence note only | None; can run in parallel with source fixes. |
| 1.2 | CI/workflow maintainer | CI workflow, pinned test dependencies, test modules | `.github/workflows/ci.yml` and only test config needed | None; keep separate from runner files. |
| 2.1 | Runner evaluation maintainer | ARS-001, `eval_evidence.py`, `eval_builtin.py`, tests | Runtime readiness/gating and focused tests | None; separate semantic boundary. |
| 2.2 | Runner output maintainer | ARS-001, `eval_builtin.py`, `eval_output.py`, tests | Projection/trap/timestamp result mapping and tests | None; owns result model correctness before renderer work. |
| 2.3 | Runner report maintainer | Approved design, `eval_output.py`, tests | Markdown/HTML rendering and tests | Depends 2.2; shared output file means serialize after 2.2. |
| 3.1 | Documentation maintainer | Plan, requirements index, authoritative docs, implementation state | Plan and factual index/log/usage doc corrections | After code fixes so current behavior can be described accurately. |
| 3.2 | Product acceptance integrator | Final implementation, real runtime image/config, tests and design baseline | E2E evidence records only | Depends on all fixes/docs; shared OCI/provider/artifact state must be isolated per run and provenance recorded. |
| 3.3 | Designer / design-validation reviewer | Real generated Markdown/HTML, report baseline | Design-validation evidence only | Depends on actual reports from 3.2; no renderer edits. |
| 4.1 | Reviewer | Final diff, all authority and evidence | Findings/dispositions only | After all implementation and proof; any blocker invalidates dependent evidence. |
| 4.2 | Integrator | Current GitHub PR state and 4.1 disposition | Final readiness record | Last; rechecks external state after review. |

## Execution waves

1. **Wave 1 (parallel):** 1.1 exact blocker investigation; 1.2 CI coverage; 2.1 runtime readiness; 2.2 result projection/trap semantics. Their write surfaces are disjoint except 2.2's contained output projection responsibility; do not concurrently edit the shared output module from 2.3.
2. **Wave 2:** 2.3 readable Markdown/HTML after 2.2. Documentation task 3.1 starts after 2.1–2.3; no documentation statements should claim fixes before they land.
3. **Wave 3:** 3.2 real composed E2E after code and docs. Re-run local/CI checks for changes made after Wave 1 as relevant.
4. **Wave 4:** 3.3 design validation of reports from 3.2, then 4.1 independent review. Resolve/rerun any findings before 4.2 current PR merge-state disposition.

## Plan checks

1. **Authorities:** Listed requirements, ARD, ARS, approved report baseline, PR/reviewer evidence and repository state; current plan supersedes stale status while retaining historical caveats.
2. **Obligations:** Every known reviewer issue and accepted cross-component guarantee has an owner, satisfier, and falsifiable verification; accepted GHCR transfer is explicitly out of scope by agreement.
3. **Decisions:** No new product or architecture decision is hidden in implementation. If implementation finds ARS/ARD contradict the approved requirement, stop only dependent work and return the conflict to the relevant authority.
4. **Foundations:** CI and local semantic/projection fixes precede renderer, docs, assembled proof, independent review and merge-state disposition.
5. **Graph:** Each task appears once; dependencies are acyclic and complete; shared `eval_output.py` changes are ordered; exact GitHub blocker investigation does not falsely gate independent code fixes.
6. **Mechanisms:** Readiness, strict projection, timestamps, null trap semantics, same-run rendering and report hierarchy each cite ARS/ARD/BR/OC/QS/design authority.
7. **Repo claims:** HEAD/base/worktree facts were verified this session. Reviewer findings and exact code ranges are source-backed via the handoff; GitHub blocker reason, OCI run availability, and current product proof remain unresolved until their tasks execute.
8. **Execution fit:** Runtime semantics, output projection, presentation, CI coverage, docs, E2E, review and GitHub state are split at independent ownership/context/verification boundaries. The two E2E scenarios share setup and are grouped for one integration/provenance loop.
9. **Vertical proof:** Task 2.1 tests evidence-to-gate semantics; Task 2.2 tests verified result projection; Task 3.2 composes actual invocation → verified state → output.
10. **E2E:** Exactly two scenarios distinguish agent/runtime evidence/judge semantics from combined skill ablation, attribution and five-iteration readability. Both require real product-owned components and upstream-produced state; actual human-facing output validation is separately owned by 3.3.
11. **Pass honesty:** Local implementation tasks are recorded as complete only where focused evidence exists. Real OCI composition, current browser/design validation, independent final review, hosted CI confirmation, and current GitHub merge disposition remain open; no no-egress or WCAG conformance claim is inferred from historical evidence.

## Open questions

| Question | Owner | Blocks |
| --- | --- | --- |
| What exact GitHub condition currently makes PR #89 merge state BLOCKED? | Integrator via Task 1.1; GitHub evidence is authoritative | Final merge-readiness claim only; code-backed fixes proceed independently. |
| Is the approved real OCI image and OpenCode-configured provider available for the two required product proofs? | Integrator / environment owner | E2E completion; unavailable proof remains UNPROVEN and cannot be replaced by mocks. |
| Does the actual final source or design inspection expose any requirement/architecture contradiction beyond the review findings? | Architect or product authority, only if evidence identifies one | Only the affected implementation or acceptance claim; no such contradiction is assumed now. |
