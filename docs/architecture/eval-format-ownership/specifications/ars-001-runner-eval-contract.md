---
title: Runner evaluation input, result, and output contract
type: Architecture
description: Defines exact accepted input families, additive eval modes, verified result fields, and JSON/YAML/Markdown/HTML representations.
tags: [evaluation, input-contracts, output-contracts, interface]
timestamp: 2026-10-30T00:00:00Z
---

**Status:** Proposed implementation contract; no implementation or compatibility migration is authorized by this artifact.

## Derived from

- [OC-001 — Evaluation case input conformance](../../../requirements/eval-format-ownership/oc-001-evaluation-case-input-conformance.md)
- [OC-002 — Evaluation output conformance](../../../requirements/eval-format-ownership/oc-002-evaluation-output-conformance.md)
- [BR-005 — Evaluate multiple skill inputs together](../../../requirements/eval-format-ownership/br-005-evaluate-multiple-skill-inputs-together.md)
- [BR-004 — Present readable Markdown and HTML results](../../../requirements/eval-format-ownership/br-004-present-readable-markdown-and-html-results.md)
- [QS-001 — Keep multi-skill five-iteration reports understandable](../../../requirements/eval-format-ownership/qs-001-readable-multi-skill-five-iteration-reports.md)
- [ARD-001 — Runner-owned input and output contracts](../design/ard-001-runner-owned-input-and-output-contracts.md)
- [Approved implementation plan](../../../plans/runner-evaluation-format-contracts.md)
- [Task 1.1 Loom responsibility inventory](../../../loom-eval-runner-responsibility-inventory.md), especially case loading, assertion semantics, judging, and skill ablation.

## Satisfies

| Requirement | Contract realization |
| --- | --- |
| BR-001 / OC-001 | Two explicit family validators with closed required fields and the observed authored optional assertion features; reject before invocation; one immutable case identity remains attached to every outcome. |
| BR-002 / OC-002 | A fully typed `eval-output/v1` model rendered as JSON/YAML/Markdown/HTML from one verified run; classifications, attempts, evidence, checks, semantic outputs and paired outcomes remain distinct and complete. |
| BR-003 | The existing `eval` command adds built-in execute and render modes without changing or removing the existing `--profile` mode. |
| BR-004 / QS-001 / OC-002 | Markdown/HTML render the run summary first, then skill/case/iteration results and retain the full captured answers/evidence in the same report. |
| BR-005 / OC-001 | Repeatable explicit skill input paths; run-wide child validation and duplicate composite rejection before invocation; distinct input provenance, skill/case/iteration results and per-skill comparison. |

## Implements

- [ARD-001](../design/ard-001-runner-owned-input-and-output-contracts.md)
- Approved plan Task 1.2. This contract, not implementation preference, owns the accepted fields, versions, wrappers and result fields.

## Scope and source evidence

The accepted source boundary below is grounded in the Task 1.1 inventory and pinned Loom commit `f0e1a78ce2e2171d9b9a755e5d1f323e02994bab`, including `scripts/eval-lib.ts`, `scripts/run-evals.py`, `scripts/loom_eval_profile/case_adapter.py`, `evidence_judge_adapter.py`, `judge_instructions.py`, `skill_ablation.py`, and `_runtime_assertions.py`. It covers the versioned agent/runtime suite (`EvalSuite` version 1) and the three skill shapes the inventory identifies as current input forms: a top-level array, `{ "skill": ..., "cases": [...] }`, and `{ "skill_name": ..., "evals": [...] }`. It does not promise other historical wrappers, directory discovery/context inference, selector aliases, old ID spellings, or migration. No material feature enumerated in OC-001 or the inventory is excluded. Fields not named in these closed contracts are rejected rather than silently ignored. The runner owns implementations of these semantics; the pinned Loom modules are evidence, not runtime dependencies.

## Structural constraints

1. Parsing, validation, normalization, orchestration, persistence, verification and rendering run in the host.
2. `invoke` remains one low-level isolated invocation per call. Each retry is a separate host attempt. No suite, paired workflow, or output work moves into the image.
3. Existing `eval-run/v1`, `eval-artifact/v1`, and `eval-paired-artifact/v1` schema rules, required fields, canonicalization and integrity calculations remain unchanged.
4. Formats are alternatives. A render request projects one completed run in one format; parity is established by rendering the same verified run separately in each format.
5. Output is written to stdout unless `--output PATH` is supplied. In new built-in modes stdout contains only the selected representation; progress and diagnostics go to stderr.

## Interface / schema / protocol

### Additive public `eval` modes

The existing profile mode remains available with its current command spelling and behavior:

```text
eval --profile MODULE:ATTRIBUTE [existing eval options]
```

When invoked with this form and no new built-in mode options, the runner MUST follow the existing `EvalProfile` load, selection, invocation, artifact, summary, stdout/stderr, and exit-code path unchanged. The new flags do not make `--profile` optional in profile mode and do not replace its API. `--format`, `--output`, `--input`, `--family`, `--skill`, and `--render-run` are built-in-mode controls; combining profile mode with any built-in mode control is a usage error before execution. This rejects only a newly mixed invocation, not an existing profile invocation.

New forms, under the same `eval` command:

```text
eval --input PATH --family agent-runtime --target-model MODEL [--all | --cases ID[,ID...]] [invocation options] [--format json|yaml|markdown|html] [--output PATH]
eval --input PATH --family skill --target-model MODEL [--skill NAME] [--all | --cases ID[,ID...]] [invocation options] [--format json|yaml|markdown|html] [--output PATH]
eval --input PATH --input PATH ... --skill NAME --skill NAME ... --family skill --target-model MODEL [--all | --cases ID[,ID...]] [invocation options] [--format json|yaml|markdown|html] [--output PATH]
eval --render-run RUN_DIRECTORY [--format json|yaml|markdown|html] [--output PATH]
```

Execute requires exactly one of `--all` and `--cases`; no implicit all-cases execution. Render mode accepts no input, selection, invocation, profile, or artifact-directory options and never invokes a model. `--format` defaults to `json` in built-in modes only. `--output` selects the rendered representation destination, not the durable artifact directory. Without it output is stdout. `--artifact-dir` retains its existing execution-mode role and default. Format is never inferred from filename extension. Unknown formats, conflicting modes, and invalid combinations fail before invocation. A file destination must not be the run directory or any existing v1 artifact/manifest path.

Every accepted skill-family case uses the pinned skill-ablation lifecycle: baseline target, baseline judge, candidate target, candidate judge, then one skill-owned comparison. There is no non-ablation skill mode in this contract. This preserves the observed source execution path and avoids inventing a new interpretation for the skill-owned family.

`--input` is repeatable only for `--family skill`. Input order is the order of `--input` occurrences. Agent/runtime accepts exactly one input, and no invocation combines families. For one input, retain the existing contract: a top-level array takes its skill identity from `--skill NAME`; either object wrapper carries `skill` or `skill_name`, and an optional `--skill` must match it. For two or more inputs, require exactly one `--skill NAME` occurrence per `--input PATH` occurrence. The skill flag at ordinal N binds only to the input at ordinal N; this explicit binding is required even when the input is an object wrapper, in which case the wrapper identity MUST match. Thus top-level arrays remain accepted in combined runs without filesystem/path inference, and object wrappers cannot conflict with CLI attribution. A mismatched number of bindings or wrapper/CLI identity rejects the whole run before invocation. `--skill` occurrence order does not determine run ordering; input argument order does. There is no directory, glob, recursive, or implicit discovery mode.

