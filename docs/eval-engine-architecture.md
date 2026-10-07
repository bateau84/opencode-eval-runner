# Generic eval-engine extraction architecture

Issue: #58 — Task 1 of 9  
Status: architecture/extraction contract; no eval-engine implementation in this task.

## 1. Purpose

This document defines the internal boundary for extracting the proven generic orchestration mechanics from Loom's `scripts/run-evals.py` into `opencode-eval-runner`.

It is constrained by two inventories merged into this branch:

- [Loom eval runner responsibility inventory](loom-eval-runner-responsibility-inventory.md)
- [Runner contract and invariant matrix](eval-engine-runner-contracts.md)

The design deliberately does **not** turn this repository into the owner of project-specific eval semantics. It provides reusable orchestration over the existing one-invocation runner boundary.

The target ownership split is:

```text
project/profile
  cases / fixtures / prompts / assertions / judge semantics / thresholds
                     |
                     v
generic eval engine
  selection / iterations / concurrency / attempts / readiness
  target -> judge -> classification / artifacts / summaries
                     |
                     v
invoke
  exactly one isolated invocation
                     |
                     v
opencode-eval-runner/v1
  + authoritative runtime_evidence/v1
```

## 2. Non-negotiable invariants

1. **One `invoke` means exactly one isolated invocation.**
2. **No hidden retry loop may be added to `invoke`.**
3. Retry is orchestration policy and every attempt must be visible in artifacts.
4. `opencode-eval-runner/v1` remains the low-level invocation result envelope.
5. `opencode-eval-runner/runtime-evidence/v1` is the only authoritative runtime-evidence object.
6. Runtime evidence readiness is scoped to the facts a project assertion requires.
7. Diagnostic/convenience fields cannot repair missing authoritative runtime evidence.
8. Product outcome, evidence outcome, and infrastructure outcome remain distinct.
9. Project/profile code owns what correct behavior means.
10. No universal assertion DSL is introduced.
11. No input-JSON invocation API is introduced.
12. No public `eval` CLI is introduced by Task 1.
13. Copilot runtime observation remains explicitly unsupported.
14. Code Mode exact caller-final value/error remains explicitly unsupported on stock OpenCode 2.0.23.
15. The normal trust profile remains trusted-checkout, not hostile-plugin isolation.
16. Loom's old direct-container fallback and old observer/evidence reconstruction paths are not migrated.

## 3. Responsibility boundary

### 3.1 Generic eval-engine responsibility

The generic engine owns mechanics that do not depend on Loom's domain:

- normalized case/run identity;
- selectors over already-normalized cases;
- explicit spend/selection safeguards;
- case x iteration job expansion;
- stable case/iteration labels;
- general and runtime execution lanes;
- bounded concurrency planning;
- target attempt orchestration;
- explicit retry policy and attempt accounting;
- runtime-evidence readiness mechanics;
- judge attempt orchestration;
- generic tri-state classification precedence;
- run/case timing;
- durable run/case artifacts;
- artifact integrity verification;
- run summary and process-level success/failure;
- preservation of transport/model/reasoning/image provenance.

### 3.2 Project/profile responsibility

A project integration such as Loom owns:

- case discovery and source-file compatibility;
- case normalization into the generic case envelope;
- selector aliases beyond the canonical case ID;
- whether a case belongs to the standard or runtime concurrency lane;
- fixture construction;
- workspace contents and writable/read-only policy;
- target agent/skill/profile selection;
- target prompt construction;
- invocation-specific config/mount/network choices;
- which runtime-evidence boundaries a case/assertion requires;
- locating the observations/fields relevant to a project assertion;
- deterministic behavioral assertions;
- judge prompt/rubric construction;
- judge result parsing and validation;
- semantic pass/fail meaning;
- project-specific scores, traps, thresholds, metadata, and reporting details;
- skill-ablation meaning and comparison policy.

### 3.3 Low-level `invoke` responsibility

The existing invocation boundary continues to own:

- OCI process construction and isolation;
- workspace/input/config/credential mounting;
- transport selection;
- provider authentication forwarding;
- inner invocation timeout;
- host/container timeout behavior;
- raw transport execution;
- result construction;
- result JSON parsing/validation;
- evidence sanitization before runner-controlled sinks;
- authoritative OpenCode runtime observation;
- `runtime_evidence/v1` construction and validation;
- output-file persistence for one invocation.

