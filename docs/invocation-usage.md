# Invocation usage and interface reference

This repository provides an isolated **invocation execution boundary** for eval harnesses. It does not own eval cases, suites, assertions, judging semantics, thresholds, or final PASS/FAIL policy.

An eval harness uses this runner to execute one target or judge invocation at a time:

~~~text
eval harness
  -> invocation inputs
  -> opencode-eval-runner invoke
  -> isolated OpenCode or GitHub Copilot CLI process
  -> result/v1 + runtime-evidence/v1
  -> eval harness assertions / judging / verdict
~~~

## Input contract

There is currently **no input JSON request API**.

The supported invocation input contracts are:

1. the host CLI: <code>opencode-eval-runner invoke ...</code>;
2. the GitHub Action inputs in <code>action.yml</code>;
3. a repository-owned harness that calls the host CLI one or more times.

Prompt and system content are supplied as UTF-8 files rather than as a JSON request body.

The absence of an input JSON schema is intentional in the current interface. Do not assume stdin JSON or an <code>invocation/v1</code> request envelope is supported.

### Input files

| Input | Required | Applies to | Meaning |
| --- | --- | --- | --- |
| <code>--prompt-file PATH</code> | Yes | Both transports | UTF-8 user/task prompt copied into the isolated invocation. |
| <code>--system-file PATH</code> | No | GitHub Copilot CLI | UTF-8 system/agent instructions. The OpenCode transport currently does not consume this file. |
| <code>--config PATH</code> | No | OpenCode | Explicit OpenCode JSON config seed. The host OpenCode config is not inherited automatically. |
| <code>--auth PATH</code> | No | OpenCode | Explicit legacy OpenCode auth JSON seed. |
| <code>--database PATH</code> | No | OpenCode | OpenCode V2 database source. The runner copies only credential rows and migration journals into a sanitized temporary database. |
| <code>--models-catalog PATH</code> | No | OpenCode | Explicit OpenCode model-catalog seed. |
| <code>--config-root PATH</code> | No | OpenCode | Explicit OpenCode config-root source used by the runtime plugin compatibility bridge. The current implementation materializes the supported local Loom plugin tree from <code>plugins/loom</code> when present. |

## Ways to run

| Mode | Interface | Typical use |
| --- | --- | --- |
| Local single OpenCode invocation | Host CLI | Debug or run one agent/tool-aware eval invocation with authoritative OpenCode runtime evidence. |
| Local single Copilot invocation | Host CLI | Run a model/role/judge invocation that does not require OpenCode runtime evidence. |
| Local eval suite | Repository-owned harness calling the CLI repeatedly | Compose cases, target/judge invocations, assertions, iterations, and verdicts outside the runner. |
| GitHub Action direct invocation | Action inputs with <code>model</code> set and <code>command</code> empty | Run one isolated invocation directly from a workflow. |
| GitHub Action repository harness | Action <code>command</code> input | Prepare the runner/images, then execute the repository's own eval harness. |
| GitHub Action setup only | Leave both <code>model</code> and <code>command</code> empty | Pull/build selected images and put the runner on PATH for later workflow steps. |

Directly invoking the transport container entrypoint is an implementation detail, not a supported public interface. Use the host CLI or GitHub Action so workspace mounts, credential seeding, result validation, and runtime-evidence handling stay consistent.

## Host CLI reference

The only current subcommand is:

~~~text
opencode-eval-runner invoke [options]
~~~

### Execution and transport

| Option | Required / default | Applies to | Description |
| --- | --- | --- | --- |
| <code>--transport {opencode,github-copilot-cli}</code> | Default: <code>opencode</code> | Both | Selects the invocation transport. |
| <code>--engine {auto,podman,docker}</code> | Default: <code>auto</code> | Both | OCI engine. <code>auto</code> prefers Podman, then Docker. |
| <code>--network MODE</code> | Optional | Both | Explicit OCI network mode/name such as <code>host</code>, <code>bridge</code>, <code>slirp4netns</code>, or a custom network. |
| <code>--image IMAGE</code> | Optional | Both | Override the selected transport image. Host runner and custom image must be contract-compatible. |
| <code>--workspace PATH</code> | Default: <code>.</code> | Both | Workspace mounted at <code>/workspace</code>. |
| <code>--workspace-mode {ro,rw}</code> | Default: <code>ro</code> | Both | Workspace bind-mount mode. |
| <code>--mount SOURCE:TARGET[:ro|rw]</code> | Repeatable | Both | Add an explicit bind mount. Default mode is read-only. |

### Model and invocation