The project workspace is the process current working directory, as in the current built-in adapter path. Every declared skill in a combined run must resolve to `cwd/skills/<skill>/SKILL.md` without escaping that `skills` root. Input-file location never selects or changes the workspace. The runner does not create per-skill workspaces outside the existing isolated baseline/candidate invocation workspaces.

Before case selection, the runner reads every submitted input, validates the complete document and all children under `skill-cases/v1`, assigns stable identities, validates every named installed skill and supplied feature, captures source provenance, and checks duplicate composite identities across all submitted children. Any input, feature, workspace-skill, or identity error rejects the whole run before target/judge invocation, even if the offending child would not be selected. Duplicate identity is the pair `(skill identity, canonical case_id)`; submitting the same case-bearing file twice is necessarily a duplicate. Repeated skill identity across different inputs is accepted when canonical case IDs are disjoint.

After full preflight, `--all` selects every child from every submitted input. In a combined run, `--cases` selects exact v2 canonical case IDs, which use a delimiter-safe injective encoding defined below; comma-separated selector parsing therefore cannot confuse a valid skill or source ID containing punctuation. An unknown or ambiguous selector fails before invocation. In the one-input mode, the existing canonical selector spelling remains accepted unchanged. Selection does not change source validation or duplicate checking. Iterations expand each selected child into N independent jobs (`1..N`); each child/iteration, baseline/candidate side, and comparison remains separately attributed. Deterministic order is input argument order, source case order within each input, then ascending iteration. `--profile` command spelling, options, behavior and outputs are unchanged; new built-in controls mixed with profile mode remain usage errors.

### Built-in invocation configuration

The built-in execute mode exposes the existing runner evaluation knobs directly. These values are resolved once before scheduling and recorded with each actual `InvocationSpec` so that target and judge provenance is auditable.

| Option | Default / requirement | Resolution |
| --- | --- | --- |
| `--target-model MODEL` | **Required** for every live run | Caller-selected target model; no default provider or model is inferred. This corresponds to Loom's required `--model`. |
| `--judge-model MODEL` | Target model | OpenCode judge model override; provider/model configuration remains within OpenCode. |
| `--reasoning LEVEL` | unset | Common reasoning setting for target and judge. |
| `--target-reasoning LEVEL` | common value, otherwise unset | Overrides the common setting for target invocations. |
| `--judge-reasoning LEVEL` | common value, otherwise family-specific rule below | Overrides the common setting for judge invocations. |
| `--engine {auto,podman,docker}` | `auto` | Applies to all phases. |
| `--network MODE` | unset | Omitted from invocation spec; existing `invoke` default applies. |
| `--timeout-seconds N` | unset | If provided, overrides both target and judge inner timeout, including a case-specific target timeout. Must be >=1. |
| `--container-timeout N` | unset | If provided, overrides both target and judge outer OCI timeout. Must be >=1. |
| `--transport-retries N` | `0` | Range 0..5; matches current runner behavior. Retries are explicit opt-in. When nonzero, uses the existing runner's replay-safe transient-provider policy; each retry is separately recorded and only occurs when its authoritative no-invocation safety predicate permits it. |
| `--iterations N` | `1` | Must be >=1. |
| `--parallel [N]` | `1` | Existing eval semantics; bare option means all planned standard jobs. |
| `--runtime-parallel N` | `1` | Must be >=1. |
| `--artifact-dir PATH` | `.opencode-evals/<run-id>` | Existing eval durable artifact directory behavior. |
| `OPENCODE_EVAL_RUNNER_OPENCODE_IMAGE` | **Required** for built-in execute mode | Caller-selected immutable identity for an image already present in the selected local OCI engine. No default, tag, or registry fallback. |

All built-in target and judge invocations use OpenCode transport. The built-in interface does not offer transport selection; if a built-in request supplies a transport selector, only `opencode` is accepted, and any other value (including GitHub Copilot CLI) is rejected before any target or judge invocation. Provider/model configuration remains through OpenCode; the runner does not introduce a separate provider configuration path. This restriction does not apply to existing `--profile` mode.

Reasoning precedence is phase-specific option > common `--reasoning` > the family default below. In normal agent/runtime evaluation, if no judge-specific/common value was selected, the judge inherits the target result's reasoning only when that result records reasoning as explicitly supplied; an implicit target reasoning default is not inherited. In skill ablation, target and judge resolve their phase-specific option independently over the common setting; target-only reasoning is not inherited by the judge. Target and judge model selection follows the table above.

For a normal agent/runtime case, `target_timeout_seconds` in the case overrides the Loom target default of 240 seconds; it is validated in [30,600]. The default outer target timeout is `max(300, effective_target_timeout + 60)` seconds. The judge defaults to 120 seconds inner / 135 seconds outer. A caller-supplied `--timeout-seconds` or `--container-timeout` overrides the corresponding timeout for both target and judge. A role/conversation case's optional target timeout uses the same resolution. For skill ablation there is no per-case timeout field: all four phases default to 240 seconds inner / 300 seconds outer; the same two CLI overrides apply to every phase.

The OpenCode-only transport rule applies uniformly to every agent/runtime execution mode, skill reference, and skill-ablation target and judge. Native skill routing and native-load checks are required for skill-ablation candidate execution; the baseline excludes the tested skill. No alternate transport-specific skill methodology is part of this contract.

`--engine`, `--network`, model, reasoning, and timeout overrides modify only the corresponding fields of runner-owned invocation specs. Auth, database, model-catalog, config and provider-environment resolution continue through existing OpenCode `invoke` environment/default mechanisms; family adapters do not reimplement credential discovery or accept secrets from case JSON. For built-in execution, `OPENCODE_EVAL_RUNNER_OPENCODE_IMAGE` is mandatory and is the caller's selection, not a default. Its value MUST identify one exact immutable image using a full local image ID or an engine-supported digest-qualified identity. Tag-only, mutable, missing, registry-only, or locally absent identities are rejected; no generic image environment variable, configured default, or registry fallback may fill or rewrite the selection. Before the first `run`, the host queries only the selected local OCI engine's local image metadata (never pull or contact a registry) and verifies that the selected identity resolves locally and that these image-config labels match the current runner release's declared compatibility contract: `org.opencontainers.image.version` MUST equal its supported OpenCode version, and `io.opencode-eval-runner.invoke-adapter` MUST equal its supported invocation-adapter identifier. The runner release MUST declare these two expected values; missing/unreadable labels, unsupported versions/adapters, or identity mismatch reject before any OCI `run`. The host carries the selected exact immutable identity unchanged into every target and judge `InvocationSpec`; OCI `run` explicitly uses pull-never for every phase. Profile-mode image selection, resolution, and execution remain unchanged. The existing invoke layer remains the sole executor and each phase invocation remains one call.

Catalog compatibility amendment: [catalog ADR-001](../../opencode-catalog/decisions/adr-001-pin-catalog-through-supported-file-interface.md) replaces only the obsolete implicit cache mechanism above. The host resolves the explicit/environment catalog override or current upstream registry once per built-in run, snapshots its bytes before scheduling, and passes the same file to every phase through existing invocation specs. OpenCode consumes it via its native file interface with fetching disabled. Catalog preparation failure remains infrastructure/preparation failure, not a fabricated behavioral outcome; model IDs, reasoning precedence and explicit variant semantics are unchanged. This realization is implemented and revalidated for OpenCode 2.2.2 as recorded in ADR-001; no provider inference or availability is claimed.

### Agent/runtime execution and judging