The eval engine must reuse this implementation path rather than create another container runner.

### 3.4 Legacy/compatibility behavior that must not migrate

The following Loom-side mechanisms are explicitly excluded from the generic engine:

- direct OCI/container execution fallback when the runner binary is unavailable;
- Loom-side `evidence_safety` eligibility as a competing authority;
- `observed_tool_results` as runtime evidence authority;
- reconstruction from `tool_result_evidence`, stdout/stderr, or model output;
- nested Code Mode reconstruction from diagnostic surfaces;
- `.loom-eval-tool-observer.jsonl` as scoring authority;
- the candidate runner-safety/private-policy adapter;
- disposable-state/candidate-image admission machinery from the superseded trust direction;
- old exact/redacted/omitted Loom evidence vocabulary as a competing runtime contract.

Diagnostic compatibility output may remain in Loom during migration, but it cannot authorize PASS.

## 4. Internal package/module decomposition

The following decomposition is authoritative for Tasks 2-5 unless implementation detail forces a narrow rename. Responsibilities should not migrate between these modules without updating this architecture.

```text
runner/
  eval_types.py          shared internal dataclasses/enums/protocol values
  eval_plan.py           selection, iteration expansion, concurrency plan
  eval_artifacts.py      run/case persistence, schemas, integrity
  eval_evidence.py       canonical evidence-readiness mechanics
  eval_execute.py        target/judge attempt execution and retry plumbing
  eval_judge.py          judge lifecycle + generic classification
  eval_engine.py         composition/orchestration only
```

Task mapping:

- **Task 2 / #59:** `eval_types.py` planning subset + `eval_plan.py`
- **Task 3 / #60:** artifact subset of `eval_types.py` + `eval_artifacts.py`
- **Task 4 / #61:** evidence/execution subset + `eval_evidence.py` + `eval_execute.py`
- **Task 5 / #62:** judge/classification subset + `eval_judge.py` + minimal `eval_engine.py` composition

No task should need to redesign the ownership boundary to proceed.

## 5. Core internal contracts

These are internal Python contracts, not a new public wire protocol.

### 5.1 JSON-compatible project metadata

Generic artifacts may carry project-owned metadata, but the generic engine must not interpret it.

```python
JsonValue = None | bool | int | float | str | list["JsonValue"] | dict[str, "JsonValue"]
```

Values written to durable artifacts must be strict JSON-compatible values.

### 5.2 NormalizedCase

```python
@dataclass(frozen=True)
class NormalizedCase:
    id: str
    selectors: tuple[str, ...]
    lane: Literal["standard", "runtime"]
    project_data: JsonValue
    metadata: dict[str, JsonValue]
```

Rules:

- `id` is globally unique within one normalized suite.
- `selectors` may contain project-defined aliases but always includes `id`.
- `lane` is scheduling metadata only. It does not imply behavioral meaning.
- `project_data` is opaque to the generic engine.
- the generic engine must not require Loom fields such as `agent`, `execution`, `requirements`, `trap`, or `expectations`.

### 5.3 EvalJob

```python
@dataclass(frozen=True)
class EvalJob:
    case: NormalizedCase
    iteration: int
    label: str
```

`label` is stable for the same case/iteration plan:

- one iteration: `<case-id>`
- multiple iterations: `<case-id>#<iteration>`

### 5.4 RunPlan

```python
@dataclass(frozen=True)
class RunPlan:
    run_id: str
    jobs: tuple[EvalJob, ...]
    standard_parallelism: int
    runtime_parallelism: int
```

Task 2 may add normalized selector/planning metadata, but execution semantics remain:

- case x iteration expansion is deterministic;
- standard and runtime jobs are planned separately;
- runtime parallelism is independently bounded;
- current Loom behavior of running the standard group before the runtime group is the initial generic ordering because it avoids mixing normal throughput with runtime stress;
- a future public interface may later expose another scheduling policy, but Tasks 2-5 should not invent one.

### 5.5 InvocationSpec