| Option | Required / default | Applies to | Description |
| --- | --- | --- | --- |
| <code>--model MODEL</code> | **Required** | Both | Model identifier passed to the selected transport. |
| <code>--reasoning LEVEL</code> | Optional | Both | OpenCode maps this to the model <code>#variant</code>; Copilot maps it to <code>--effort</code>. |
| <code>--agent NAME</code> | Optional | OpenCode | Select the OpenCode agent. Copilot uses its fixed isolated <code>eval-runner</code> profile. |
| <code>--skill ID</code> | Optional | OpenCode only | Records the skill under test. It does not force the skill to load. |
| <code>--expected-plugin NAME</code> | Optional | OpenCode only | Fail closed before inference unless the named plugin is materialized and active in the isolated OpenCode runtime. |
| <code>--prompt-file PATH</code> | **Required** | Both | UTF-8 invocation prompt. |
| <code>--system-file PATH</code> | Optional | Copilot | UTF-8 system instructions consumed by the Copilot transport. |
| <code>--env NAME</code> | Repeatable | Both | Explicitly forward an additional host environment variable when it is set. |

### OpenCode seeds

| Option | Required / default | Applies to | Description |
| --- | --- | --- | --- |
| <code>--auth PATH</code> | Optional; otherwise env/default discovery | OpenCode | Legacy auth JSON seed. |
| <code>--database PATH</code> | Optional; otherwise env/default discovery | OpenCode | V2 database source; sanitized before container use. |
| <code>--models-catalog PATH</code> | Optional; otherwise env/default discovery | OpenCode | Model-catalog seed. |
| <code>--config PATH</code> | Optional | OpenCode | Explicit OpenCode config JSON. |
| <code>--config-root PATH</code> | Optional | OpenCode | Explicit config-root source for supported local plugin materialization. |

### Timeouts and result handling

| Option | Required / default | Applies to | Description |
| --- | --- | --- | --- |
| <code>--timeout-seconds N</code> | Default: <code>240</code> | Both | Timeout for the model/OpenCode/Copilot invocation inside the container. |
| <code>--container-timeout N</code> | Default: <code>300</code> | Both | Outer host timeout for the OCI process. |
| <code>--output PATH</code> | **Required** | Both | Host path where the validated result JSON is written. |
| <code>--print-result</code> | Default: off | Both | Also print the validated result JSON to stdout. |

### CLI examples

OpenCode:

~~~bash
opencode-eval-runner invoke \
  --transport opencode \
  --workspace /path/to/project \
  --model openai/gpt-5.5 \
  --agent general \
  --prompt-file /tmp/prompt.txt \
  --output /tmp/result.json
~~~

Copilot:

~~~bash
opencode-eval-runner invoke \
  --transport github-copilot-cli \
  --workspace /path/to/project \
  --model gpt-5.4 \
  --prompt-file /tmp/prompt.txt \
  --system-file /tmp/system.txt \
  --output /tmp/judgment.json
~~~

A local eval harness simply invokes the CLI repeatedly for its target and judge calls. The harness, not this runner, owns case IDs, iterations, expected behavior, assertions, grading, and final verdicts.

## Environment-variable reference

### Runner configuration

| Variable | Meaning |
| --- | --- |
| <code>OPENCODE_EVAL_RUNNER_OPENCODE_IMAGE</code> | Default OpenCode image override when <code>--image</code> is not supplied. |
| <code>OPENCODE_EVAL_RUNNER_COPILOT_IMAGE</code> | Default Copilot image override when <code>--image</code> is not supplied. |
| <code>OPENCODE_EVAL_RUNNER_IMAGE</code> | Generic fallback image override used after the transport-specific override. |
| <code>OPENCODE_EVAL_RUNNER_AUTH</code> | OpenCode auth JSON seed path. |
| <code>OPENCODE_EVAL_RUNNER_DB</code> | OpenCode V2 database source path. |
| <code>OPENCODE_EVAL_RUNNER_MODELS</code> | OpenCode model-catalog seed path. |
| <code>OPENCODE_EVAL_RUNNER_CONFIG</code> | Explicit OpenCode config JSON path. |
| <code>OPENCODE_EVAL_RUNNER_CONFIG_ROOT</code> | Explicit OpenCode config-root source path. |

Explicit CLI paths take precedence over their environment equivalents.

### Automatically recognized provider credentials

For OpenCode, these host variables are forwarded automatically when set:

- <code>OPENAI_API_KEY</code>
- <code>ANTHROPIC_API_KEY</code>
- <code>OPENROUTER_API_KEY</code>

Use <code>--env NAME</code> for any additional variable.

For GitHub Copilot CLI, authentication precedence is:

1. <code>COPILOT_GITHUB_TOKEN</code>
2. <code>GH_TOKEN</code>
3. <code>GITHUB_TOKEN</code>
4. authenticated host <code>gh auth token</code> fallback

The token value is passed through the child-process environment, not placed on the OCI command line.

## GitHub Action interface

The Action has three behaviors:

1. <code>command</code> non-empty: setup images/runner, then run the repository-owned command. This takes precedence over direct invocation inputs.
2. <code>command</code> empty and <code>model</code> non-empty: run one direct isolated invocation.
3. both empty: setup only; no invocation is run.

### Action inputs

