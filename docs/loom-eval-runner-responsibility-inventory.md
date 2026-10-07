# Loom eval runner responsibility inventory

Status: research inventory for issue #58, parallel worker A.

This document is intentionally not the final generic eval-engine architecture. It records what the current Loom harness does, classifies ownership, and identifies behavior that must not be copied into the future engine. The integration owner can use this inventory together with the runner-contract inventory to synthesize the architecture.

## Sources pinned for this inventory

- Loom repository: bateau84/loom
- Loom branch: functionality-anchor-requirements-coherance
- Loom file: scripts/run-evals.py
- Loom file SHA: 30f2ae87764be180173a9e5b4b609ee79b2f063d
- Post-PR-#45 opencode-eval-runner integration base: fd9da10cbe2a8182fc8910ec199a221250deb3ca
- Runtime evidence contract file SHA: 01f7c72b57e468b8189927f148f9aaf8a2caac45
- Invocation usage file SHA: 5e82aa91291fb12230c3ddba9eec11db7c190b5d
- Runner README result-contract file SHA: f93709bfe21116cfb7fad7a5e38b4f12b5ac9fa4

The post-#45 runner contract is treated as authoritative where it conflicts with historical Loom-side observation or evidence code.

## Classification legend

This inventory uses the four ownership classes required by issue #58:

1. **Generic orchestration** — reusable sequencing or run-management behavior that is not Loom-specific.
2. **Project/profile** — Loom-owned case semantics, setup, assertions, judge policy, scoring, or execution-profile policy.
3. **Low-level invoke** — behavior already owned by opencode-eval-runner invoke and its result/runtime-evidence contracts.
4. **Legacy/compatibility — do not migrate** — historical Loom-side transport, evidence, or compatibility machinery superseded by the post-#45 runner boundary.

Some current functions mix classes. Those functions are split by responsibility below instead of being assigned wholesale.

## Current end-to-end lifecycle

For a normal non-ablation case, scripts/run-evals.py currently performs this sequence:

1. Discover Loom suites and skill-owned suites.
2. Select cases and normalize skill-owned legacy shapes.
3. Expand selected cases into a case × iteration job matrix.
4. Create an isolated target project and judge project.
5. Materialize Loom agents, skills, fixtures, and runtime plugin inputs.
6. Build target invocation inputs.
7. Invoke the target through opencode-eval-runner when available, otherwise through a historical direct-container fallback.
8. Apply Loom-side transport projection and historical observer/evidence processing.
9. Apply a Loom-side target evidence gate.
10. Run deterministic Loom assertions.
11. Build and invoke the semantic judge when the target is usable.
12. Parse and validate the Loom judge response.
13. Classify the run as pass, behavioral-fail, or non-evidence.
14. Write one per-case/per-iteration artifact, hash it, and verify the durable artifact before counting it.
15. Report per-case status and a final passed/total count.

Skill-owned cases replace the single target/judge sequence with baseline target → baseline judge → candidate target → candidate judge, then calculate an ablation delta and skill-value classification.

This lifecycle contains a reusable orchestration skeleton, but almost every input and semantic decision around that skeleton is Loom-owned.

## Responsibility inventory

### 1. Generic orchestration responsibilities

These are the reusable orchestration behaviors demonstrated by Loom.

| Current Loom behavior | Current location | Why it is generic |
| --- | --- | --- |
| Build a run identity and case/iteration identity | main, write_case_artifact | A multi-case engine needs stable run and job identity independent of project semantics. |
| Expand selected cases into case × iteration jobs | main: jobs construction | Iteration is orchestration, not a behavioral assertion. |
| Sequence target execution before judging | run_case | The project supplies target inputs and judge semantics; the engine controls phase order. |
| Do not run the judge when the target invocation is unusable | run_case | Phase gating is orchestration. The reason a target is unusable comes from invoke/evidence/project logic. |
| Track target, judge, and total timings | run_case, run_skill_ablation_case | Timing/provenance is generic run metadata. |
| Execute explicit retry attempts outside invoke | invoke_container_with_retry | The loop is orchestration. One invoke remains one isolated invocation. |
| Preserve retry attempt/error history in the invocation result | invoke_container_with_retry | Retry provenance must remain visible rather than hidden. |
| Produce a top-level run classification that distinguishes evidence failure from behavioral failure | classify_behavioral_result | The tri-state outcome concept is generic, although Loom currently names fail as behavioral-fail and supplies Loom semantic inputs. |
| Create and claim an artifact directory for one run | claim_artifact_directory | Preventing accidental cross-run artifact mixing is generic run management. |
| Write per-job artifacts atomically | write_case_artifact | Durable per-run evidence is generic orchestration. |
| Hash and verify the durable artifact before counting/reporting it | artifact_evidence_id, verify_case_artifact | Artifact integrity between in-memory result and durable result is generic. |
| Run jobs sequentially or through a bounded worker pool | execute_group in main | Bounded concurrency is generic orchestration. |
| Aggregate per-job success into process success/failure | report and main | Run-level completion/exit status is orchestration. |