For each case, create a fresh target project and a separate fresh judge project. The judge project is read-only, contains only the `eval-judge` primary agent, and has no Loom runtime plugin. Runtime target projects contain the Loom skills tree, full agent set with the authored agent promoted to primary, fixtures, Loom runtime plugin/config root, and required runtime `node_modules`; runtime target workspace is read-write and expected plugin is `loom`. Role-decision and conversation-response targets use the authored agent wrapped as a tool-denied primary agent, no runtime plugin, and a read-only workspace. Conversation-response prompt is the authored prompt unchanged. Role-decision prompt is the authored prompt followed exactly by `\n\nRespond with the production decision/action for this scenario. Do not claim to have executed unavailable tools.` All target and judge invocations use OpenCode.

For runtime cases, authoritative `runtime_evidence/v1` is the sole runtime evidence source. Required boundary/field readiness is assertion-scoped using the pinned Loom assertion requirements. Deterministic tool/action/tool-result/output checks run only when required evidence is ready; checks distinguish observed fail from non-evidence. The normal agent/runtime semantic judge is constructed only if the target is usable and every deterministic check is `pass`; any deterministic `fail` or `non-evidence` skips the judge. Classification follows the existing generic runner's exact precedence: (1) target failure => `non-evidence`; (2) missing/unready required evidence => `non-evidence`; (3) required judge execution/parse failure or absent required semantic result => `non-evidence`; (4) any deterministic `fail` => `fail`; (5) otherwise any deterministic status other than `pass` (including `non-evidence`) => `non-evidence`; (6) otherwise semantic judge `fail` => `fail`, semantic judge `pass` => `pass`; (7) with no required judge and all checks passing => `pass`. Thus `pass + non-evidence` checks classify as non-evidence, while `fail + non-evidence` checks classify as fail. Target/readiness/required-judge failures outrank deterministic outcomes exactly as the generic classifier defines.

The runner-owned judge prompt contains, in order: case identity; target identity (`skill:<name>` when skill-targeted, else `agent:<name>`); execution mode; declared trap or `(none declared)`; scenario context marked as untrusted evidence, capped at 30,000 characters; each positive expectation in source order; each forbidden rule in source order; for runtime mode, the canonical authoritative runtime-evidence JSON, capped at 160,000 characters; final assistant text, capped at 30,000 characters. It never asks the judge to infer runtime observations from assistant text, stdout/stderr, tool/action projections, workspace files, or diagnostic results. Judge system instructions require grading observed behavior, mode-appropriate feasibility, and every expectation/forbidden rule plus trap; for runtime, only runtime evidence authorizes tool identity/input/outcome/order/parent/native result facts, and incomplete/unsupported evidence is not proof of absence. The static judge charter is installed as the `eval-judge` primary-agent document with all actions denied in OpenCode because its runner does not forward `InvocationSpec.system`.

Normal agent/runtime judge output is one strict, unfenced JSON object with exactly these keys: `passed:boolean`, `expectations:[{expectation:string,met:boolean,reason:string}]`, `violations:[{rule:string,violated:boolean,reason:string}]`, `trap_observed:boolean`, `trap_evidence:string`, `summary:string`. Duplicate keys, additional/missing fields, non-JSON constants, count/order/text mismatch against authored rules, or wrong primitive types invalidate the judge result. Each authored expectation and `must_not` occurs exactly once, in source order and exact text. A trap is declared iff its trimmed text is non-empty; undeclared trap requires `trap_observed:false`. `passed` must equal `(all expectations met) AND (all violations not violated) AND (no declared trap observed)`. Judge error/malformed output cannot become a semantic pass.

### Skill-ablation construction, evidence, and comparison

Every accepted skill-family case runs the generic paired lifecycle with four phase specs. Preparation creates isolated baseline and candidate target projects plus distinct baseline-judge and candidate-judge projects. Baseline config has its dedicated `skill-baseline` primary agent and no tested skill. Candidate config has its dedicated `skill-eval` primary agent and only the tested skill (excluding its eval/assessment files). Authored fixtures are installed into both target projects. Each judge project is read-only, contains only `eval-judge`, and is isolated from its side's target. All four target/judge phases use read-only workspaces, no Loom runtime plugin, and no `expected_plugin`. Baseline and candidate never share mutable workspace/config state.

With OpenCode, the candidate target spec names the tested skill and baseline target spec has no skill setting; the candidate must produce a completed native skill load under authoritative native runtime evidence, while baseline must not load it. The paired lifecycle requires a complete native evidence boundary for each side. Missing/indeterminate native actor, session, arguments, identifier, or terminal evidence is non-evidence; a completed candidate with no tested-skill load is fail; a tested-skill load or contradictory projection in baseline is non-evidence contamination. Convenience `skills_loaded`, actions, or text cannot substitute for native runtime evidence. Skill-scoring readiness also requires complete target text, tools/actions projections and skill-load projection; inconsistent or missing evidence is non-evidence, never a zero score.

Both target and judge phases use OpenCode. The candidate receives only the tested native skill, while baseline excludes it; candidate native skill load and baseline non-contamination are checked against authoritative runtime evidence. No inline skill-methodology fallback or alternate transport-specific configuration is part of the built-in contract.