| Input | Default | Meaning |
| --- | --- | --- |
| <code>opencode-image</code> | <code>ghcr.io/bateau84/opencode-eval-runner:opencode-edge</code> | OpenCode transport image. |
| <code>copilot-image</code> | <code>ghcr.io/bateau84/opencode-eval-runner:copilot-edge</code> | Copilot transport image. |
| <code>prepare-opencode</code> | <code>true</code> | Pull/build the OpenCode image during setup. |
| <code>prepare-copilot</code> | <code>true</code> | Pull/build the Copilot image during setup. |
| <code>engine</code> | <code>docker</code> | Container engine used by action invocations/builds. |
| <code>build</code> | <code>false</code> | Build transport images from the action checkout instead of pulling published images. |
| <code>transport</code> | <code>opencode</code> | Direct-invocation transport. Ignored when <code>command</code> is supplied. |
| <code>model</code> | empty | Direct-invocation model. A non-empty value triggers direct mode when <code>command</code> is empty. |
| <code>reasoning</code> | empty | Optional reasoning level/effort. |
| <code>agent</code> | empty | Optional OpenCode agent. |
| <code>skill</code> | empty | Optional OpenCode skill ID under test. |
| <code>workspace</code> | <code>.</code> | Direct-invocation workspace. |
| <code>workspace-mode</code> | <code>ro</code> | Direct workspace mount mode. |
| <code>prompt-file</code> | empty | Direct prompt file. Required when <code>model</code> is set. |
| <code>system-file</code> | empty | Optional system prompt file. Consumed by the Copilot transport. |
| <code>output</code> | <code>.opencode-evals/result.json</code> | Direct-invocation result path. |
| <code>mounts</code> | empty | Newline-separated <code>SOURCE:TARGET[:ro|rw]</code> mounts. |
| <code>timeout-seconds</code> | <code>240</code> | Inner model invocation timeout. |
| <code>container-timeout</code> | <code>300</code> | Outer container timeout. |
| <code>command</code> | empty | Repository-owned eval command; takes precedence over direct invocation. |
| <code>artifact-dir</code> | <code>.opencode-evals</code> | Host artifact directory created during Action setup. |

### Action direct-mode coverage

The Action direct mode intentionally exposes a smaller interface than the host CLI.

The following CLI capabilities are **not direct Action inputs**:

- <code>--network</code>
- <code>--expected-plugin</code>
- <code>--auth</code>
- <code>--database</code>
- <code>--models-catalog</code>
- <code>--config</code>
- <code>--config-root</code>
- repeatable arbitrary <code>--env</code>
- <code>--print-result</code>

For OpenCode seed paths, workflows can use the documented <code>OPENCODE_EVAL_RUNNER_*</code> environment variables where applicable. If a workflow needs the full CLI option surface, use setup-only or <code>command</code> mode and invoke <code>opencode-eval-runner</code> explicitly.

### GitHub Action direct invocation

~~~yaml
- uses: bateau84/opencode-eval-runner@main
  with:
    transport: opencode
    model: openai/gpt-5.5
    agent: general
    workspace: .
    prompt-file: .github/evals/prompt.txt
    output: .opencode-evals/result.json
~~~

### GitHub Action repository-owned harness

~~~yaml
- uses: bateau84/opencode-eval-runner@main
  with:
    command: |
      python3 scripts/run-evals.py --cases WORK-01,REVIEW-01
~~~

### GitHub Action setup only

~~~yaml
- uses: bateau84/opencode-eval-runner@main
  with:
    prepare-opencode: true
    prepare-copilot: false

- run: |
    opencode-eval-runner invoke \
      --transport opencode \
      --model openai/gpt-5.5 \
      --prompt-file .github/evals/prompt.txt \
      --output .opencode-evals/result.json
~~~

## Output contract

Each invocation produces one validated <code>opencode-eval-runner/v1</code> JSON result. The complete representative result is documented in the repository README.

Every official result includes <code>runtime_evidence</code>:

- OpenCode results can contain authoritative <code>runtime-evidence/v1</code> observations.
- Copilot results report runtime evidence as explicitly <code>unsupported</code>.
- the host validates <code>runtime_evidence</code> before persisting the result artifact.

For runtime assertions, follow the evidence-readiness decision procedure in [runtime-evidence-contract.md](runtime-evidence-contract.md). Diagnostic fields such as <code>tools</code>, <code>actions</code>, <code>tool_result_evidence</code>, stdout/stderr, and model text cannot substitute for missing authoritative evidence.

## What belongs outside this runner

An eval harness or repository remains responsible for:

- case definitions and IDs;
- iterations/repetitions;
- target-versus-judge orchestration;
- behavioral assertions;
- rubrics and judge prompts;
- expected results;
- thresholds;
- aggregation;
- PASS/FAIL/non-evidence decisions.

This separation is deliberate: the runner provides faithful isolated invocations and runtime evidence; the consumer decides what those observations mean for the eval.
