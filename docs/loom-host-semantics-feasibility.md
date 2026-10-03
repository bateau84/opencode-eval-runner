# Loom host-semantics capture feasibility

## Decision

The protected-capture work must sit **under Loom's existing eval entrypoint**:

```text
bun run eval:live ...
  -> python3 scripts/run-evals.py
  -> opencode-eval-runner invoke
  -> normal OpenCode agent/session/tool execution
```

PR #41 must not require Loom to replace that path with `observe`, a synthetic
session loop, or a remote-tool reconstruction of normal host behavior. Existing
case selection, prompts, agents, permissions, workspace setup, retries, judges,
artifacts, and pass/fail behavior remain owned by Loom's current harness.

The restricted `observe` / `codemode-inner/direct-session/v1` profile remains a
supplemental security experiment only. It is not the migration target for normal
Loom evals.

## Feasibility result

There are two separate questions.

### 1. Can the real runtime expose the required semantics without replacing them?

**Yes, for the core tool boundary.**

OpenCode 2.0.18 already routes normal direct/native tools through the central
Tool service. The same service is used when a real child Session executes tools.
Its context contains the actual executing session, agent, assistant message and
runtime call ID. Code Mode inner calls ultimately dispatch through that same Tool
service, while the Code Mode interpreter owns the final JSON value/error seen by
the script.

The downstream runtime patch therefore keeps normal execution intact and exposes
two diagnostic hook streams:

- `tool.execute.native-observed` — direct/native Tool-service starts and final
  Tool returns/errors, including the outer `execute` call.
- `tool.execute.observed` — Code Mode inner starts and the final value/error
  delivered to the Code Mode caller.

Both use one process-wide monotonic sequence. When host-semantics observation is
enabled, the actual outer native `execute` invocation ID is bound to its inner
Code Mode records without adding metadata to tool inputs or public Tool.Context.

The experimental normal-invoke image enables those seams but otherwise uses the
same `opencode-eval-runner invoke` entrypoint and normal OpenCode configuration.
It does **not** apply the restricted profile's removal of Code Mode networking or
remote-tool substitution.

These hook records remain diagnostic until a protected collection path exists.

### 2. Can those observations be protected from the current in-process Loom plugin
without changing Loom's host semantics?

**Not with the current OpenCode plugin isolation model.**

The evaluated Loom plugin and the observation seam execute in the same OpenCode
process. An arbitrary in-process plugin therefore shares the process/OS authority
needed to reach same-process files, descriptors, sockets, environment, libraries,
or a signing/collector API made available to that process.

A hidden path, random file descriptor, same-process HMAC key, localhost socket,
closure-only signer, or second hook does not create a supported security boundary
between two pieces of code with the same process authority.

Moving Loom tool closures behind `/call` protects the collector only by replacing
the host environment those tools normally depend on. That is useful as a restricted
smoke, but it cannot prove normal Loom session, permission, grant, OQ, cancellation,
gate or continuation behavior.

Therefore the smallest honest conclusion is:

> semantic observation under normal `invoke` is feasible in PR #41; a
> target-unforgeable collector while arbitrary Loom plugin code remains in-process
> requires a broader OpenCode plugin-isolation/capability project.

PR #41 must not silently build that broader platform.

## Supported / unsupported matrix

| Capability | Normal-invoke runtime seam | Protected positive evidence |
| --- | --- | --- |
| Existing `bun run eval:live` case behavior | **Preserved** — same runner `invoke` contract | N/A |
| Direct/native dispatched input | **Supported diagnostic seam** | **Blocked** for in-process plugin |
| Direct/native final Tool result/error | **Supported diagnostic seam** | **Blocked** for in-process plugin |
| Code Mode exact dispatched input | **Supported diagnostic seam** | Restricted profile already proves a subset |
| Code Mode final caller value/error | **Supported diagnostic seam** | Restricted profile already proves a subset |
| Genuine agent/session/message/call identity | **From actual Tool.Context** | Protection blocked in normal in-process profile |
| Unique child invocation correlation | **Runtime-generated IDs** | Protection blocked in normal in-process profile |
| Separate start/completion ordering | **Shared runtime sequence** | Protection blocked in normal in-process profile |
| Inner -> outer `execute` parent binding | **Runtime-bound, not FIFO/input inference** | Protection blocked in normal in-process profile |
| Delegated child Session identity | **Same central Tool path; expected to carry child context** | **Composition proof still required** |
| Session ancestry beyond executing Session ID | **Not yet emitted/proved** | Unsupported |
| Normal permission/grant/plugin behavior | **Not replaced by the observation patch** | Loom composition proof still required |
| Cancellation/lifecycle/OQ/gate continuation | **Normal host path retained** | Loom composition proof still required |
| Collector unforgeable by arbitrary in-process Loom plugin | No | **Unsupported** |
| Native/delegated full handoff acceptance | No | **Open** |

