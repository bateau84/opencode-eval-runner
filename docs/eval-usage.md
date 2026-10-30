# Public eval CLI and profile reference

> **Current interface:** `eval` has three mutually exclusive modes: the existing `--profile MODULE:ATTRIBUTE` mode, built-in execution with explicit `--input PATH --family agent-runtime|skill` arguments, and persisted-run rendering with `--render-run RUN_DIRECTORY`. Skill mode accepts one or more explicitly supplied input files. Built-in target and judge transport is OpenCode-only; existing profile mode keeps its transport flexibility. Use [ARS-001](architecture/eval-format-ownership/specifications/ars-001-runner-eval-contract.md) for the normative accepted input fields and family semantics. Built-in output is one selected JSON, YAML, Markdown, or HTML view rendered from verified persisted records. Markdown and HTML use a readable result hierarchy; they do not add grading semantics or make a provider/spend compatibility guarantee.

## Built-in runner-owned inputs and output

Built-in mode does not load an external `EvalProfile`. It reads explicitly supplied JSON input file(s) and requires an explicit `--family`; it does not scan directories, discover files, or infer family from file shape/name. The supported families are the `agent-runtime/v1` suite and the specified `skill-cases/v1` shapes only. Agent/runtime mode accepts exactly one input. Skill mode accepts one input for the existing one-skill path or multiple inputs for a combined skill-family run; each input occurrence is explicit. Invalid or ambiguous input is rejected before invocation. For skill-family inputs, the runner uses the baseline-target, baseline-judge, candidate-target, candidate-judge paired ablation lifecycle; expectations, negative expectations and trap semantics remain skill-owned.

```bash
opencode-eval-runner eval --input cases.json --family agent-runtime \
  --target-model openai/gpt-5.6 --cases CASE-01 --format markdown

# Combine two skill inputs. Each --skill binds to the --input at the same
# position; wrapper identities must agree with their bindings.
opencode-eval-runner eval \
  --input skills/python-testing/evals/evals.json --skill python-testing \
  --input skills/python-error-handling/evals/evals.json --skill python-error-handling \
  --family skill --all --iterations 5 \
  --target-model '<provider/model>' --format html

# Render a previously completed run without invoking a model:
opencode-eval-runner eval --render-run .opencode-evals/RUN_ID --format html
```

Built-in mode requires `--target-model`, uses OpenCode for every target/judge phase, and rejects a non-OpenCode transport request before invocation. Live built-in execution also requires the caller to set `OPENCODE_EVAL_RUNNER_OPENCODE_IMAGE` to a compatible full local image ID or digest-qualified identity. The runner checks that identity and the OpenCode-version/invocation-adapter labels against the selected local engine's metadata without pulling or contacting a registry; tags, absent local images, incompatible metadata, and remote engine endpoints fail closed. The exact selection is preserved for every target and judge OCI run, which uses pull-never. Existing `--profile` image resolution is unchanged. Built-in evaluation resolves one validated catalog snapshot before scheduling, then shares it across all phases, iterations and retries. `--models-catalog` overrides `OPENCODE_EVAL_RUNNER_MODELS`; otherwise the runner downloads `https://models.opencode.ai/api.json`. An acquisition or validation failure is a preparation error before invocation. OpenCode receives the snapshot through its supported file setting with background fetching disabled. OpenCode provider/model configuration continues through the existing `invoke` path; the built-in interface does not claim cross-provider transport compatibility. `--transport-retries` defaults to `0`; retries are opt-in and each permitted attempt is a separate `invoke`. One `invoke` and its image still perform exactly one isolated invocation.

For combined skill runs, repeat `--input PATH` and provide exactly one `--skill NAME` for each input occurrence, in the same order. Inputs are explicit; paths do not trigger directory scanning or discovery. A raw top-level case array gets its skill identity from the paired `--skill`; a wrapped input declares its identity and must agree with the paired binding. Repeated skill names are allowed when the case identities do not collide. Duplicate `(skill, case)` identities anywhere in the submitted inputs—including cases omitted by selection—reject the complete set before a target or judge invocation. `--all` selects all cases across the submitted inputs; `--cases` selects cases from that combined set. `--iterations 5` runs each selected case five times, with iterations separately attributed under their skill and case. The agent/runtime family remains single-input and cannot be mixed into a skill run.