```python
@dataclass(frozen=True)
class InvocationSpec:
    transport: Literal["opencode", "github-copilot-cli"]
    model: str
    reasoning: str | None
    agent: str | None
    skill: str | None
    workspace: Path
    workspace_mode: Literal["ro", "rw"]
    prompt: str
    system: str | None
    expected_plugin: str | None
    engine: str
    network: str | None
    image: str | None
    auth: Path | None
    database: Path | None
    models_catalog: Path | None
    config: Path | None
    config_root: Path | None
    env_names: tuple[str, ...]
    timeout_seconds: int
    container_timeout: int
```

This is a logical internal orchestration structure. It is **not** an input JSON API.

The default invoker adapter must execute through the same host `invoke` implementation/semantics used by the public CLI. It may factor common Python code out of `runner.cli.invoke()`, but it must not duplicate OCI construction or invoke the transport container directly.

### 5.6 AttemptFailure

```python
@dataclass(frozen=True)
class AttemptFailure:
    plane: Literal["infrastructure", "product", "evidence"]
    code: str
    message: str
    retry_safe: bool
```

`retry_safe` is a fact established by the attempt classifier, not permission to retry. Policy still decides whether another attempt is allowed.

Examples of infrastructure codes may include:

- outer container timeout;
- missing result file;
- invalid/non-object result JSON;
- failed workspace/config/plugin preflight.

Product failure remains distinct, for example:

- transport/model non-zero result;
- inner model timeout represented by `result.exit_code == 124`.

Evidence failure is scoped to a declared evidence requirement, not inferred from product status.

### 5.7 AttemptRecord

```python
@dataclass(frozen=True)
class AttemptRecord:
    attempt: int
    started_at: str
    duration_seconds: float
    host_exit_code: int | None
    result: dict[str, JsonValue] | None
    failure: AttemptFailure | None
```

Every actual call to `invoke` produces one AttemptRecord, including failed attempts where no valid result exists.

### 5.8 RetryPolicy / RetryDecision

Retry remains orchestration policy:

```python
class RetryPolicy(Protocol):
    def decide(
        self,
        attempts: tuple[AttemptRecord, ...],
        latest: AttemptRecord,
    ) -> "RetryDecision": ...

@dataclass(frozen=True)
class RetryDecision:
    retry: bool
    reason: str
    delay_seconds: float
```

Requirements:

- default internal behavior is no hidden retry unless a policy is explicitly supplied;
- max attempts/backoff are bounded;
- every prior attempt is retained;
- a behavioral FAIL is never retried as infrastructure;
- replay safety must fail closed;
- convenience `tools`/`actions` must not be used as authoritative proof that no side effect occurred;
- if retry safety depends on whether execution reached a runtime tool boundary, use authoritative `runtime_evidence` when available;
- if safety cannot be established, do not retry.

The narrow Loom `provider.no-route` + `Model unavailable` behavior is reference policy, not a hard-coded engine semantic.

### 5.9 EvidenceRequirement

The engine needs a generic way to decide capture/boundary readiness without owning behavioral assertions.

```python
@dataclass(frozen=True)
class EvidenceRequirement:
    boundaries: tuple[
        Literal["native", "code_mode_execution", "code_mode_finality"],
        ...
    ]
```

A profile chooses the required boundary set for a case or individual project check.

The generic engine does **not** define a selector/assertion DSL for observations. Project checks locate the observation and exact field they care about.

### 5.10 EvidenceReadiness

```python
@dataclass(frozen=True)
class EvidenceReadiness:
    status: Literal["ready", "incomplete", "unsupported", "invalid"]
    reasons: tuple[str, ...]
    required_boundaries: tuple[str, ...]
```

`eval_evidence.py` exposes two levels of reusable mechanics:

1. **capture/boundary readiness**

```python
check_evidence_readiness(
    runtime_evidence: Mapping[str, Any],
    requirement: EvidenceRequirement,
) -> EvidenceReadiness
```

2. **exact field readiness**

```python
check_field_readiness(field: Mapping[str, Any]) -> EvidenceReadiness
```

Rules:

- valid `runtime_evidence/v1` is mandatory;
- overall `incomplete` or `invalid` makes any non-empty runtime requirement not ready;
- every required boundary must be `complete`;
- a required boundary that is `unsupported` yields `unsupported`;
- exact field state `available` is ready;
- exact field `redacted` or `omitted` yields incomplete for that exact-value project check;
- exact field `unsupported` yields unsupported;
- an empty boundary requirement is allowed for cases/checks that do not depend on runtime evidence;
- diagnostics never backfill an unavailable authoritative field.

This separation avoids a universal assertion DSL: the generic engine decides whether declared evidence is usable, while project code decides what fact to ask for and what it means.

### 5.11 CheckOutcome

Project deterministic checks normalize into:

```python
@dataclass(frozen=True)
class CheckOutcome:
    name: str
    status: Literal["pass", "fail", "non-evidence"]
    reason: str
    metadata: dict[str, JsonValue]
```

The generic engine does not know how a check was computed.

A profile may use authoritative runtime evidence, product text, repository data, or other project evidence as appropriate. It must not use diagnostic fields to substitute for missing authoritative runtime facts.

### 5.12 SemanticDecision

```python
@dataclass(frozen=True)
class SemanticDecision:
    status: Literal["pass", "fail"]
    summary: str
    data: JsonValue
```

Judge parse/contract failure is not represented as a semantic FAIL. It is a judge attempt/infrastructure failure and therefore non-evidence.

### 5.13 EvaluationResult

```python
@dataclass(frozen=True)
class EvaluationResult:
    classification: Literal["pass", "fail", "non-evidence"]
    target_attempts: tuple[AttemptRecord, ...]
    target_readiness: EvidenceReadiness
    deterministic_checks: tuple[CheckOutcome, ...]
    judge_attempts: tuple[AttemptRecord, ...]
    semantic: SemanticDecision | None
    project_metadata: dict[str, JsonValue]
```

The durable artifact adds case/run identity and timing.

## 6. Project/profile extension protocol

The project extension surface is intentionally small and imperative. It is not a declarative assertion language.

Conceptually:

```python
class EvalProfile(Protocol):
    def discover_cases(self) -> Sequence[NormalizedCase]: ...

    @contextmanager
    def prepare(
        self,
        case: NormalizedCase,
        iteration: int,
    ) -> Iterator[Any]:
        ...

    def target_spec(
        self,
        case: NormalizedCase,
        prepared: Any,
    ) -> InvocationSpec:
        ...

    def target_evidence_requirement(
        self,
        case: NormalizedCase,
        prepared: Any,
    ) -> EvidenceRequirement:
        ...

    def deterministic_checks(
        self,
        case: NormalizedCase,
        prepared: Any,
        target: AttemptRecord,
        readiness: EvidenceReadiness,
    ) -> Sequence[CheckOutcome]:
        ...

    def judge_spec(
        self,
        case: NormalizedCase,
        prepared: Any,
        target: AttemptRecord,
        checks: Sequence[CheckOutcome],
    ) -> InvocationSpec | None:
        ...

    def parse_judge(
        self,
        case: NormalizedCase,
        prepared: Any,
        judge: AttemptRecord,
    ) -> SemanticDecision:
        ...

    def artifact_metadata(
        self,
        case: NormalizedCase,
        prepared: Any,
    ) -> Mapping[str, JsonValue]:
        ...
```

Narrow implementation changes are allowed, but the ownership rules are fixed:

- `prepare` owns project workspace/fixture lifecycle;
- target/judge specs are project-produced;
- project code declares runtime evidence needs;
- deterministic checks and semantic meaning remain project-owned;
- generic code owns attempts, retries, readiness mechanics, classification precedence, scheduling, and artifacts.

A profile may return `None` from `judge_spec` for deterministic-only cases.

Skill ablation is **not** implemented in Tasks 2-5. The normal target/judge lifecycle should be factored so Task 8 can compose the same phase primitive twice rather than duplicate execution.

## 7. One-case lifecycle

The generic normal-case lifecycle is:

```text
NormalizedCase + iteration
        |
        v
profile.prepare()
        |
        v
profile.target_spec()
        |
        v
execute target attempts
  one invoke per attempt
        |
        v
profile.target_evidence_requirement()
        |
        v
generic evidence readiness
        |
        v
profile.deterministic_checks()
        |
        +-------------------------------+
        |                               |
        v                               |
profile.judge_spec()                    |
        |                               |
        | None                          | InvocationSpec
        |                               v
        |                       execute judge attempts
        |                               |
        |                               v
        |                       profile.parse_judge()
        |                               |
        +-------------------------------+
                        |
                        v
             generic classification
                        |
                        v
               durable artifact
```

