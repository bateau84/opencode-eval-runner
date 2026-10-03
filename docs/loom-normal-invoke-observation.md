# Loom normal-invoke observation interface

## Status

This is the exact **diagnostic runtime interface** supplied underneath Loom's
existing live-eval path:

```text
bun run eval:live ...
  -> scripts/run-evals.py
  -> opencode-eval-runner invoke
  -> normal OpenCode/Loom execution
```

It does not replace `invoke` with `observe`, does not move Loom tools behind the
restricted remote-tool service, and does not create positive protected evidence.

Two different claims must remain separate:

1. **Trusted installation observation:** a reviewed OpenCode runtime and reviewed
   installed plugin can receive truthful runtime-owned observation events.
2. **Protection from arbitrary evaluated in-process plugins:** not supported.
   An arbitrary plugin in the same OpenCode process shares process authority with
   the observation callbacks and any same-process collector/signing capability.

Signing an artifact does not turn claim 1 into claim 2.

## Enablement

The reviewed experimental normal-invoke image enables both seams:

```text
OPENCODE_EVAL_HOST_OBSERVATIONS=1
OPENCODE_EVAL_OBSERVATIONS=1
```

- `OPENCODE_EVAL_HOST_OBSERVATIONS=1` enables native/direct starts and final
  session terminals.
- `OPENCODE_EVAL_OBSERVATIONS=1` enables Code Mode inner observations.

The flags expose events only. They do not authorize evidence eligibility.

Loom does not need a new CLI verb. With a reviewed runner checkout and immutable
image:

```bash
export OPENCODE_EVAL_RUNNER_BIN=/path/to/opencode-eval-runner/bin/opencode-eval-runner

bun run eval:live -- \
  --opencode-image 'ghcr.io/bateau84/opencode-eval-runner@sha256:<reviewed-digest>' \
  --model '<provider/model>' \
  <existing case/suite/target options>
```

Existing case selection, runtime projects, agents, permissions, retries, judge
execution, artifacts, and result classification remain Loom-owned behavior.

## Hook registrations

A reviewed installed plugin may subscribe to:

```ts
await ctx.tool.hook("execute.native-observed", event => {
  // diagnostic runtime event; not authenticated evidence
})

await ctx.tool.hook("execute.observed", event => {
  // diagnostic Code Mode inner event; not authenticated evidence
})
```

The callbacks are ordinary in-process plugin hooks. They are not a security
boundary. A callback failure is suppressed by the observation seam; a callback
that never returns can still delay execution and therefore remains unsupported
for a strong noninterference claim.

## Shared ordering

Both event families allocate from one process-wide monotonic `sequence`.

Sequence is assigned at the observation boundary before awaiting the plugin
callback. It expresses observed boundary order, not serial execution.

For example:

```text
A.call_end.sequence < B.call_start.sequence
```

can establish that B's observed start followed A's observed completion. Merely
sorting starts or terminals cannot establish that relation for overlapping calls.

## Native/direct events — `opencode-native-observation/v2`

### Start

A native start is emitted only after:

1. normal `tool.execute.before` processing has selected the executed tool/input;
2. the tool input has decoded successfully;
3. the tool is about to execute.

Shape:

```json
{
  "schema": "opencode-native-observation/v2",
  "sequence": 1,
  "actor": {
    "agent": "actual-executing-agent",
    "session_id": "actual-session",
    "message_id": "actual-assistant-message"
  },
  "observer_failures": 0,
  "kind": "call_start",
  "invocation_id": "runtime-observation-uuid",
  "call_id": "actual-provider-tool-call-id",
  "tool": "actual_resolved_registration",
  "mode": "native",
  "parent": null,
  "input": {
    "state": "available",
    "value": {}
  },
  "boundary": "executable-input"
}
```

### Identity

- `tool` is the resolved runtime registration actually dispatched after normal
  request-definition/repair processing.
- `actor.agent`, `session_id`, and `message_id` come from the real
  `Tool.Context`.
- `call_id` is the actual provider/runtime ToolCall ID.
- `invocation_id` is a separate observation identity. It is not substituted
  into tool input or public Tool.Context.