Each invocation selects one format (`json`, `yaml`, `markdown`, or `html`; default JSON). `--output PATH` writes the representation, otherwise it is written to stdout; progress and diagnostics are separated from built-in representation output. `--render-run` verifies the persisted manifest/artifacts and never evaluates or invokes a model; use it with `--format` to select a saved-run view. A conforming output can be reported only for a completed, verified run where every planned case-iteration job has a family result. Pre-result orchestration/preparation errors and not-run jobs retain their terminal state without fabricated family results or classifications, and make the run ineligible for successful conforming output. Markdown and HTML present a readable hierarchy derived from that same verified result and include full case answers and evidence details in the report alongside individually visible iterations. JSON and YAML preserve the existing result semantics; combined runs use the specified v2 projection to carry input and skill/case identity, with no per-skill roll-up or cross-skill aggregate. Historical input aliases/migration and external v1 consumer compatibility are not promised.

For a combined skill run, the result hierarchy is run → skill → case → iteration. Each skill/case retains its own baseline/candidate comparison at each iteration. The run summary counts planned case-iteration jobs; the output does not create per-skill summary objects or aggregate comparisons across skills. One-input skill runs retain the existing v1 output and selector spelling; combined inputs use `opencode-eval-runner/eval-output/v2`. Rendering a saved run uses the persisted inputs/results and does not re-evaluate it. See the [combined skill report baseline](design/eval-format-ownership/multiskill-readable-report-baseline.md) for the accepted readable hierarchy; it is a design reference, not a separate output contract.

Family-specific judge gates differ: agent/runtime judging runs only if the target is usable and every deterministic check passes; a deterministic fail or non-evidence check suppresses that judge. In skill ablation, a side judge is suppressed by non-evidence checks, but a behavioral fail alone does not suppress it. Classification and skill comparison rules are specified in ARS-001.

<code>opencode-eval-runner</code> has two public execution boundaries:

~~~text
opencode-eval-runner invoke ...
opencode-eval-runner eval ...
~~~

<code>invoke</code> still means **exactly one isolated model invocation**. It has no hidden retry loop.

In profile mode, <code>eval</code> is generic orchestration over one or more <code>invoke</code> attempts. The project supplies cases, fixtures, prompts, evidence requirements, deterministic checks, judge construction/parsing, semantic meaning, and opaque metadata through the frozen <code>EvalProfile</code> interface in <code>runner.eval_api</code>. Built-in modes instead use runner-owned family contracts and adapters described above.

The shared orchestration layer owns common selection, iterations, scheduling, attempts, evidence readiness, durable artifacts, summaries, and process exit status. Profile mode retains project-owned target/judge semantics; built-in family adapters own the accepted family-specific evaluation semantics.

## Existing profile mode

The existing `--profile` interface remains available, separately from the built-in modes. It preserves the profile's external case semantics and its existing transport flexibility; built-in OpenCode-only restrictions do not apply to it. New built-in-only controls (`--input`, `--family`, `--skill`, `--ablation`, `--format`, `--output`, `--render-run`) cannot be combined with profile mode.

## Profile loading

The public profile hook is explicit:

~~~text
--profile module:attribute
~~~

The attribute must already be an initialized object that implements the frozen <code>EvalProfile</code> methods. The loader does not execute arbitrary profile files, call factories, or perform implicit discovery.

For example:

~~~bash
opencode-eval-runner eval \
  --profile myproject.eval_profile:PROFILE \
  --list
~~~

The module must be importable by the Python process running the CLI. A repository can normally make its profile importable by running from the repository root with the repository on <code>PYTHONPATH</code>, or by installing its Python package.

The stable profile API is:

- <code>discover_cases()</code>
- <code>prepare(case, iteration)</code>
- <code>target_spec(case, prepared)</code>
- <code>target_evidence_requirement(case, prepared)</code>
- <code>deterministic_checks(case, prepared, target, readiness)</code>
- <code>judge_spec(case, prepared, target, checks)</code>
- <code>parse_judge(case, prepared, judge)</code>
- <code>artifact_metadata(case, prepared)</code>

Use the normalized public types exported by <code>runner.eval_api</code>. The runner does not define a universal assertion language or judge JSON schema.

## Listing cases

Listing is provider-free:

~~~bash
opencode-eval-runner eval \
  --profile myproject.eval_profile:PROFILE \
  --list
~~~

Output is tab-separated:

~~~text
CASE-01    standard    smoke,fast
RUNTIME-01 runtime     runtime
~~~

The columns are canonical case ID, execution lane, and non-canonical selector aliases. <code>--list</code> performs discovery/validation only. It does not call <code>prepare</code>, construct invocation specs, or run target/judge inference.

## Spend safeguard and selection

A live eval never means "all cases" implicitly.

Use explicit selectors:

~~~bash
opencode-eval-runner eval \
  --profile myproject.eval_profile:PROFILE \
  --cases CASE-01,CASE-02
~~~

<code>--cases</code> accepts canonical IDs or profile aliases and may be repeated.

Or explicitly select everything:

~~~bash
opencode-eval-runner eval \
  --profile myproject.eval_profile:PROFILE \
  --all
~~~

A live command with neither <code>--cases</code> nor <code>--all</code> is rejected before <code>prepare</code> or any model invocation. Unknown selectors are also rejected before inference.

## CLI reference

| Option | Default | Meaning |
| --- | --- | --- |
| <code>--profile MODULE:ATTRIBUTE</code> | Required in profile mode | Initialized external <code>EvalProfile</code> export. |
| <code>--list</code> | Off | List normalized cases and exit without provider calls. |
| <code>--all</code> | Off | Explicitly select all discovered cases. |
| <code>--cases SELECTOR[,SELECTOR...]</code> | None | Explicit case/alias selection. Repeatable. |
| <code>--iterations N</code> | <code>1</code> | Run each selected case N times. |
| <code>--parallel [N]</code> | <code>1</code> | Standard-lane concurrency. Bare <code>--parallel</code> means all planned standard jobs may run concurrently. |
| <code>--runtime-parallel N</code> | <code>1</code> | Independent runtime-lane concurrency. |
| <code>--target-transport TRANSPORT</code> | Profile value | Override target transport with <code>opencode</code> or <code>github-copilot-cli</code>. |
| <code>--judge-transport TRANSPORT</code> | Profile value | Override judge transport. |
| <code>--target-model MODEL</code> | Profile value | Override target model. |
| <code>--judge-model MODEL</code> | Profile value | Override judge model. |
| <code>--reasoning LEVEL</code> | Profile value | Common target/judge reasoning override. |
| <code>--target-reasoning LEVEL</code> | Common/profile value | Target-only reasoning override. |
| <code>--judge-reasoning LEVEL</code> | Common/profile value | Judge-only reasoning override. |
| <code>--engine {auto,podman,docker}</code> | Profile value | Override OCI engine for target and judge. |
| <code>--network MODE</code> | Profile value | Override OCI network mode/name for target and judge. |
| <code>--artifact-dir PATH</code> | <code>.opencode-evals/&lt;run-id&gt;</code> | Directory owned by this eval run. |
| <code>--timeout-seconds N</code> | Profile value | Override inner model invocation timeout. Must be at least 1. |
| <code>--container-timeout N</code> | Profile value | Override outer OCI process timeout. Must be at least 1. |
| <code>--transport-retries N</code> | <code>0</code> | Opt in to replay-safe transient provider retries. Range <code>0..5</code>. |

### Override precedence

The profile constructs complete target and judge <code>InvocationSpec</code> values. The CLI only changes fields that the caller explicitly overrides.

Reasoning precedence is:

~~~text
phase-specific override
  > --reasoning
  > profile InvocationSpec.reasoning
~~~

For example:

~~~bash
opencode-eval-runner eval \
  --profile myproject.eval_profile:PROFILE \
  --cases CASE-01 \
  --target-model openai/gpt-5.6 \
  --judge-model openai/gpt-5.6 \
  --reasoning medium \
  --judge-reasoning high
~~~

The target uses <code>medium</code>; the judge uses <code>high</code>.

<code>--engine</code>, <code>--network</code>, <code>--timeout-seconds</code>, and <code>--container-timeout</code> apply to both target and judge when supplied. Otherwise the profile-produced values remain unchanged.

## Iterations and concurrency lanes

Profiles assign every normalized case to either the <code>standard</code> or <code>runtime</code> lane.

The public scheduler preserves the generic engine contract:

1. run the standard group with resolved <code>--parallel</code>;
2. then run the runtime group with resolved <code>--runtime-parallel</code>.

Examples:

~~~bash
# Sequential standard and runtime jobs.
opencode-eval-runner eval \
  --profile myproject.eval_profile:PROFILE \
  --all
~~~

~~~bash
# Up to four standard jobs at once; runtime remains serialized.
opencode-eval-runner eval \
  --profile myproject.eval_profile:PROFILE \
  --all \
  --iterations 3 \
  --parallel 4
~~~

~~~bash
# Allow all standard jobs concurrently and up to two runtime jobs.
opencode-eval-runner eval \
  --profile myproject.eval_profile:PROFILE \
  --all \
  --parallel \
  --runtime-parallel 2
~~~

A profile that keeps mutable shared state must make its hooks safe for the concurrency the caller requests. <code>prepare</code> should normally create per-job fixture/workspace state.

## Explicit retries

<code>invoke</code> never retries.

The public eval command defaults to:

~~~text
--transport-retries 0
~~~

A non-zero value opts into the runner's narrow <code>TransientProviderRetryPolicy</code>. It recognizes only the architecture-approved transient provider routing case and still retries only when authoritative runtime evidence proves the failed attempt is replay-safe.

The maximum number of actual attempts is:

~~~text
1 + --transport-retries
~~~

Every actual attempt is preserved in the per-job artifact together with retry decisions. Behavioral FAIL, product timeout/error, evidence failure, and any failure whose replay safety cannot be established are not made retryable by the flag.

Current public range:

~~~text
0..5
~~~

## Artifacts

Every live run claims one artifact directory. The default is:

~~~text
.opencode-evals/<generated-run-id>/
~~~

Layout:

~~~text
.opencode-evals/<run-id>/
  .eval-run-owner.json
  run.json
  jobs/
    case-<encoded-case-id>/
      iteration-1.json
      iteration-2.json
~~~

<code>run.json</code> uses <code>opencode-eval-runner/eval-run/v1</code>.

Each job artifact uses <code>opencode-eval-runner/eval-artifact/v1</code> and includes:

- target attempt history;
- canonical evidence readiness;
- deterministic check outcomes;
- judge attempt history and semantic decision when applicable;
- classification <code>pass | fail | non-evidence</code>;
- opaque project metadata;
- artifact integrity ID.

The CLI writes each job artifact through the generic artifact store and re-reads/verifies it before including it in the run summary.

A directory that is non-empty without a compatible ownership claim, or is already owned by another run, is rejected.

## Exit status

The public eval command has stable process-level semantics:

| Exit | Meaning |
| ---: | --- |
| <code>0</code> | Every selected case/iteration completed with classification <code>pass</code>. |
| <code>1</code> | The run completed normally, but at least one durable result was <code>fail</code> or <code>non-evidence</code>. |
| <code>2</code> | Usage/profile/planning/storage/orchestration failure prevented a normal complete run. |

<code>non-evidence</code> is deliberately not collapsed into behavioral <code>fail</code>. Both produce exit <code>1</code> only when the run itself completed normally.