#### Important split: retry mechanism versus retry policy

The current retry loop is reusable orchestration, but its hard-coded retryability rule is not a generic contract:

- retries are limited to 0..5;
- only provider.no-route plus Model unavailable is considered transient;
- any observed tool/action disables retry because replay could duplicate side effects;
- backoff is capped at two seconds;
- exhausted retries remain non-evidence.

The invariant to preserve is structural: retry happens outside invoke and every attempt is a separate invocation. The exact provider-error predicate and replay-safety evidence used by Loom are current policy, not a universal behavioral rule.

#### Important split: concurrency mechanism versus Loom runtime policy

Thread-pool execution and concurrency caps are generic. Loom's division into runtime and non-runtime groups is project/profile policy:

- non-runtime work uses --parallel;
- runtime work defaults to serial execution;
- --runtime-parallel greater than one is explicitly treated as load/stress;
- non-runtime jobs are executed as one group before runtime jobs.

That policy exists because one Loom runtime case can itself dispatch multiple model-backed subagents. It should be recorded as a Loom profile choice, not assumed to be universally correct.

### 2. Loom/project/profile responsibilities

These behaviors encode Loom's corpus, product topology, behavioral meaning, or benchmark policy and must stay project-owned.

#### Case discovery and normalization

| Function/behavior | Location | Project responsibility |
| --- | --- | --- |
| Discover evals/*.json | behavioral_eval_files | Loom suite layout. |
| Interpret suite/case default opt-in flags | load_cases | Loom corpus selection semantics. |
| Discover skills/<skill>/evals/*.json | skill_eval_files | Loom skill repository layout. |
| Accept legacy skill eval shapes | skill_eval_raw_cases | Loom compatibility for existing case files. |
| Convert skill-owned cases to SKILL-<skill>-<id> runtime cases | normalize_skill_eval_case | Loom-specific normalized case semantics. |
| Enforce skill folder/declaration agreement and unique skill case IDs | skill_eval_raw_cases, load_skill_owned_cases | Loom authoring contract. |
| Target kind/name and selector aliases | case_target_kind, case_target_name, case_selectors | Loom case selection UX. |
| Global duplicate case-ID rejection | main | Corpus validation belongs with project case normalization. |

The central Loom suites are mostly consumed as authored. Skill-owned evals receive stronger runtime normalization and support several historical JSON shapes.

#### Target and workspace preparation

The following are Loom/profile behavior:

- safe placement of authored fixture_files inside the isolated project;
- creation of target and judge OpenCode projects;
- copying the Loom skills tree;
- copying/promoting Loom agent files;
- wrapping role-decision and conversation-response agents with tool-denied evaluation boundaries;
- creating the eval-judge agent from Loom's JUDGE_AGENT prompt;
- choosing read-only versus read-write workspace mode from Loom execution mode;
- materializing the full Loom agent set for runtime cases so Loom subagent roles resolve;
- supplying the Loom repository as config-root and expecting the Loom plugin for runtime cases;
- mounting Loom node_modules for runtime cases;
- target prompt differences between runtime/conversation and role-decision cases;
- Copilot-specific insertion of Loom agent or skill guidance into system text.

The generic orchestration layer may need a prepared invocation specification, but it must not know how Loom agents, skills, fixtures, or plugin trees are built.

#### Judge construction and semantic interpretation

All of these are Loom-owned semantics:

- JUDGE_AGENT content and its execution-mode rules;
- positive expectations, forbidden behavior, and named trap meaning;
- judge_prompt layout and which target observations are shown to the judge;
- parse_judge strict JSON shape;
- judge_contract_error requirement that every expectation and violation is represented exactly once;
- semantic_pass rules;
- semantic_behavior_score;
- trap handling;
- skill-value labels and the 10 percentage-point material-improvement threshold.

The engine can sequence a judge invocation, but it cannot own this rubric without turning Loom policy into a universal evaluation language.

#### Deterministic assertions

The entire deterministic assertion language in scripts/run-evals.py is Loom/project behavior:

- tool requires/forbids;
- action requires/forbids/any_of;
- argument alias normalization;
- equals, ends_with, contains, contains_all matching;
- output contains/forbids;
- minimum source URL checks;
- native skill-load confirmation;
- tool-result requires/forbids;
- occurrence and after ordering;
- Loom-specific normalization of tool names and Code Mode call shapes.

Key functions include normalize_tool, normalized_target_actions, action_matches, tool_result_matches, tool_result_call_state, result_evidence_events, describe_* helpers, and deterministic_failures.

This is evidence-consuming project logic, not a candidate universal assertion DSL.

#### Skill ablation

run_skill_ablation_case is a Loom/project evaluation profile, not generic core behavior.

It owns:

- baseline versus candidate workspace construction;
- removal of the target skill from baseline;
- exposing only the target skill to the candidate;
- reasoning-only/no-persistence boundaries;
- transport-specific skill injection;
- baseline contamination detection;
- four invocations per iteration;
- baseline/candidate semantic scoring;
- delta_pp;
- trap_fixed/trap_regression;
- material-improvement/improvement/neutral/regression;
- candidate absolute PASS requirement.

A generic engine may execute whatever phases a profile asks for, but this benchmark meaning belongs to Loom.

#### Loom reporting and selection UX

The following are project/CLI concerns rather than generic engine semantics:

- --all, --cases, --suite, --target-kind, --target selection rules;
- the inference-spend safety rule requiring an explicit selection;
- native skill-routing restrictions for non-OpenCode target transport;
- Loom-oriented labels such as agent/execution and skill-ablation output;
- printing deterministic failure details and Loom action previews.

Issue #58 explicitly excludes adding a public eval CLI now, so these current CLI choices are evidence of behavior, not an interface to copy.

### 3. Low-level invoke responsibilities

The post-#45 runner already owns the single-invocation execution boundary. These current Loom concerns must not be reimplemented by the generic eval engine.

| Current Loom concern | Current functions | Post-#45 owner |
| --- | --- | --- |
| Resolve Podman/Docker | resolve_engine | opencode-eval-runner invoke |
| Select/override transport image | image_for_transport and DEFAULT_IMAGES | invoke configuration |
| Bind workspace and additional mounts | volume, prepare_node_modules_mount, invoke_container | invoke |
| Pass network mode | invoke_container | invoke |
| Forward explicit environment variables/provider credentials | host_environment_for_transport, pass_env | invoke |
| Seed auth/config/models/OpenCode DB/config-root | default_* helpers, sanitize_database_seed, resolve_optional_file | invoke |
| Enforce workspace ro/rw mount mode | invoke_container | invoke |
| Set model, agent, skill, reasoning, expected plugin | invoke_container | invoke |
| Enforce inner model timeout and outer container timeout | invoke_container | invoke |
| Execute exactly one isolated OCI transport invocation | invoke_container's runner path | invoke |
| Validate official result shape before persistence | historical Loom checks | host runner validates result/v1 and runtime_evidence/v1 |
| Build/validate authoritative runtime evidence | historical Loom observers/projections | runner runtime_evidence/v1 builder/validator |

The orchestration layer chooses invocation inputs and time budgets. The low-level runner performs one invocation and returns one validated result.

### 4. Legacy/compatibility behavior that should not migrate

The largest non-portable section of run-evals.py is historical evidence/transport compatibility code. Post-#45 contracts supersede it.

#### Direct OCI fallback

invoke_container first prefers an opencode-eval-runner executable. If it is absent, Loom constructs and runs the transport container directly.

That fallback duplicates runner responsibilities:

- OCI hardening flags;
- workspace/input/seed mounts;
- provider environment forwarding;
- timeout handling;
- raw stdout JSON parsing;
- result projection.

The future generic orchestration layer should not preserve a second execution implementation beside invoke.

#### Candidate runner-safety mode and private-policy machinery

The CredentialEntry/CredentialInventory block and associated RUNNER_SAFETY_* constants/functions implement an older candidate safety adapter. This includes:

- immutable candidate image/hash checks;
- private credential inventory construction;
- policy-file generation;
- safe-result admission;
- evidence_safety acknowledgement/validation;
- custom safe-result schemas;
- disposable runtime-state checks;
- preflight result synthesis.

Post-#45 runtime evidence moves authoritative observation safety and validation into the runner. This older Loom-side admission system is compatibility history, not generic eval-engine behavior.

#### Loom-side tool-result reconstruction

The following historical paths must not become a second evidence authority:

- extracting tool results from raw target stdout;
- opencode-eval-runner/tool-results/v1 projection consumption;
- observed_tool_results;
- nested Code Mode call reconstruction;
- metadata alignment;
- truncation and omission accounting maintained by Loom;
- result matching against that reconstructed ledger.

Post-#45 explicitly says tools, actions, tool_result_evidence, stdout/stderr, model text, and workspace files are diagnostic/convenience data and cannot fill an authoritative runtime-evidence gap.

Project assertions may still consume non-authoritative fields for non-runtime/product semantics where appropriate, but they cannot treat those fields as substitutes for runtime_evidence/v1.

#### In-process Loom observer plugin

setup_projects can install eval-tool-observer.ts and attach_observer_capture can replace the projected tool-result ledger with data from .loom-eval-tool-observer.jsonl.

That is historical Loom-side evidence collection. The post-#45 runner owns authoritative native and Code Mode observation and publishes only runtime_evidence/v1 as the authority.

#### Normal-invoke diagnostic observer

OPENCODE_EVAL_NORMAL_OBSERVATIONS enables loom-normal-invoke-observer.ts and stores normal_invoke_diagnostic.

The code already marks this channel diagnostic_only and deliberately excludes it from scoring/evidence eligibility. It can remain a debugging aid in Loom if useful, but it is not an extraction input for the generic engine.

#### Loom evidence_safety field disposition

prepare_transport_result creates Loom's own evidence_safety map with field state exact/redacted/omitted and target_scoring_evidence_error requires exact values for text/tools/actions/skills_loaded.

That is not the post-#45 authoritative evidence model. The public runtime-evidence field states are available/redacted/omitted/unsupported, and runtime readiness is decided per required runtime boundary/field.

Do not migrate the Loom-side exact-field status engine as a competing evidence authority.

## Detailed function-family map

This map covers the major function blocks in the 5,215-line script.

| Lines | Functions / behavior | Ownership |
| --- | --- | --- |
| 24-43 | strict_json_loads duplicate/non-finite rejection | Legacy helper used by old runner-safety admission; official runner now validates its result. |
| 53-219 | JUDGE_AGENT, agent wrappers, skill baseline/candidate wrappers | Project/profile |
| 222-354 | central and skill-owned case discovery/normalization | Project/profile |
| 357-404 | workspace mode, target identity, reasoning provenance, artifact default, selectors | Mixed: project/profile for target/workspace/selectors; run provenance is generic metadata. |
| 407-586 | safe fixtures, project config, observer attachment, target/judge workspace setup, ablation setup | Mostly project/profile; observer attachment is legacy. |
| 589-721 | engine resolution, default seed paths, DB sanitization, volumes, transport env | Low-level invoke duplication |
| 724-1675 | credential inventory, runner-safety admission, evidence projection/sanitization | Legacy/compatibility — do not migrate |
| 1676-2531 | redaction helpers, stdout/tool-result extraction, observer ledger, nested call reconstruction, prepare_transport_result | Legacy/compatibility — do not migrate as evidence authority |
| 2534-2601 | reasoning enforcement, node_modules mount prep, timeout/image helpers | Mixed: low-level invoke plus Loom profile defaults |
| 2602-3030 | invoke_container | Mixed: desired runner call is low-level invoke; direct-container fallback and Loom evidence projection are legacy |
| 3032-3449 | tool/action/result normalization and assertion matching helpers | Project/profile |
| 3451-3719 | deterministic_failures | Project/profile |
| 3722-3830 | judge prompt, parse/contract validation, semantic pass | Project/profile |
| 3833-3846 | classify_behavioral_result | Mixed: generic tri-state precedence fed by project semantic outcomes |
| 3849-3885 | skill score/value and target prompt | Project/profile |
| 3888-3994 | transport error extraction, retry predicate, old exact-field evidence gates | Mixed: orchestration error handling plus project/legacy policy |
| 3995-4032 | invoke_container_with_retry | Generic orchestration loop; hard-coded retry predicate is current policy |
| 4035-4210 | artifact naming, run claim, hash, atomic write, verification | Generic artifact plumbing with Loom-specific paths/names |
| 4213-4560 | run_skill_ablation_case | Project/profile workflow using generic phase sequencing |
| 4563-4814 | run_case | Mixed: generic target→judge→classification→artifact skeleton with Loom hooks/semantics |
| 4817-4858 | eval_job_concurrency | Generic scheduling mechanism plus Loom runtime/non-runtime policy |
| 4861-5210 | main selection, matrix, execution groups, reporting, exit | Mixed: generic run control plus Loom CLI/profile/reporting |

## Trace details required by issue #58

### Case loading and normalization

Central behavioral suites:

- default discovery is direct JSON files under evals/;
- a suite or case can set default: false to be opt-in;
- explicitly selecting case IDs causes opt-in suites/cases to be included;
- central cases are mostly used in authored shape.

Skill-owned suites:

- every direct JSON file under skills/<skill>/evals/ is discovered;
- accepted historical forms are top-level arrays, {skill,cases}, and {skill_name,evals};
- the declared skill must match the containing folder;
- prompt and expectations are mandatory;
- negative_expectations or must_not becomes must_not;
- trap is normalized to a string and remembered as explicitly declared or not;
- the normalized ID is SKILL-<skill>-<source-id>;
- normalized skill-owned cases always use the skill-eval agent and runtime execution;
- duplicate normalized IDs are rejected.

main later rejects duplicate IDs across the combined central and skill-owned corpus.

### Target setup

Normal cases use a fresh temporary root with separate target and judge projects.

For Loom runtime cases, the target contains:

- all Loom skills;
- the full Loom agent set;
- the selected target agent promoted to primary;
- authored fixture files;
- the Loom runtime plugin supplied from the repository config root;
- node_modules when runtime execution requires it;
- a writable workspace because Loom stores project-local runtime state.

Role-decision and conversation-response cases use wrapped, tool-denied primary agents and a read-only workspace.

The judge gets a separate project containing only the eval-judge agent.

This isolation pattern is useful evidence for the generic lifecycle, but the contents and mutation policy are Loom profile decisions.

### Target invocation

run_case resolves target/judge models, reasoning provenance, images, timeouts, and seed files, then calls invoke_container_with_retry.

For a Loom runtime target:

- target transport must be OpenCode;
- config_root is the Loom repository;
- expected_plugin is loom;
- workspace is writable;
- node_modules are mounted;
- case-specific target timeout can override the global timeout.

Judge invocations use a separate judge workspace and no Loom runtime plugin.

Skill ablation uses separate baseline, candidate, and judge projects.

### Retry behavior

invoke_container_with_retry is the only retry loop in the Loom harness.

Each attempt calls invoke_container once.

The current predicate retries only when:

- the invocation has an error;
- the error contains provider.no-route and Model unavailable;
- no tool/action has been observed;
- attempts remain.

A successful retry returns transport_retry metadata with attempt count and prior errors. A terminal failed attempt after earlier retries records all errors.

This is consistent with the issue invariant that retries belong to orchestration, not invoke.

### Runtime evidence and legacy observers

The current Loom script predates the final post-#45 evidence consumer shape.

Its scoring path still uses:

- Loom-side evidence_safety;
- observed_tool_results;
- tool_result_evidence/stdout reconstruction;
- optional eval-tool-observer.ts output;
- optional diagnostic normal-invoke observer output.

Post-#45 changes the authority model:

- runtime_evidence with schema opencode-eval-runner/runtime-evidence/v1 is mandatory;
- it is the only authoritative runtime-evidence object;
- overall status is complete/incomplete/unsupported/invalid;
- readiness is assertion-scoped by required boundary and required field availability;
- native and code_mode_execution may be complete while code_mode_finality is unsupported;
- tools/actions/tool_result_evidence/stdout/stderr/model text/workspace files are not substitutes;
- the host invoke CLI validates runtime_evidence before writing the result;
- Copilot reports runtime evidence as unsupported.

Therefore the Loom observer/evidence stack is reference history for behavior and assertions, not code to extract into the generic engine.

### Judge construction and parsing

run_case invokes the judge whenever the target is usable, even if deterministic assertions have already found behavioral failures.

The judge sees:

- case identity, target, and execution mode;
- trap;
- scenario context;
- every positive expectation;
- every forbidden behavior;
- observed tools/actions;
- runtime tool results for normal Loom runtime cases;
- final assistant text.

parse_judge accepts JSON, including JSON wrapped in common markdown fences, then requires:

- boolean passed;
- expectations array;
- violations array;
- boolean trap_observed;
- string trap_evidence.

judge_contract_error then requires the expectation/violation arrays to exactly match the number of authored rules and requires boolean met/violated values per entry.

These are Loom's judge contract, not a generic judge schema.

### Deterministic checks

deterministic_failures evaluates authored Loom assertions separately from semantic judging.

It distinguishes an observed behavior failure from inability to prove an assertion. Several evidence gaps are represented as strings prefixed with non-evidence:.

Current examples include:

- incomplete capture for required/forbidden tools;
- incomplete capture for required/forbidden actions;
- missing complete tool-result evidence;
- unavailable chronological ordering;
- malformed call identity/input;
- unavailable or indeterminate per-call result;
- missing nested Code Mode capture.

This distinction is valuable, but the exact assertions and evidence mapping are Loom semantics.

### Classification

Normal cases currently classify as:

- non-evidence when target_error or judge_error exists;
- non-evidence when every deterministic failure is a non-evidence failure;
- behavioral-fail when any deterministic behavioral failure exists, including a mix of behavioral and non-evidence failures;
- pass when deterministic checks are clear and semantic_pass is true;
- behavioral-fail otherwise.

The issue #58 target vocabulary is pass | fail | non-evidence. This inventory records the current Loom name behavioral-fail without choosing the final engine representation.

Skill ablation has related but distinct project logic:

- artifact starts as non-evidence;
- target/judge evidence errors keep the run non-evidence;
- candidate absolute pass requires no candidate deterministic failures plus semantic_pass;
- candidate pass produces pass; otherwise behavioral-fail;
- skill-value classification is separate from absolute pass.

### Artifacts

For normal cases, the artifact records:

- case and iteration;
- target identity/profile data;
- target/judge images and transports;
- model and reasoning provenance;
- target/judge/total timing;
- classification and passed boolean;
- full target result;
- target_error;
- normalized observed actions;
- observed_tool_results;
- deterministic failures;
- judge transport result;
- semantic judge object;
- judge_error.

Skill ablation adds baseline/candidate phase records, scores, delta, trap change, and skill-value classification.

Run-level artifact behavior:

- a UUID eval_run_id is generated;
- default directory is .loom-evals/<run-id>;
- .loom-eval-run-id claims the directory;
- a non-empty directory or conflicting owner fails closed;
- per-case files are written through a temporary file plus os.replace;
- artifact_evidence_id is SHA-256 over the serialized artifact excluding the ID itself;
- report re-reads and re-hashes the durable artifact before counting it.

Current limitation to preserve as an observation, not a design decision: exceptions caught by main.execute before run_case writes an artifact are reported to the console but do not necessarily produce a per-job artifact.

### Iterations and concurrency

main creates one job for every selected case and every iteration from 1..N.

Scheduling is split:

- non-runtime jobs use --parallel;
- --parallel with no explicit number maps to the full non-runtime job count;
- runtime jobs use the separate --runtime-parallel cap;
- runtime default is one;
- non-runtime group executes before runtime group;
- parallel result reporting occurs in completion order.

The Loom reason for separate runtime scheduling is product-specific: one runtime case may already dispatch many subagents.

### Skill ablation

Each skill-owned case performs four model invocations per iteration:

1. baseline target;
2. baseline judge;
3. candidate target;
4. candidate judge.

The same target reasoning is used for baseline and candidate. The benchmark separately records absolute candidate correctness and relative skill value.

This is an important project extension use case for the final architecture: the generic engine must not assume every case is exactly one target plus one judge, but this inventory does not choose the extension API.

### Reporting

report first verifies durable artifact integrity.

Console states are:

- PASS for classification pass;
- ERROR for non-evidence;
- FAIL for behavioral-fail.

It also reports:

- total duration;
- artifact evidence ID prefix;
- ablation baseline/candidate delta;
- trap fixed/regression;
- deterministic failure details;
- observed tools/actions;
- semantic judge summary when false.

main exits zero only if every job counted as pass.

## Validation against post-PR-#45 runner contracts

The following cross-checks were made against the merged runner documentation and host CLI behavior.

### One invoke is exactly one isolated invocation

Confirmed.

The host CLI describes invoke as one isolated target or judge invocation and runner/cli.py executes one OCI subprocess for one invoke call. There is no runner retry loop.

Loom's retries are outside invoke in invoke_container_with_retry, which preserves the invariant.

### Runner does not own eval semantics

Confirmed.

docs/invocation-usage.md states that the runner does not own:

- cases/suites;
- assertions;
- judge semantics;
- thresholds;
- target-versus-judge orchestration;
- iterations;
- aggregation;
- PASS/FAIL/non-evidence decisions.

Those match the project/generic split observed in Loom.

### runtime_evidence/v1 is authoritative

Confirmed.

docs/runtime-evidence-contract.md states:

- runtime_evidence is the only authoritative runtime-evidence object;
- raw observers are internal adapter input;
- tools, actions, tool_result_evidence, stdout/stderr, model text, and workspace files are diagnostic/convenience only;
- incomplete or invalid overall capture makes runtime assertions ineligible;
- each assertion declares required runtime boundaries;
- each required boundary must be complete;
- exact required observation fields must be available.

This directly supersedes the Loom-side historical evidence eligibility machinery.

### Boundary support is partial, not all-or-nothing

Confirmed.

The post-#45 contract exposes:

- native;
- code_mode_execution;
- code_mode_finality.

native and code_mode_execution can be complete and eligible while code_mode_finality is unsupported. The generic evidence-readiness stage therefore cannot use only a single top-level complete flag, while project code still decides which boundaries/fields an assertion needs.

### Result contract is validated by invoke

Confirmed.

Each invocation produces one opencode-eval-runner/v1 result with mandatory runtime_evidence. The host validates runtime_evidence before persisting the output file.

The eval engine should consume that validated result rather than rebuild transport evidence.

### Unsupported areas remain explicit

Confirmed.

Post-#45 explicitly reports:

- exact Code Mode caller-final value/error as unsupported on stock OpenCode 2.0.23;
- runtime evidence as unsupported for github-copilot-cli;
- no hostile-plugin isolation guarantee for the trusted-checkout profile.

The project must not fill those gaps from model text or diagnostic result fields.

## Extraction facts for the integration owner

These are inventory conclusions, not final module/API design:

1. The proven reusable lifecycle is target execution → evidence readiness → project checks/judge → classification → durable artifact.
2. Runner invoke is below that lifecycle and remains one invocation per call.
3. Retry is above invoke and must remain visible as multiple attempts.
4. Case discovery, normalization, fixtures, workspace content, prompts, assertions, judge parsing, semantic pass, and ablation meaning are project/profile responsibilities.
5. The generic engine needs to carry project-produced metadata without interpreting it.
6. Iteration and bounded concurrency are generic run mechanics; Loom's runtime/non-runtime scheduling distinction is profile policy.
7. Artifact identity, atomic persistence, attempt/result provenance, and timing are reusable orchestration behavior.
8. The current Loom evidence stack is not an implementation source for the new authoritative evidence boundary. The post-#45 runtime_evidence/v1 contract is.
9. Diagnostic tools/actions/tool_result_evidence may still be useful project inputs, but never as replacements for missing authoritative runtime evidence.
10. Skill ablation proves the project extension surface must support more than one target/judge phase, but its benchmark rules remain Loom-owned.
11. No universal assertion DSL is implied by Loom's deterministic_failures function.
12. No Loom code migration or public eval CLI is performed by this worker.

## Non-goals of this document

This document does not:

- define final engine modules or APIs;
- choose the normalized engine case schema;
- choose the final extension interface;
- migrate Loom cases or assertions;
- change runtime code;
- change invoke;
- add retries to invoke;
- add a public eval CLI;
- define a universal assertion DSL.

Those decisions belong to the issue #58 integration synthesis after both worker inventories are available.