### 7.1 Target invocation usability

A target is unusable/non-evidence when the engine cannot obtain a valid target result required for the case, for example:

- outer OCI timeout;
- invalid result JSON;
- failed required plugin/runtime preflight;
- exhausted retryable infrastructure failure;
- product/model timeout or error when the profile requires a completed target response;
- declared runtime evidence requirement is not ready.

The profile may still have deterministic-only cases that do not require runtime evidence. An empty `EvidenceRequirement` means runtime status such as Copilot `unsupported` does not by itself block a purely semantic/textual case.

### 7.2 Judge execution

If the target is usable enough to judge, the engine should not automatically skip the judge merely because deterministic checks already contain a behavioral failure. Loom currently retains both deterministic and semantic evidence, and the generic engine should preserve that diagnostic value.

The profile can explicitly return no judge for deterministic-only cases.

### 7.3 Classification precedence

Generic final classification is:

1. required target execution/infrastructure failure -> **non-evidence**
2. required target evidence readiness failure -> **non-evidence**
3. required judge execution or judge-contract failure -> **non-evidence**
4. any deterministic `fail` -> **fail**
5. otherwise any deterministic `non-evidence` -> **non-evidence**
6. semantic decision `fail` -> **fail**
7. semantic decision `pass` (or no judge required) and all required deterministic checks pass -> **pass**

This preserves the important distinction:

- inability to prove required behavior is not a behavioral failure;
- an observed valid behavioral violation is a real FAIL;
- judge parser/contract failure is not evidence against the product.

If a project needs a different domain scoring model, it should normalize its domain-specific results into `CheckOutcome` and `SemanticDecision`; it should not replace the generic infrastructure/evidence precedence.

## 8. Run planning and concurrency contract

Task 2 implements planning over normalized cases.

### 8.1 Selection

The planner accepts:

- normalized cases from the profile;
- canonical case IDs and profile-provided selectors;
- explicit selection/all intent;
- iteration count;
- standard parallelism;
- runtime parallelism.

It must reject:

- duplicate normalized IDs;
- unknown selectors;
- iteration < 1;
- invalid concurrency values;
- live execution with no explicit selection/all intent.

Listing cases is provider-free and does not require model configuration.

### 8.2 Job expansion

For selected cases:

```python
jobs = [
    EvalJob(case, iteration)
    for case in selected_cases
    for iteration in range(1, iterations + 1)
]
```

The planner never executes jobs.

### 8.3 Concurrency lanes

Profiles assign each case to `standard` or `runtime`.

Initial generic scheduling preserves Loom's proven separation:

1. execute the standard group with standard parallelism;
2. execute the runtime group with independently bounded runtime parallelism.

The generic reason is resource/load separation. Loom's reason that a runtime case may itself dispatch multiple subagents remains project context, not engine semantics.

The planner records resolved concurrency in run metadata so artifacts explain how the run was scheduled.

## 9. Retry contract

Retry is performed by `eval_execute.py`, never by `invoke`.

For each phase:

```text
attempt 1 -> classify attempt -> RetryPolicy
                         | no
                         v
                     final attempt
                         |
                        yes
                         v
                    delay/backoff
                         |
                         v
attempt 2 -> ...
```

Required behavior:

- attempt numbering starts at 1;
- max attempts are bounded;
- each attempt calls `invoke` once;
- all attempts survive in the final artifact;
- retry reasons and delay are recorded;
- a success after retry does not erase earlier failures;
- no retry occurs after a valid behavioral result merely because the result would fail the eval;
- replay safety is conservative.

Task 4 may provide a built-in narrow transient-provider policy based on the proven Loom policy, but it must remain explicitly selected/configured rather than hidden in `invoke`.

## 10. Artifact contract

Task 3 implements durable artifacts before Task 4/5 execution is wired in.

Two versioned on-disk schemas are chosen from the start:

- `opencode-eval-runner/eval-run/v1` — run manifest/summary
- `opencode-eval-runner/eval-artifact/v1` — one case/iteration result