Profile/import errors, invalid selection, invalid concurrency/timeouts/retry counts, incompatible artifact storage, or unexpected job/profile exceptions produce exit <code>2</code>.

If an orchestration/profile exception occurs in the standard lane, the CLI does not start the later runtime lane. This avoids additional inference after the run is already known to be incomplete.

## Complete example

~~~bash
opencode-eval-runner eval \
  --profile myproject.eval_profile:PROFILE \
  --cases smoke,runtime \
  --iterations 2 \
  --parallel 4 \
  --runtime-parallel 1 \
  --target-transport opencode \
  --target-model openai/gpt-5.6 \
  --target-reasoning medium \
  --judge-transport github-copilot-cli \
  --judge-model gpt-5.4 \
  --judge-reasoning high \
  --engine podman \
  --network host \
  --timeout-seconds 240 \
  --container-timeout 300 \
  --transport-retries 2 \
  --artifact-dir .opencode-evals/manual-run
~~~

Transport/model/reasoning controls change only the generic invocation fields. Project-specific agent, skill, fixture, evidence, assertion, rubric, threshold, and judge meaning remain profile-owned.

## Optional paired baseline/candidate evaluations

The generic Python API also supports paired execution. This is **opt-in** and
does not change the public `eval` CLI, its profile requirements, its artifacts,
or its exit codes. There is currently **no paired CLI flag**.

- Build two `PairedSideExecution` inputs (one baseline, one candidate). Each
  supplies its own target spec, prepared fixture, evidence requirements,
  profile callbacks, and target/judge retry settings.
- Call `run_paired_evaluation(..., policy=PairedExecutionPolicy(mode="sequential"))`
  or select `mode="parallel"` for concurrent sides. Sequential mode uses
  an explicit side order; both sides share one run/case/iteration identity.
- Optionally pass `comparison_extension=project_profile`, where the extension
  implements `compare_pair(baseline, candidate) -> ComparisonDecision`.
  It receives the two **completed** `EvaluationResult` objects, including
  target/judge attempts, readiness, checks, and their classifications.
- Serialize with `build_paired_eval_artifact(result)` and persist via
  `RunArtifactStore.write_paired_job_artifact(identity, artifact)`.
  Use `read_paired_job_artifact` to verify durable round trips.

Imports:

~~~python
from runner.eval_paired import (
    PairedExecutionPolicy,
    PairedSideExecution,
    build_paired_eval_artifact,
    run_paired_evaluation,
)
from runner.eval_compare import ComparisonDecision
~~~

The optional `comparison` field uses
`opencode-eval-runner/eval-comparison/v1`. Its `status` is one of:

- `compared`: a valid **project-owned** `classification`, summary, and JSON
  data; the core does not choose scores or thresholds.
- `non-evidence`: at least one side is ineligible; the callback is not run
  and no numeric value is substituted for unavailable evidence.
- `invalid`: missing callback or invalid/throwing project comparison code;
  an explicit failure code is retained rather than a fabricated decision.

When no comparison extension is passed, both sides still execute and their
paired artifact intentionally omits `comparison`. The
`eval-paired-artifact/v1` includes two complete `eval-artifact/v1` side
envelopes and a stable pair identity. Any included comparison is validated
against their real classifications and is **sealed in the paired integrity
digest**. Normal single-case eval artifacts remain unchanged.

Projects own baseline/candidate meaning, score interpretation, thresholds,
trap rules, and any higher-level PASS/FAIL decision. The generic paired
result does not define a final combined verdict. The caller owns any paired
run scheduling, user-facing summary, or exit behavior beyond this API.

## Scope limits

The public generic eval interface does not add:

- Loom-specific cases, selectors, prompts, or verdict rules;
- Loom-specific ablation policies, skill loading, or scoring thresholds;
- a universal assertion DSL;
- a universal judge result schema;
- an input JSON request API;
- repository or binary renaming.

For the one-invocation boundary and transport-specific options, see [Invocation usage and interface reference](invocation-usage.md).

For the architecture and ownership split, see [Generic eval-engine architecture](eval-engine-architecture.md).