- `parent: null` means no enclosing Code Mode invocation. It does **not** state
  that the Session has no parent Session.

### Successful terminal

The terminal is emitted only **after** the normal session writer has:

1. applied `ToolOutput.truncate`;
2. constructed the canonical `SessionEvent.Tool.Success`;
3. successfully published that durable session event.

Shape:

```json
{
  "schema": "opencode-native-observation/v2",
  "sequence": 9,
  "actor": { "...": "same start binding" },
  "observer_failures": 0,
  "kind": "call_end",
  "invocation_id": "same-runtime-observation-uuid",
  "call_id": "same-tool-call-id",
  "boundary": "session-tool-terminal",
  "unavailable_fields": 0,
  "outcome": "returned",
  "result": {
    "state": "available",
    "value": {
      "content": [],
      "metadata": {},
      "executed": false
    }
  }
}
```

The `result.value` payload is the canonical session result delivered through
`SessionEvent.Tool.Success`, excluding duplicate identity fields. If output was
truncated, the observed content/metadata are the **truncated session form**, not
the larger pre-truncation Tool result.

### Failed terminal

The failed terminal is emitted only after the canonical
`SessionEvent.Tool.Failed` has been published.

```json
{
  "schema": "opencode-native-observation/v2",
  "sequence": 10,
  "actor": { "...": "same start binding" },
  "observer_failures": 0,
  "kind": "call_end",
  "invocation_id": "same-runtime-observation-uuid",
  "call_id": "same-tool-call-id",
  "boundary": "session-tool-terminal",
  "unavailable_fields": 0,
  "outcome": "threw",
  "error_representation": "session-tool-failed/v1",
  "error": {
    "state": "available",
    "value": {
      "error": {
        "type": "pinned-runtime-session-error-type",
        "message": "canonical session error"
      },
      "metadata": {},
      "executed": false
    }
  }
}
```

The representation preserves the actual pinned-runtime `SessionError` result;
it does not normalize error types to a preferred vocabulary.

A decode failure before executable-input admission produces no native start and
must not manufacture a terminal-only record.

## Code Mode inner events — `opencode-local-observation/v1`

The Code Mode seam retains its existing schema.

### Parent

One Code Mode engine invocation emits `parent_start` and `parent_end`.
When host observations are enabled, the parent binding uses the actual observed
outer native `execute` invocation ID:

```json
{
  "parent": {
    "invocation_id": "outer-native-observation-id",
    "session_id": "actual-session",
    "message_id": "actual-assistant-message",
    "call_id": "actual-outer-execute-call-id"
  }
}
```

This is runtime-carried binding, not FIFO, input equality, or a reused parent
call ID.

### Inner start

`call_start` contains:

- runtime-generated inner `invocation_id`;
- `tool`: actual internal registration selected for execution;
- `catalog_path`: exact Code Mode callable path;
- the same actual actor/session/message binding as its execution context;
- the actual decoded executable input after normal before-hook changes;
- `boundary: "executable-input"`.

### Inner terminal

`call_end` uses the same inner invocation ID.

- `outcome: "returned"` with `result` is the final JSON value delivered to
  the Code Mode caller after the interpreter conversion boundary.
- `outcome: "threw"` uses
  `error_representation: "codemode-catch-name-message/v1"`, matching the
  name/message view received by Code Mode catch handling.
- `outcome: "interrupted"` has no invented result/error.

Script-controlled outer return text never supplies an inner value.

## Snapshot/value semantics

Both seams create owned snapshots rather than retaining mutable tool objects.

Supported exact values are JSON-compatible values composed from:

- null;
- booleans;
- finite numbers;
- strings;
- dense arrays;
- plain data objects.

Snapshots reject cycles, accessors, symbols, sparse arrays, non-finite numbers,
non-data properties, `toJSON` behavior, and non-plain objects. Rejected values
become:

```json
{"state":"omitted","reason":"unsupported_snapshot"}
```

No value is silently converted to a different JSON type.

## Redaction

**The normal-invoke runtime seams do not implement secret redaction.**

They emit owned in-memory snapshots to installed plugin callbacks. They do not
persist those snapshots themselves.