For each side, target checks require readiness and complete scoring inputs. The pinned skill-ablation adapter skips a side judge when any check is `non-evidence`; a behavioral `fail` alone does not suppress the skill judge. This differs from the normal agent/runtime judge gate above. The skill judge receives case prompt, positive/negative expectations, trap, and only the complete target assistant text; it does not receive tool/action or tool-result projections as judging facts. It uses the same exact grade object and passed formula as the normal judge. Skill ablation accepts strict JSON with the pinned outer Markdown fence tolerance (` ``` ` or `~~~`, optionally followed by `json`); after removing only one outer fence, the payload must satisfy the same strict duplicate-free schema. Redacted, absent, oversized or invalid judge text is non-evidence/error, not a numeric-zero grade.

Skill behavior score is the fraction of positive expectations met, negative rules not violated, and (if a non-empty trap is declared) trap-not-observed, over the total number of those applicable items. `delta_pp = round((candidate_score - baseline_score) * 100, 2)`. `trap_fixed` means a declared trap was observed in baseline and not observed in candidate; `trap_regression` means declared trap was not observed in baseline and observed in candidate. Skill value is `regression` if trap regression or delta is negative; else `material-improvement` if trap fixed or delta is at least 10 percentage points; else `improvement` if delta is positive; else `neutral`. This label is descriptive only. The paired case's absolute classification is candidate correctness: candidate passes only when its deterministic checks are all pass and its judge passes; comparison decision classification is pass iff candidate absolute classification is pass, otherwise fail. Generic paired lifecycle prevents comparison when either side is non-evidence and preserves both side classifications; no score is synthesized for an unusable side.

Each skill case independently follows this lifecycle. A combined run is a set of per-case lifecycles; baseline/candidate pairing and comparison never cross a skill or case identity. A skill's repeated cases or iterations do not create a per-skill score, rate, ranking, or aggregate verdict. The run-level summary remains the existing runner summary over planned case-iteration jobs, as required for one combined run; it is not a skill-comparison metric.

### Accepted agent/runtime suite input (`agent-runtime/v1`)

Input is one UTF-8 JSON object. JSON duplicate object keys and non-finite numeric constants are rejected. Unknown object fields are rejected at every level. The suite schema is exactly:

```text
AgentSuite = {
  version: integer exactly 1,
  name: non-empty string,
  default?: boolean,
  cases: non-empty AgentCase[]
}
AgentCase = {
  id: unique non-empty string,
  default?: boolean,
  agent: non-empty string,
  skill?: non-empty string,
  execution: "runtime" | "role-decision" | "conversation-response",
  target_timeout_seconds?: integer in [30, 600],
  requirements: non-empty string[],
  prompt: non-empty string,
  trap: non-empty string,
  expectations: string[] with at least 2 non-empty entries,
  must_not: string[] with at least 1 non-empty entry,
  tools?: { requires?: string[], forbids?: string[] },
  actions?: {
    requires?: ActionAssertion[], forbids?: ActionAssertion[],
    any_of?: non-empty ActionAssertion[][]
  },
  tool_results?: { requires?: ToolResultAssertion[], forbids?: ToolResultAssertion[] },
  output?: {
    min_source_urls?: integer in [1, 100],
    contains?: string[], forbids?: string[]
  },
  fixture_files?: { path: non-empty relative path, content: string }[]
}
ActionAssertion = {
  tool: non-empty string,
  // Exactly one match form: tool presence, args subset, or arg comparator.
  arg?: non-empty string,
  equals?: JSONScalar,
  args?: non-empty map<string, JSONScalar>,
  ends_with?: string,
  contains?: string,
  contains_all?: non-empty string[]
}
ToolResultAssertion = {
  tool: non-empty string,
  args: non-empty map<string, JSONScalar>,
  occurrence?: integer >= 1,
  after?: { tool: non-empty string, args: non-empty map<string, JSONScalar> },
  status?: non-empty string,
  output_contains?: non-empty string,
  output_contains_all?: non-empty string[],
  json_path?: non-empty dotted path,
  equals?: JSONScalar
}
JSONScalar = null | boolean | finite number | string
```

An `ActionAssertion` has exactly one of three forms: `{tool}` tests tool presence only; `{tool,args}` tests a subset of the observed argument object; or `{tool,arg,<one comparator>}` tests one selected argument. `args` cannot coexist with `arg` or any comparator. In subset form every authored key is resolved using the pinned argument path/alias rules and its value must equal the authored JSON scalar; extra observed keys do not affect a match. In the selected-argument form exactly one of `equals`, `ends_with`, `contains`, or `contains_all` is required. `equals` uses JSON equality (booleans are type-sensitive); string comparators require a string argument. `contains_all` requires every listed substring to occur in the same selected argument string, not across multiple arguments. `{tool}` alone is valid in `requires`, `forbids`, and every member of `any_of`.

An action/tool-only assertion matches when at least one observation has an available tool field whose normalized tool identity matches. For a required assertion, observed presence passes; complete evidence establishing absence fails. For a forbidden assertion, observed presence fails; complete evidence establishing absence passes. A missing, redacted, omitted, unsupported, malformed or otherwise indeterminate tool field that could change the answer yields `non-evidence` if no conclusive match exists. A conclusive forbidden match remains fail even if another observation is uncertain; a conclusive required match remains pass. Argument-filtered action assertions additionally need an available object-valued input field for a matching tool observation; unavailable or invalid input yields non-evidence unless another observation conclusively matches.

Each `any_of` entry is a non-empty group. Its check passes if any member matches; if none match it is non-evidence when any member/observation is uncertain, otherwise fail. Every group produces a separate check and therefore each authored group must pass for the case to satisfy the full `any_of` field. `requires` and `forbids` evaluate each authored assertion independently; their statuses are not collapsed. The pinned runtime evidence readiness contract still requires both `tool` and `input` fields for the `actions` family, even though a tool-only check reads only `tool`; preserve the readiness result separately, and do not let a passing individual action check erase incomplete overall evidence. For `ToolResultAssertion`, preserve its distinct tool+args+outcome/result/error semantics, including `occurrence`, chronological `after`, and result-value tests; it is not a tool-presence assertion. Tool normalization, source argument aliases, runtime boundary/field requirements, and evidence-state interpretation follow the pinned `_runtime_assertions.py`; no additional aliases are introduced.

`ToolResultAssertion` must include at least one result test: `output_contains`, `output_contains_all`, or both `json_path` and `equals`; the latter two are supplied together. Optional arrays may be empty and then assert nothing. For tools/actions/tool-results, `requires` evaluates every authored assertion and `forbids` evaluates every prohibited assertion; each `any_of` group yields a separate OR check as defined above. This remains Loom's assertion language, not an extensible universal DSL.

`output.contains` requires each literal substring in the final assistant text; `output.forbids` fails when each literal substring occurs in that text. `output.forbids` is not a URL/source assertion. `output.min_source_urls` is optional: when absent, no URL-count assertion is run; when present, it must be an integer in [1,100] or the input is rejected before invocation. Its runtime predicate extracts URL tokens matching `https?://[^\s<>"\[\]()]+`, strips only trailing `.`, `,`, `;`, and `:` from each token, forms a set for the prompt and a set for the final answer, then counts the exact-string intersection. Thus duplicate occurrences count once, URL canonicalization/normalization is not performed, and URLs present only in the answer do not count. Count below the threshold is a deterministic `fail`; missing complete answer text is `non-evidence`.

The public input boundary enforces the accepted optional field's type and range before invocation; rejected values have no evaluation classification. The contract makes no claim about behavior of direct internal assertion-helper calls that bypass this boundary. These runner-owned semantics are grounded in the pinned [`eval-lib.ts`](https://github.com/bateau84/loom/blob/f0e1a78ce2e2171d9b9a755e5d1f323e02994bab/scripts/eval-lib.ts) schema validation and [`_runtime_assertions.py`](https://github.com/bateau84/loom/blob/f0e1a78ce2e2171d9b9a755e5d1f323e02994bab/scripts/loom_eval_profile/_runtime_assertions.py) predicate; neither source is a runtime dependency.

`fixture_files` are written into the prepared isolated project at their authored relative paths; absolute paths, `..` traversal, duplicate destinations and unsafe paths reject the suite before invocation. An absent optional field adds no assertion/setup. Execution mode determines the existing tool boundary and workspace policy; a supplied incompatible tool/action/tool-result feature is rejected, never ignored. `skill` and timeout retain their authored meanings. Suite/case `default` booleans are accepted and retained in provenance. Built-in execution uses an explicitly supplied file, so `--all` includes every case in that file regardless of `default`; `--cases` selects exactly the requested IDs. No directory discovery or default-only selection occurs in built-in mode.

### Accepted skill input (`skill-cases/v1`)

Input is one UTF-8 JSON value with duplicate keys and non-finite numbers rejected. Exactly one of these shapes is accepted:

```text
SkillInput = SkillCase[]
           | { skill: non-empty string, cases: non-empty SkillCase[] }
           | { skill_name: non-empty string, evals: non-empty SkillCase[] }
SkillCase = {
  id?: non-empty string | integer,
  name?: non-empty string,
  prompt: non-empty string,
  expectations: non-empty string[],
  negative_expectations?: string[],
  must_not?: string[],
  trap?: string | null,
  fixture_files?: { path: non-empty relative path, content: string }[]
}
```

For a top-level array `--skill NAME` is required. For either object form the wrapper's skill value is authoritative; optional `--skill` must match it exactly. The two wrapper properties are mutually exclusive; mixed `cases`/`evals`, missing skill identity, empty cases, non-object case entries, and unknown fields reject the document. Exactly one negative-expectation field may be present; supplying both is accepted only if the arrays are equal. The selected list is the complete authored positive/negative expectation set; each non-empty string remains a separate judge rule. `trap` absent, null or whitespace-only means no active trap; a non-empty trimmed trap is presented as a named trap rule to the skill judge, and its observed/evidence result is retained separately. `fixture_files`, when supplied, are safely materialized in both target projects. `name` is descriptive metadata and does not change case meaning.

If `id` is absent, `source_id` is the 1-based array position. The readable source ID is the authored string unchanged or the integer's base-10 spelling; this canonical source-ID text is kept separately from the skill name in `SkillResult.case_identity.source_id` and `authored_id` retains the original string-or-integer type when supplied. The identity is assigned once before normalization and is not regenerated from selectors or output.

For one-input runs, preserve the existing canonical `case_id` and selector spelling `skill:<skill-name>:<source-id>` unchanged. The single skill identity is fixed for that run, so this legacy spelling does not conflate distinct source IDs within its domain. For combined runs, define the canonical `case_id` as `sk1_` followed by unpadded RFC 4648 base64url encoding of this byte sequence: (1) the shortest unsigned LEB128 encoding of the number of UTF-16 code units in `skill_name`; (2) those code units in big-endian order; (3) the shortest unsigned LEB128 encoding of the number of UTF-16 code units in `canonical_source_id_text`; and (4) those code units in big-endian order. Convert each decoded JSON string to its UTF-16 code-unit sequence without Unicode normalization; retain lone surrogate code units if present. Use the canonical base64url alphabet (`A-Z`, `a-z`, `0-9`, `-`, `_`), zero unused trailing bits, and omit padding. The length prefixes and fixed-width code units make this encoding injective over the exact skill-name/source-ID-text pair and it contains no comma, so it remains unambiguous in the existing comma-separated `--cases` syntax without restricting valid input strings. `identity.skill` and the readable `SkillResult.skill`, `source_id`, `authored_id`, `source_index`, and display name remain separate fields; the encoded case ID is an identity/selection key, not a replacement for readable source data. Duplicate canonical composite identities reject the complete submitted set. The source input digest, source position, authored ID if any, and canonical ID are stored, so a later rendering never re-derives identity. No filesystem-directory inference or directory-based selector alias is used.

### Family semantics and execution

The agent/runtime adapter uses the suite's authored agent and execution mode, prompt, requirements, trap, positive/negative expectations and optional runtime assertions. It reports deterministic assertion outcomes separately from the semantic judge result. The semantic judge must report every positive expectation and forbidden rule exactly once, with pass/violation and reason, plus `passed`, summary, `trap_observed` and `trap_evidence`; malformed or incomplete judge output is an evaluation error/non-evidence according to the existing evidence/classification rules, never a successful semantic judgment.

Skill mode uses the skill prompt, expectation list, optional negative list and optional trap as skill-native judge inputs. It produces one expectation result for each authored positive rule and one violation result for each negative rule, with reasons; trap declaration, observed status and evidence are retained. Skill expectation meaning is never converted into agent/runtime assertions. Each skill case comprises four side phases: baseline target, baseline judge, candidate target, candidate judge. Baseline excludes the named skill; candidate receives the target skill only; the pinned target/read-only isolation and candidate methodology behavior is defined above. The skill adapter supplies baseline/candidate semantic scores, candidate absolute pass, comparison delta in percentage points, trap change and skill-value classification. It preserves the pinned score calculation and label precedence defined above. The generic paired lifecycle only blocks invalid/non-evidence sides and validates envelopes; it does not derive these policy results.

### Canonical result wire model: `opencode-eval-runner/eval-output/v1` and `/v2`

Every key below is required unless marked nullable; no `...` placeholders are permitted in emitted objects. JSON and YAML encode the same object tree. All objects reject unknown keys for this schema version. Numbers are finite JSON numbers; timestamps are UTC RFC 3339 strings. An empty array means no facts in that category; `null` means the phase/value is unavailable or not applicable, never pass.

```text
EvalOutput = {
  schema: "opencode-eval-runner/eval-output/v1",
  run: RunResult,
  cases: CaseResult[]
}
RunResult = {
  id: non-empty string,
  created_at: RFC3339,
  input: { family: "agent-runtime"|"skill", contract: non-empty string,
           sha256: 64 lowercase hex },
  execution: {
    mode: "agent-runtime"|"skill-ablation",
    selection: { all: boolean, selectors: string[], case_ids: string[] },
    iterations: integer >= 1,
    concurrency: { standard: integer >= 0, runtime: integer >= 0 }
  },
  summary: {
    status: "pass"|"verdict"|"error",
    pass: integer >= 0, fail: integer >= 0, non_evidence: integer >= 0,
    errors: integer >= 0, not_run: integer >= 0, total: integer >= 0
  }
}
CaseResult = {
  id: non-empty string,
  family: "agent-runtime"|"skill",
  contract: non-empty string,
  iteration: integer >= 1,
  execution_status: "complete"|"error"|"not-run",
  classification: "pass"|"fail"|"non-evidence"|null,
  error: { code: non-empty string, message: string }|null,
  attempts: AttemptGroup[],
  evidence: EvidenceReadiness,
  checks: CheckResult[],
  semantic: SemanticResult|null,
  family_result: AgentRuntimeResult|SkillResult,
  source_artifacts: ArtifactRef[]
}
AttemptGroup = { phase: "target"|"judge"|"baseline-target"|"baseline-judge"|
                        "candidate-target"|"candidate-judge",
                 attempts: Attempt[] }
Attempt = { number: integer >= 1, started_at: RFC3339,
            duration_seconds: finite number >= 0,
            invocation: InvocationRecord,
            host_exit_code: integer|null,
            result: RunnerResultV1|null, failure: AttemptFailure|null,
            retry_decision: { retry: boolean, reason: string,
                              delay_seconds: finite number >= 0 }|null }
InvocationRecord = { transport: "opencode",
                     model: non-empty string, reasoning: string|null,
                     agent: non-empty string|null, skill: non-empty string|null,
                     workspace_mode: "ro"|"rw",
                     timeout_seconds: integer >= 1,
                     container_timeout: integer >= 1,
                     engine: "auto"|"podman"|"docker",
                     network: string|null, image: string|null,
                     expected_plugin: string|null }
AttemptFailure = { plane: "infrastructure"|"product"|"evidence",
                   code: non-empty string, message: string, retry_safe: boolean }
RunnerResultV1 = the complete validated opencode-eval-runner/v1 result envelope,
                  including its complete runtime_evidence object
EvidenceReadiness = { status: "ready"|"incomplete"|"unsupported"|"invalid"|null,
                      reasons: string[], required_boundaries: string[],
                      runtime_evidence: RuntimeEvidenceV1[] }
CheckResult = { name: non-empty string,
                status: "pass"|"fail"|"non-evidence",
                reason: string, metadata: JSONValue }
SemanticResult = { status: "pass"|"fail", summary: string,
                   data: JSONValue }
ArtifactRef = { schema: "opencode-eval-runner/eval-artifact/v1"|
                         "opencode-eval-runner/eval-paired-artifact/v1",
                relative_path: non-empty string,
                evidence_id: 64 lowercase hex }
```

`JSONValue` is null, boolean, finite number, string, array of JSONValue, or string-keyed object of JSONValue. `RuntimeEvidenceV1` is the complete validated runtime-evidence/v1 record, not a reconstruction from stdout, observed tool names, or model text. Attempt numbering is contiguous from 1 within a phase. `InvocationRecord` captures effective, non-secret phase configuration; it excludes workspace paths, credential values, auth/config/database paths, and environment values. `source_artifacts` lists every validated durable record supporting this result. A pre-result terminal error or not-run job has `classification:null`, a structured error/not-run state (not a behavioral verdict), empty unavailable phase-attempt arrays, and no fabricated evidence or family result. A completed job has `error:null` and a non-null classification; a completed job may legitimately classify non-evidence. `EvalOutput` is emitted only for an eligible run (defined below), so every emitted `CaseResult` has a family result; an internal terminal job without one is not serialized as a public case result.

`AgentRuntimeResult` is exactly:

```text
{
  kind: "agent-runtime/v1",
  suite: { name: non-empty string, version: 1, default: boolean|null },
  case: { default: boolean|null, agent: non-empty string, skill: non-empty string|null,
          execution: "runtime"|"role-decision"|"conversation-response",
          target_timeout_seconds: integer in [30,600]|null,
          requirements: string[], prompt: string, trap: string,
          expectations: string[], must_not: string[],
          fixture_files: { path: string, content: string }[] },
  assertions: AgentAssertionResult[],
  semantic_judge: { passed: boolean,
                    expectations: { expectation: string, met: boolean,
                                    reason: string }[],
                    violations: { rule: string, violated: boolean,
                                  reason: string }[],
                    trap_observed: boolean, trap_evidence: string,
                    summary: string }|null
}
AgentAssertionResult = {
  kind: "tools"|"actions"|"tool_results"|"output",
  authored: the exact validated source value for that kind,
  status: "pass"|"fail"|"non-evidence",
  reason: string,
  observed: JSONValue,
  evidence_refs: string[]
}
```

For the `tools`, `actions`, and `tool_results` assertion kinds, `authored` has the exact input type defined above; `observed` carries the matching normalized observations used by the checker. For `output`, `authored` is the validated `output` object and `observed` is `{source_urls: string[], final_text: string}`. `fixture_files` are setup data, not verdict assertions; each fixture path and content is preserved in `case` and fixture preparation failures are execution errors. Agent deterministic outcomes are all represented, including evidence insufficiency as non-evidence. `semantic_judge` is null only when the judge phase did not occur; it is not equivalent to pass.

`SkillResult` is exactly:

```text
{
  kind: "skill/v1",
  skill: non-empty string,
  case_identity: { case_id: non-empty string, source_id: string|integer,
                   authored_id: string|integer|null, source_index: integer >= 1,
                   display_name: non-empty string|null },
  prompt: non-empty string,
  fixture_files: { path: string, content: string }[],
  expectations: non-empty string[],
  negative_expectations: string[],
  trap: { declared: boolean, text: string|null },
  ablation: AblationResult
}
AblationResult = {
  baseline: SideResult,
  candidate: SideResult,
  comparison: {
    schema: "opencode-eval-runner/eval-comparison/v1",
    status: "compared"|"non-evidence"|"invalid",
    baseline_classification: "pass"|"fail"|"non-evidence"|null,
    candidate_classification: "pass"|"fail"|"non-evidence"|null,
    decision: { classification: non-empty string, summary: string,
                data: SkillComparisonData }|null,
    failure: { code: non-empty string, message: non-empty string }|null
  }
}
SideResult = {
  case_id: non-empty string, run_id: non-empty string, iteration: integer >= 1,
  classification: "pass"|"fail"|"non-evidence",
  attempts: AttemptGroup[], evidence: EvidenceReadiness,
  checks: CheckResult[],
  skill_outcome: {
    expectations: { text: non-empty string, met: boolean, reason: string }[],
    negative_expectations: { text: non-empty string, violated: boolean,
                             reason: string }[],
    trap: { declared: boolean, text: string|null, observed: boolean|null,
            evidence: string|null },
    semantic_judge: { passed: boolean, summary: string,
                      behavior_score: finite number in [0,1]|null }|null
  },
  source_artifact: ArtifactRef
}
SkillComparisonData = {
  candidate_absolute_pass: boolean,
  baseline_score: finite number in [0,1],
  candidate_score: finite number in [0,1],
  delta_pp: finite number|null,
  trap_fixed: boolean|null,
  trap_regression: boolean|null,
  skill_value: "material-improvement"|"improvement"|"neutral"|"regression"|null
}
```

`SkillResult.expectations` and `.negative_expectations` are the authored source rules in order. Each side's `skill_outcome` contains exactly one judge result per corresponding rule, preserving this same order and exact source text. Top-level `trap` records only declaration and authored text; each side's `skill_outcome.trap` records observed state/evidence. `trap.declared` is true exactly when a non-empty trap was supplied; absent/empty trap has `declared:false`, `text:null`, and null per-side observation/evidence. The behavior score is the fraction of positive expectations met, negative rules not violated, and (when declared) trap-not-observed, over all applicable rules. On `comparison.status == "compared"`, side scores are fractions in [0,1] and `delta_pp = round((candidate_score - baseline_score) * 100, 2)`. Trap booleans are set if a trap was declared (`trap_fixed` means baseline observed and candidate not; `trap_regression` means baseline not observed and candidate observed). `skill_value` precedence is exact: `regression` if trap_regression or delta < 0; else `material-improvement` if trap_fixed or delta >= 10; else `improvement` if delta > 0; else `neutral`. `candidate_absolute_pass` is true exactly when the candidate side classification is `pass`; the comparison decision classification is `pass` exactly when that boolean is true, otherwise `fail`. Baseline contamination is a side deterministic non-evidence check and blocks comparison through the paired lifecycle; it remains in baseline checks rather than comparison data. Non-evidence/invalid comparison uses null decision and required failure per the existing comparison envelope; it never substitutes zero scores.

#### Combined-input projection: `opencode-eval-runner/eval-output/v2`

The existing v1 schema remains exactly as defined above and is emitted for the existing one-input path. It is not extended with optional fields because v1 rejects unknown keys and has only one `run.input.sha256`. A run with more than one submitted input emits v2. JSON and YAML serialize the same v2 tree. V2 is closed to unknown keys and otherwise reuses v1 field definitions; its exact differences are:

```text
EvalOutputV2 = {
  schema: "opencode-eval-runner/eval-output/v2",
  run: RunResultV2,
  cases: CaseResultV2[]
}
RunResultV2 = RunResult with `input` replaced by {
  family: "skill",
  contract: "skill-cases/v1",
  inputs: SkillInputRef[]  // non-empty, in --input argument order
}
SkillInputRef = {
  ordinal: integer >= 1,   // contiguous, starts at 1
  source_path: non-empty string, // exact path argument supplied by caller
  contract: "skill-cases/v1",
  sha256: 64 lowercase hex,
  skill: non-empty string
}
CaseResultV2 = CaseResult with these additional required fields:
  identity: { skill: non-empty string, case: non-empty string },
  source_input: integer >= 1 // ordinal into RunResultV2.input.inputs
```

All other v1 `RunResult` and `CaseResult` fields and semantics are identical in v2. For every v2 case, `identity.case == id == family_result.case_identity.case_id`, `identity.skill == family_result.skill`, and `source_input` is the ordinal of the exact `SkillInputRef` occurrence from which that case was parsed. The referenced input's bound `skill` MUST equal `identity.skill`; its ordinal, exact submitted path, digest, and contract remain the case's provenance even when another input occurrence has the same skill. Repeated skill identities are allowed when their canonical case IDs are disjoint. The pair `(identity.skill, identity.case)` is unique across the entire submitted set, including unselected children; every v2 emitted case corresponds to one planned case-iteration job and retains its `iteration`. Input ordinals bind provenance and are not identity substitutes. `run.summary` is the same run-level planned-job summary equation as v1; there are no per-skill summary objects or new comparative aggregates.

One-input skill files, including a top-level array selected by the existing `--skill`, continue to emit v1 and retain the existing canonical case ID and `--cases` spelling. Combined skill inputs, including top-level arrays, emit v2 and use the per-input CLI binding to resolve identity; combined `--cases` values are the injectively encoded v2 case IDs. Emitting v2 does not assert that a v1-only consumer accepts v2.

### Summary derivation and result validity

The runner manifest supplies planned jobs and their terminal state. Counts are over case-iteration jobs, not unique authored case IDs:

- `total` is planned job count.
- `pass`, `fail`, and `non_evidence` count completed jobs with that exact classification.
- `errors` counts terminal jobs that could not produce a behavioral result because of orchestration/evaluation error.
- `not_run` counts planned jobs not started or skipped after an earlier run error.
- `status = error` if `errors > 0` or `not_run > 0`; otherwise `status = verdict` if `fail > 0` or `non_evidence > 0`; otherwise `status = pass`.
- Enforce `total = pass + fail + non_evidence + errors + not_run`.

**Public-format eligibility:** An execute or render request may report successful conforming output only for a completed, verified evaluation with a family-owned result for every planned case-iteration job. The manifest must be terminal; all required v1 records must pass integrity verification; and run/case/iteration/family identities and family payloads must agree. A terminal pre-result orchestration/preparation error or a not-run job is outside this eligibility precondition: retain its terminal/error state without fabricating a family result or behavioral classification. If any planned job lacks its family-owned result, execute mode must not report conforming output success and `--render-run` must fail to produce conforming output. No public format can omit that job, invent its result, or turn its error into a verdict. A still-running manifest, missing planned-job disposition, missing family payload, or integrity/identity mismatch likewise cannot render successfully. This restriction does not alter the successful completed-run guarantee: eligible evaluations render from the same verified family results in every requested format.

### Machine and human format mapping

- **JSON:** UTF-8 serialization of exactly `EvalOutput`; duplicate keys and non-finite numbers are prohibited. Object key ordering is non-semantic.
- **YAML:** YAML 1.2 serialization of the identical `EvalOutput` tree; it must load to a JSON-equivalent value. Tags, aliases, merge keys and non-JSON scalar types are prohibited.
- **Markdown:** one document. For v1 retain deterministic run-manifest order. For v2 render the run summary first, then group by skill identity, case identity, and iteration ascending; include each input source path/digest with its declared skill. Render run ID, timestamp, family/contract, mode, selection, iteration/concurrency, all six summary counts/status. For every job render ID and (v2) structured skill/case identity/source-input reference, family, contract, iteration, execution status, classification (or explicit error/not-run), every attempt with phase/number/time/duration/exit/result or failure/retry decision, evidence readiness and runtime evidence, every check/status/reason, semantic result, and all family payload. Skill cases render stable identity/source ID, every positive/negative expectation outcome and trap; ablations render complete baseline and candidate phase outcomes, absolute pass, contamination, scores, delta, trap change, skill-value classification and comparison failure if any. Full captured target/judge answers and supporting evidence remain available in clearly identified details associated with the run/case/iteration; existing sanitization/redaction and truncation state is preserved, and rendering adds no omission/truncation. Headings describe these associations; no status is conveyed by color alone.
- **HTML:** static self-contained HTML5 equivalent in facts and deterministic order to Markdown, using the same v1 order or v2 skill/case/iteration hierarchy. Require `html`, `head/title`, `body`, one `main`, one `h1`, nested run/skill/case/iteration headings, semantic lists or tables with associated headers, text labels for all statuses, and escaped input-derived strings. No interaction is required. Any added interaction must be keyboard-operable with accessible name/state. Full captured answers/evidence remain available in associated detail sections with current capture metadata; status distinctions are textual and color is supplementary.

Markdown/HTML may choose presentation ordering within a job, but may not omit any fact listed above or collapse side outcomes/comparison. This is a functional view, not a polished report; no WCAG level is claimed.

### Durable source and v1 coexistence

The projection is assembled only after the run manifest and all referenced `eval-artifact/v1` and paired artifacts are re-read and verified. For existing one-input runs, each case artifact's integrity-covered `project_metadata.runner_eval` remains exactly `{schema, family, contract, case_id, family_result}` using `opencode-eval-runner/eval-family-result/v1`. For combined v2 runs, the integrity-covered family payload uses `opencode-eval-runner/eval-family-result/v2` and additionally identifies the exact source input ordinal, submitted path, and SHA-256; its family and case identity must match the projection. Both remain covered by existing artifact evidence IDs. The implementation must not change v1 required keys, checksum calculation, reader/writer validation, or reinterpret prior metadata. Public v1/v2 output schemas remain distinct from persisted artifact envelopes.

## Invariants and lifecycle

1. All input documents and all cases are decoded/validated, supported features checked, identities assigned, run-wide composite uniqueness checked, and case selection resolved before first invocation. Invalid input rejects the whole submitted set before side effects, including invalid unselected children.
2. The same canonical case ID is used in normalized case, plan, storage, every attempt outcome, paired sides/comparison and every format. Agent IDs are authored IDs. Skill IDs follow the exact identity rule above.
3. Family identity and contract version cannot change during normalization, execution, persistence, or rendering.
4. Pass/fail/non-evidence remain distinct; infrastructure errors and not-run jobs have null behavioral classification and no fabricated family result; no renderer repairs or changes a verdict.
5. Every conforming public format derives from one completed verified run with a family-owned result for every planned case-iteration job. A pre-result terminal error or not-run job makes the run ineligible; neither execute nor render mode may report conforming output success for it. `--render-run` never evaluates.
6. Existing v1 integrity verification occurs before projection; family extension data is included before v1 hash calculation.
7. Each target/judge/side attempt invokes host `invoke` exactly once; image work remains one invocation.
8. A multi-input skill result binds every case to exactly one explicit source input and digest, and uses `(skill, case)` as its unique composite identity. Selection/iterations cannot change or merge that identity.
9. Multi-input skill results use `eval-output/v2`; the existing one-input path uses unchanged `eval-output/v1`. Every renderer is derived from the same verified versioned result.

## Failure behavior

| Failure | Observable behavior |
| --- | --- |
| Invalid JSON, invalid field/type/version/wrapper, unknown field/feature, duplicate case ID, family mismatch | Usage/input error before any invocation; no behavioral result is created for rejected input. |
| Invalid/unsupported skill input in a combined set; unresolved skill in common workspace; duplicate `(skill, case)` anywhere in submitted children, including repeated file | Reject the whole run before target/judge invocation, irrespective of selection. No valid sibling starts, and no colliding child is merged or omitted. |
| Combined input has a missing/extra `--skill` binding or a binding that conflicts with its wrapper | Reject the whole run before invocation; no case is attributed using path or directory inference. |
| Combined input provenance missing, digest mismatch, case-to-source mismatch, or v2 composite identity mismatch | Verified projection/render fails; no successful output claim or reconstructed source attribution. |
| Invalid/unsupported format or incompatible mode options | Usage error before invocation or output. |
| Missing, mutable, tag-only, nonlocal, mismatched, or unverifiable built-in image identity/version/adapter | Reject before any OCI `run`; no registry/default fallback or pull is attempted. |
| Pre-result terminal orchestration/preparation error or not-run planned job | Run summary status `error`; job retains `execution_status:error|not-run` without a fabricated family result or behavioral classification; the run is ineligible for conforming public output, and execute/render cannot claim output success. |
| Missing/corrupt/unverified/mismatched source artifact, family result, or incomplete manifest | Render fails; no successful output claim and no fact reconstructed from logs. |
| Invalid comparison or non-evidence side | Emit validated `invalid` or `non-evidence` comparison envelope and preserve both side facts; no numeric substitute or invented skill-value decision. |
| Serializer or destination error | Output operation fails and does not change the source evaluation result. File output is temporary-sibling/atomic-replace where supported; stdout may be partial if downstream closes the pipe and command reports failure. |
| HTML content | Escape input-derived text; unsafe markup is never interpreted. |

Diagnostic wording and retry policy for output errors are not specified. Existing profile-mode errors/exits remain unchanged for invocations that do not use the new built-in flags.

## Compatibility and evolution

- The existing `eval --profile MODULE:ATTRIBUTE` path remains additive and behavior-preserving; no profile API migration/removal is authorized. No compatibility duration or migration guarantee is inferred beyond this requirement to keep the current path working.
- Accepted new input contracts are exactly agent runtime suite version 1 and the three skill wrappers/shapes stated above. Other historical aliases, directory-based discovery and selector aliases are not promised. If a currently authored material feature outside this list is identified before implementation, do not silently exclude it; return the precise scope decision to General.
- Repeated `--input` is accepted only for skill family; agent/runtime remains one input and mixed families are rejected. Combined mode requires one ordinally paired `--skill` binding per input, including object wrappers whose embedded identity must agree. This preserves raw top-level arrays without directory/path inference. No directory or glob discovery is accepted.
- Existing v1 envelope schemas and integrity remain unchanged. No external consumer tolerance for the new `project_metadata.runner_eval` content is assumed; no external v1 consumer compatibility promise is made.
- `eval-output/v1` remains distinct from durable v1 artifacts and unchanged for one-input runs. Combined runs emit `eval-output/v2`; v1-only consumers must not be assumed to accept v2. No migration schedule or byte stability is promised.
- Polished-report behavior beyond the specified functional accessible views is out of scope.

## Security surface

Input parsing treats files as data, never executable code. Fixture paths are constrained to safe relative paths within the prepared isolated workspace. HTML escapes input-derived values. Output destinations cannot overwrite durable v1 records. Credentials and workspace mounts retain existing `invoke` controls and trust model.

Built-in image preflight is a local-only metadata read against the explicitly selected OCI engine. It MUST NOT pull, contact a registry, or accept an image by mutable tag. The exact immutable identity admitted by preflight is passed to every target and judge invocation, with OCI pull-never enforced on each run. This guarantee applies only to the new built-in modes; profile-mode image behavior is preserved.

## Verification

1. Validate one suite-v1 fixture with every optional assertion/fixture category and each execution mode; compare each authored feature to its assertion result and preserve semantic judge shape. Specifically test tool-only `{tool}` in `requires`, `forbids`, and `any_of`; complete absence versus missing/unsupported tool evidence; conclusive match alongside an uncertain observation; `args` subset matching with extra observed keys; and `contains_all` matching multiple substrings within one selected argument (not across arguments). For output assertions, test absent threshold (no assertion), unique exact URL intersection between prompt and answer, punctuation stripping, answer-only/duplicate URLs, accepted thresholds 1 and 100, rejection before invocation for non-integer or out-of-range values, insufficient-count fail, and literal `output.forbids` substrings.
2. Validate each accepted skill wrapper; test top-level array with explicit `--skill`, `skill/cases`, `skill_name/evals`, authored and derived IDs, negative aliases, optional traps, duplicate identities and wrong declarations. Reject other wrappers/fields before invocation.
3. Verify the pre-existing `eval --profile` command and all prior profile-mode behavior remain unchanged when new flags are absent.
4. Run each family once to completion; re-verify its durable source, then separately render all four formats from that same run and compare against all typed fields above, not independent runs.
5. Verify normal agent/runtime judge gating on every deterministic non-pass and exact classifier precedence: target failure, unready evidence, and required judge failure are non-evidence; with a usable target/ready evidence, pass+non-evidence is non-evidence, fail+non-evidence is fail, and all-pass checks defer to semantic pass/fail. For skill ablation, separately verify its pinned non-evidence-only judge gate. Verify the summary equation and terminal errors/not-run jobs; no execution error becomes a behavioral verdict.
6. Verify ablation baseline/candidate side identity, all attempts/evidence/checks/semantics, comparison data, 10-point category boundary and trap change; side non-evidence produces no numeric comparison.
7. Keep existing v1 schema/hash tests unchanged and prove family payload is covered by existing artifact integrity. Corruption or absent payload blocks rendering success.
8. Prove eligibility using a completed verified run with a family-owned result for every planned job; separately prove that a pre-result orchestration/preparation failure and a not-run planned job produce no fabricated family result/classification and cannot be reported as successful conforming output by execute or render mode.
9. Check output syntax/round-trip, Markdown/HTML fact completeness and order, non-color labels, HTML escaping, and keyboard operation of any added controls.
10. Verify actual host `invoke` and image still perform one isolated invocation per call.
11. Verify that selecting a non-OpenCode target transport and, separately, a non-OpenCode judge transport in built-in mode is rejected before any invocation. Verify that this built-in restriction does not alter existing `--profile` transport flexibility.
12. Without launching an OCI container or contacting a registry, exercise image-guard adapter tests for absent selection, tag-only/mutable reference, nonlocal identity, unknown/unreadable version or adapter metadata, version mismatch, adapter mismatch, and accepted full-ID/digest identities. Prove rejection precedes every OCI `run`, each accepted target/judge spec preserves the exact selected identity, and every resulting engine command sets pull-never. Prove the preflight lookup is local-only and profile-mode image selection remains unchanged.
13. Run the public interface with repeated explicit skill inputs in differing source order. Verify no unlisted file is discovered, all skills resolve under one project root, per-input occurrence ordinals/paths/digests and each case's composite identity survive verified persistence and all formats, and result ordering follows input/source/iteration order. Include repeated skill names on distinct files and verify each case retains its exact originating source occurrence.
14. Submit disjoint case IDs for the same skill across files and verify acceptance; submit duplicate `(skill, case)` pairs in separate files and by repeating a case-bearing file and verify rejection before any target/judge invocation. Include skill/source IDs with colons, commas, quotes, backslashes, and non-ASCII characters; verify the encoded identities are distinct and each combined selector selects exactly one case. Include an invalid or unknown-skill child not selected by `--cases` and verify the complete submitted set still rejects before invocation.
15. With multiple skills, exercise `--all`, exact encoded `--cases` selection, and `--iterations N`; verify each selected composite case produces N separately identified results, comparisons remain within each skill/case, and no per-skill aggregate or cross-skill comparison appears. Separately verify the one-input legacy selector spelling remains unchanged.
16. Verify existing one-input skill arrays and `--skill NAME` remain supported. In combined mode, pair two raw-array files with two `--skill` occurrences in matching ordinal order; verify the resulting skill identities, provenance, duplicate checks, and v2 output. Repeat with object wrappers and matching bindings; mismatched binding count or wrapper identity rejects before invocation. Confirm `--profile` is unchanged and one-input output remains v1 with the existing selector spelling. Render the same verified combined run in all formats and compare summary, skills, cases, iterations, full captured answers/evidence, and input provenance.
17. Inspect Markdown and rendered HTML with at least two skills and five iterations per case. Confirm summary-first order, nested skill/case/iteration grouping, all five individually attributable statuses/comparisons, and that a selected iteration's complete captured answers/evidence and truncation/redaction state can be located without raw machine-data decoding. Confirm no per-skill or cross-skill aggregate appears.

## Open questions

| Question | Owner | Blocks |
| --- | --- | --- |
| Are external v1 consumers strict about additional `project_metadata.runner_eval` data, and what guarantees do they require? | User/product owner, informed by consumer inventory | Blocks external-consumer compatibility claims only; existing v1 schema/integrity and profile path remain specified. |
| Is compatibility with additional historical aliases or migration required? | User/product owner | Blocks only additional compatibility/migration commitments; the stated accepted shapes are implementation-ready. |
| Is a polished report beyond the accessible functional Markdown/HTML output required? | User/product owner | Blocks richer report only. |
| Is a named accessibility conformance level required beyond the observable requirements in OC-002? | Design owner/user if product promise changes | Blocks formal conformance-level claim only. |
