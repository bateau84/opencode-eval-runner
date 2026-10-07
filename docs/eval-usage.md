# Public eval CLI and profile reference

<code>opencode-eval-runner</code> has two public execution boundaries:

~~~text
opencode-eval-runner invoke ...
opencode-eval-runner eval ...
~~~

<code>invoke</code> still means **exactly one isolated model invocation**. It has no hidden retry loop.

<code>eval</code> is generic orchestration over one or more <code>invoke</code> attempts. A project supplies cases, fixtures, prompts, evidence requirements, deterministic checks, judge construction/parsing, semantic meaning, and opaque metadata through the frozen <code>EvalProfile</code> interface in <code>runner.eval_api</code>.

The generic runner owns selection, iterations, standard/runtime scheduling, explicit retry attempts, evidence readiness, target-to-judge execution, tri-state classification, durable artifacts, summaries, and process exit status.

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
| <code>--profile MODULE:ATTRIBUTE</code> | **Required** | Initialized external <code>EvalProfile</code> export. |
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

## Scope limits

The public generic eval interface does not add:

- Loom-specific cases, selectors, prompts, or verdict rules;
- skill-ablation/baseline-candidate semantics;
- a universal assertion DSL;
- a universal judge result schema;
- an input JSON request API;
- repository or binary renaming.

For the one-invocation boundary and transport-specific options, see [Invocation usage and interface reference](invocation-usage.md).

For the architecture and ownership split, see [Generic eval-engine architecture](eval-engine-architecture.md).