Only demonstrated coverage may become eligible evidence.

## Exact Loom-facing interface

### Entrypoint

No new Loom-facing command is required.

```bash
OPENCODE_EVAL_RUNNER_OPENCODE_IMAGE="<reviewed-normal-invoke-image@sha256:...>" \
  bun run eval:live -- --model <model> <existing selectors/options>
```

Loom continues to construct cases and call:

```text
opencode-eval-runner invoke ...
```

with its existing arguments. The runner/image implementation changes underneath
that contract.

### Diagnostic runtime hooks

A Loom feasibility observer may subscribe to both hook streams:

```ts
await ctx.tool.hook("execute.native-observed", event => { /* diagnostic only */ })
await ctx.tool.hook("execute.observed", event => { /* diagnostic only */ })
```

`execute.native-observed` uses schema `opencode-native-observation/v1`.
`execute.observed` retains `opencode-local-observation/v1`.

The two streams share the runtime sequence counter. Native records carry
`mode: "native"`, actual `call_id`, actor identity, a unique invocation ID and
`parent: null`. Code Mode inner records retain the existing actual actor and
parent structure; when the normal host observation mode is active their parent
invocation ID is the actual observed outer `execute` invocation.

Neither hook is an authenticated producer. Loom must not promote these diagnostic
records into PASS evidence merely because their shape validates.

### Result compatibility

The normal runner result contract remains the existing `invoke` result. Existing
eval cases and judge behavior must not require `observed_execution` to be present
or eligible unless a case is explicitly migrated after the protected normal-host
path exists.

The normal-invoke compatibility probe verifies the public runner CLI with a
deterministic local provider, not a second eval entrypoint.

## Broader-project boundary

To make normal in-process Loom observations target-unforgeable, OpenCode needs an
actual isolation boundary between evaluated plugin code and the collector
capability. Examples that could be researched separately include a process-isolated
plugin host with a narrow capability broker or another runtime-supported sandbox
that preserves every OpenCode API Loom requires.

That project must prove permission, session, cancellation, child/delegation,
continuation and lifecycle equivalence. It must not be introduced implicitly in
this exporter PR.

Until such a boundary exists, the runner should report normal-host observation
protection as unsupported rather than signing or authenticating same-process claims.

## Loom composition work after a compatible protected path exists

Loom then owns only the adaptation above its stable entrypoint:

1. pin the runner image/revision and the committed observer/parser/smoke checkpoint;
2. consume the agreed versioned projection without falling back to stdout/source;
3. run the existing eval cases unchanged through `bun run eval:live`;
4. add focused assertions for native, inner and delegated observations;
5. preserve disposable HOME/XDG/workspace state and avoid the installation-wide DB;
6. keep unsupported coverage non-evidence.

The handoff identifies Loom checkpoint `f8439e4`. PR #41 does not rewrite those
tests or historical results.

## Contract erratum

The historical `c1629415...` restricted-profile proof used runtime events
`opencode-local-observation/v1`, wire `opencode-protected-observation/v2`, and
projection version **3**. Any text describing that implementation as wire v1 /
projection v2 is stale documentation, not the tested contract. Historical
artifacts keep their original bytes and meaning.


## Empirical normal-invoke checkpoint

Tested implementation: `3005bcdfb7fa81c86f9a6222a8b8a04d990e42a2`.

Published experimental normal-invoke image:

```text
ghcr.io/bateau84/opencode-eval-runner@sha256:8268bdf9c0269d00585bdce434c8e7b763f5999d9a36990761c52c1ca019b517
```

The **Normal-invoke runtime observation seam #12** workflow passed its source,
build, publication and read-only verification jobs. Its provider-free
`eval-live-invoke-compatibility` probe entered through the public
`opencode-eval-runner invoke` command and observed all of the following without
real-provider credentials:

- the existing result text remained `EVAL-LIVE-FINAL`;
- the normal native sentinel remained `NATIVE-RAW`;
- the normal `execute` product result retained the Code Mode `INNER-RAW` value;
- native and outer-`execute` observations were present;
- the inner final Code Mode result was present;
- the inner parent invocation ID matched the actually observed outer
  `execute` invocation;
- native/inner start and completion events shared truthful sequence ordering.

The separate runtime seam probe also passed overlap/reverse-completion,
dispatched-input, denial-string, caught-throw, final-output-mutation, observer
failure and forged-sidecar rejection checks.

This is **diagnostic semantic evidence only**. The workflow intentionally records
`evidence_status: diagnostic_non_evidence`,
`delegated_session_identity: not_exercised`, and
`in_process_plugin_protection: unsupported`.

All four PR workflows were green on the tested implementation. This does not
authorize merge or full Loom acceptance.