A trusted installed observer can apply reviewed redaction before persistence for
diagnostic use. That does not establish protection from an arbitrary evaluated
plugin sharing the same process: such a plugin can subscribe to the same hooks or
reach same-process collection/signing authority.

Therefore raw normal-invoke events are not eligible evidence and should not be
persisted as general live-eval artifacts until the redaction/trust boundary is
resolved.

## Completeness

The current normal-invoke interface does **not** prove run-wide completeness.

- Native v2 pairs starts/terminals by invocation ID when both are observed, but
  has no trusted run header/footer/drain fence.
- Code Mode v1 `parent_end` supplies per-`execute` admitted/dispatched/terminal
  accounting only.
- `observer_failures` reports callback failures visible to the runtime, but
  cannot prove that the tail of a process-level stream was not lost.
- There is no protected omission count covering native calls, delegated Sessions,
  callback queues, process interruption, or final collector drain.

Consequently no normal-invoke event stream may claim complete positive evidence.

## Host projection

There is currently **no protected normal-invoke projection** for these two hook
families.

The runner's existing `observed_execution` field belongs to the older
observer/import candidate (`--observer-key-file`) or reports capture unavailable.
It must not be silently reinterpreted as a projection of
`execute.native-observed` / `execute.observed`.

Until a protected normal-host collector exists:

- hook events are diagnostic only;
- `evidence_eligible` for this normal-host path is effectively false;
- Loom must not backfill missing fields from stdout, script output, requested
  actor names, old metadata, or source text.

A future protected collector must introduce an explicitly versioned projection
contract and consumer migration rather than relabeling an existing version.

## Supported / unsupported coverage

| Capability | Status |
| --- | --- |
| Existing `eval:live -> run-evals.py -> invoke` behavior | supported / regression-tested |
| Native executable input | diagnostic support |
| Native final session success payload | diagnostic support |
| Native final session error payload | diagnostic support |
| Code Mode executable input | diagnostic support |
| Code Mode final caller value/error | diagnostic support |
| Actual direct-session actor/session/message/call identity | diagnostic support |
| Runtime outer-execute -> inner parent binding | diagnostic support |
| Shared native/inner ordering | diagnostic support |
| Real delegated foreground child-session identity/ancestry | exercised provider-free through built-in `subagent` |
| Child Session parentID | verified in the delegated probe by querying the actual child Session; not emitted as a normal observation field |
| Provider-hosted tool results | outside this local-execution seam |
| Run-wide completeness | unsupported |
| General live-eval redaction | unsupported |
| Observer callback hang noninterference | unsupported |
| Protection from arbitrary in-process evaluated plugins | unsupported |
| Normal-host positive evidence projection | unsupported |
| Cosign image/result authentication | trusted default-branch signer implemented separately; activation requires that workflow on the default branch |
| Loom checkpoint `f8439e4` composition | Loom session reported provider-free composition PASS; runner fixtures remain separate evidence |

## Trust statement

A reviewed runtime plus a reviewed installed observer can be trusted *by policy*
to report these runtime facts. That is a deployment trust decision.

It is categorically different from proving that arbitrary evaluated plugin code
cannot fabricate, suppress, or interfere with observations while sharing the same
process. PR #41 does not claim the latter.


## Delegated-session composition checkpoint

The normal-invoke workflow includes a provider-free test using OpenCode's real
built-in foreground `subagent` tool. It verifies:

- the parent `subagent` invocation is observed under the actual parent actor and
  Session;
- the child provider request runs as the configured `reviewer` agent;
- the child tool observation carries the child Session ID;
- the child Session ID returned by the real `subagent` result matches the child
  observation;
- the actual child Session object's `parentID` matches the parent Session;
- child tool completion precedes the foreground `subagent` terminal;
- a resource-scoped permission denial for `subagent/reviewer` prevents any child
  Session request or child-tool observation.

This closes the focused foreground identity/ancestry/permission proof. Background
delivery, cancellation, and OQ-specific lifecycle behavior remain separate Loom
composition obligations and are not inferred from this test.

See [Cosign provenance](signing-provenance.md) for artifact authentication and
[plugin isolation feasibility](plugin-isolation-feasibility.md) for the stronger
same-process trust boundary.