These are versioned internal/on-disk contracts during Tasks 2-5. They are not promised as stable external/public API until Task 6 reviews the public `eval` interface.

### 10.1 Run manifest minimum fields

```json
{
  "schema": "opencode-eval-runner/eval-run/v1",
  "run_id": "...",
  "created_at": "...",
  "selection": {},
  "iterations": 1,
  "concurrency": {
    "standard": 1,
    "runtime": 1
  },
  "jobs": [],
  "summary": {}
}
```

### 10.2 Per-job artifact minimum fields

```json
{
  "schema": "opencode-eval-runner/eval-artifact/v1",
  "run_id": "...",
  "case": "...",
  "iteration": 1,
  "lane": "standard",
  "classification": "pass",
  "timing": {},
  "target": {
    "attempts": [],
    "evidence_readiness": {}
  },
  "deterministic_checks": [],
  "judge": {
    "attempts": [],
    "semantic": null
  },
  "project_metadata": {},
  "artifact_evidence_id": "..."
}
```

Rules:

- full validated low-level target/judge results are preserved inside their AttemptRecords;
- prior retry attempts are retained;
- runtime evidence is stored exactly as returned; artifact code does not rewrite it;
- project metadata is opaque JSON;
- artifacts use atomic replace where supported;
- an artifact evidence ID is calculated over a canonical serialized form excluding the evidence ID itself;
- reporting/counting re-reads and verifies durable artifacts before trusting them;
- run directories fail closed on conflicting ownership/non-empty incompatible contents.

Task 3 may refine field names but must preserve these semantics.

## 11. Timeout model

The engine must distinguish:

### Inner invocation timeout

Owned by `invoke --timeout-seconds`.

A valid result may exist with:

- `result.exit_code == 124`
- `timed_out == true`
- timeout-aware `runtime_evidence`

The orchestration layer records the result and classifies it according to phase requirements. It must not call it behavioral FAIL merely because time expired.

### Outer container timeout

Owned by `invoke --container-timeout`.

A valid result may not exist. This is infrastructure/non-evidence and may be eligible for explicit orchestration retry only if replay safety is established.

### Eval-engine scheduling timeout

No new global wall-clock timeout is introduced in Tasks 2-5. A later public eval CLI may add one explicitly if needed.

## 12. Judge contract

The generic engine has no universal judge JSON schema.

The profile owns:

- judge system instructions;
- judge prompt;
- expected output schema;
- parser;
- schema/contract validation;
- semantic interpretation.

The generic engine owns:

- running the judge via `invoke`;
- retry/timeout/infrastructure handling;
- preserving judge result provenance;
- distinguishing judge transport/contract failure from semantic FAIL.

Loom's current strict JSON judge contract is a project adapter reference, not the generic schema.

## 13. Skill-ablation extension boundary

Loom skill-owned evals prove a future case may require:

```text
baseline target -> baseline judge
candidate target -> candidate judge
comparison
```

Tasks 2-5 implement only the normal single target/judge lifecycle.

However, code must be factored so the phase primitive can be reused:

```python
run_evaluation_phase(
    invocation_spec,
    evidence_requirement,
    retry_policy,
) -> PhaseOutcome
```

Task 8 can compose two such phases and a project-owned comparison callback.

Do not add baseline/candidate fields to `NormalizedCase` or hard-code skill/trap/score semantics now.

## 14. Error taxonomy

Generic error codes should be stable enough for artifacts/tests but not overfit Loom strings.

Minimum categories:

### Infrastructure

- `invoke_outer_timeout`
- `invoke_no_result`
- `invoke_invalid_result`
- `invoke_preflight_failed`
- `profile_prepare_failed`
- `judge_contract_invalid`

### Product

- `product_error`
- `product_timeout`

### Evidence

- `evidence_incomplete`
- `evidence_invalid`
- `evidence_unsupported`
- `evidence_field_unavailable`

Task implementations may add narrower codes but must preserve the three-plane taxonomy.

## 15. Reporting and exit semantics

Task 5 may provide internal summary helpers but no public `eval` CLI yet.

Internal summary semantics:

- PASS corresponds to classification `pass`;
- FAIL corresponds to classification `fail`;
- ERROR/non-evidence corresponds to `non-evidence`;
- a run succeeds only if every selected job is `pass`;
- reporting happens from verified durable artifacts where artifacts are enabled.

Human-readable formatting remains replaceable; durable artifacts are the stronger resumption/debugging surface.

## 16. Explicit migration mapping from Loom

| Current Loom responsibility | Destination |
| --- | --- |
| behavioral/skill case discovery | Loom profile |
| normalization of historical skill formats | Loom profile |
| case IDs/selectors | profile produces `NormalizedCase`; generic selection uses them |
| setup_projects / setup_skill_ablation_projects | Loom profile `prepare` |
| target agent wrappers | Loom profile |
| runner/container invocation | existing low-level `invoke` |
| direct-container fallback | remove/do not migrate |
| Loom observer attachment | remove as authority/do not migrate |
| tool-result reconstruction | remove as authority/do not migrate |
| runner-safety candidate adapter | remove/do not migrate |
| invoke_container_with_retry loop | generic `eval_execute` with explicit policy |
| provider.no-route predicate | optional policy/reference, not hidden engine rule |
| target_scoring_evidence_error legacy checks | replace with runtime-evidence requirements + profile checks |
| deterministic_failures | Loom profile returning `CheckOutcome` |
| judge_prompt | Loom profile |
| parse_judge / judge_contract_error | Loom profile |
| semantic_pass | Loom profile returning `SemanticDecision` |
| classify_behavioral_result | generic classifier over normalized outcomes |
| artifact run claim/write/hash/verify | generic artifact module |
| case x iteration expansion | generic planner |
| standard/runtime concurrency | generic planner; profile assigns lane |
| skill ablation orchestration | Task 8 generic paired mode + Loom comparison policy |
| console formatting | thin project/public CLI layer; not core semantics |

## 17. Task handoff

### Task 2 / #59 may proceed with

- `NormalizedCase`
- `EvalJob`
- `RunPlan`
- explicit-selection safeguards
- stable labels
- standard/runtime lanes
- deterministic case x iteration expansion
- separated concurrency resolution

It must not execute models or create artifacts.

### Task 3 / #60 may proceed with

- run and per-job artifact schemas;
- directory claiming;
- stable artifact paths;
- atomic writes;
- canonical hash/integrity verification;
- opaque project metadata;
- preserving future target/judge/readiness/check data without interpreting it.

### Task 4 / #61 may proceed with

- `InvocationSpec`
- `AttemptRecord`
- three-plane `AttemptFailure`
- `RetryPolicy`
- `EvidenceRequirement`
- `EvidenceReadiness`
- boundary and exact-field readiness helpers;
- target phase execution over the existing `invoke` path.

### Task 5 / #62 may proceed with

- judge phase execution using the same attempt machinery;
- profile judge construction/parsing;
- `CheckOutcome`
- `SemanticDecision`
- generic classification precedence;
- minimal one-case `eval_engine` composition;
- provider-free complete-lifecycle test doubles.

No one of Tasks 2-5 should need to choose a new ownership model.

## 18. Deferred decisions

These are deliberately deferred, not missing from Task 1:

- public `eval` CLI syntax — Task 6;
- external suite/profile loading mechanism — Task 6;
- whether the internal artifact schemas become stable public schemas — Task 6;
- exact public retry defaults — Task 6;
- Loom migration adapter details — Task 7;
- generic baseline/candidate ablation mode — Task 8;
- final removal of Loom duplicated orchestration — Task 9;
- repository/product rename — separate product decision;
- input JSON request API — no current requirement.

## 19. Architecture acceptance check

This design satisfies issue #58 because:

- every major Loom runner responsibility has an explicit owner;
- the generic target -> readiness -> judge -> classification -> artifact lifecycle is defined;
- retry ownership and replay-safety constraints are explicit;
- inner/outer timeout ownership is explicit;
- iteration/concurrency planning is explicit;
- artifacts have an implementable versioned internal shape;
- project extension points are explicit without creating an assertion DSL;
- `invoke` remains exactly one isolated invocation;
- `runtime_evidence/v1` remains the sole runtime authority;
- legacy Loom evidence and direct-container paths are explicitly excluded;
- Tasks 2-5 have concrete module/type handoffs and can proceed independently.
