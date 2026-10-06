# Code Mode inner-call observation experiment

Status: **bounded negative result with partial stock support**

Parent: PR #45 trusted-checkout runtime evidence.

Runtime checkpoint: stock OpenCode **v2.0.23**, tag commit
`0fd7e2829449b052abf0078666669302923d77af`.

This experiment asks one question only: how much of an actual inner Code Mode
tool invocation can reviewed same-process runner instrumentation observe without
patching OpenCode?

## Result

Stock OpenCode 2.0.23 supports a useful partial observation path:

| Fact | Stock supported surface | Result |
| --- | --- | --- |
| unique inner invocation identity | runner-owned `tool.transform` wrapper allocates an ID when the decoded leaf handler is actually entered | **supported** |
| actual selected tool | wrapper is attached to the effective registered tool | **supported** |
| executable input | wrapper runs after core input decoding and receives the value passed to the leaf handler | **supported** |
| real outer `execute` binding | the real `Tool.Context` carries Session/message/outer CallID into each inner leaf; production evidence also records the outer call at `execute.before` | **supported** |
| start / handler-terminal ordering | runner observer sequence around the transformed leaf handler | **supported** |
| exact final value delivered to the Code Mode script | no supported public stock boundary exposes it with unique inner identity | **unsupported** |
| exact final error seen by the script catch path | no supported public stock boundary exposes it with unique inner identity | **unsupported** |

The partial path is useful for proving that an inner call really entered a
particular tool with a particular decoded input. It is **not** sufficient for
assertions about the value/error ultimately observed by Code Mode.

The experiment therefore reports the final-caller capability as:

```json
{
  "status": "unsupported",
  "reason": "stock_codemode_final_boundary_not_exposed"
}
```

No value is reconstructed from an earlier result.

## Exact missing boundary

There are three distinct boundaries in stock 2.0.23.

### 1. Public transformed leaf handler

`packages/core/src/tool/runtime.ts` decodes input and then calls the registered
tool's `execute(decoded, context)`.

A runner-owned `ctx.tool.transform(...)` wrapper can therefore allocate a fresh
per-call ID at a real execution boundary and observe:

- the effective tool registration;
- decoded/executable input;
- the real Session ID, agent, message ID and outer `execute` CallID carried in
  `Tool.Context`;
- a parent ID that resolves to the separately observed model-facing outer `execute`
  invocation rather than to an internal correlation-only token;
- handler return or throw;
- start and handler completion order.

This works for identical concurrent calls because correlation is carried by the
wrapper's own per-invocation state. It does not pair calls by input, FIFO order,
tool name, or completion order.

But the handler result is still early. After it returns, core may:

1. encode/normalize the tool output;
2. run public `tool.execute.after` hooks, which may mutate the result;
3. normalize content;
4. let the Code Mode adapter choose structured output vs text/null fallback;
5. validate Code Mode output;
6. JSON stringify/parse the value before it crosses into the confined script.

So the transform wrapper cannot claim its handler terminal is the script-visible
terminal.

### 2. Public core `tool.execute.after`

`packages/core/src/tool.ts` exposes a later hook with the core result/error.

This is also insufficient for exact Code Mode correlation:

- every inner Code Mode call receives the same `Tool.Context.id` as the outer
  model-visible `execute` call;
- therefore concurrent identical inner calls have the same public CallID;
- the hook runs before Code Mode's own final output decode/JSON round trip;
- failures that escape the core Tool.Error path need not produce this hook even
  though Code Mode later converts the failure for the script.

Using input equality, FIFO order, object identity, or completion order to join
this hook back to wrapper records would invent a correlation contract that stock
OpenCode does not provide.

### 3. Private Code Mode terminal and catch materialization

The last success-value boundary exists inside `@opencode/codemode`.

In `packages/codemode/src/tool-runtime.ts`, `hooked(...)` runs
`hooks["tool.after"]` from `Effect.onExit` around the Code Mode execution body.
For a successful call, this happens after output decoding and the JSON
stringify/parse round trip, so its `CallResult.value` is the plain value that the
tool promise will deliver into the interpreter.

However, `packages/core/src/codemode/tool.ts` constructs Code Mode with only
OpenCode's private `progressHooks(record)`. That hook uses the internal call
object only to update UI rows and publishes name/input/status. It does **not**
publish the success value, and stock plugin APIs provide no supported way to add
another Code Mode hook there.

The error path is later still. A failed tool promise reaches the interpreter and
`packages/codemode/src/interpreter/interpreter.ts` materializes the failure into
the JavaScript error value bound by a `catch` clause. There is no plugin/runtime
hook at that materialization boundary either. The private Code Mode `tool.after`
can see the host-side failure before this conversion, but that is not the exact
JavaScript error object seen by the script.

So stock exposes neither the final success value with public unique correlation
nor the final catch-path error representation. Those are the missing boundaries.

## PR #41 reuse decision

PR #41 correctly demonstrated the semantics needed at this boundary, but it did
so by patching OpenCode and adding an internal Code Mode observer seam. That
implementation is not reused here.

Only the behavioral test ideas are retained:

- overlapping identical calls;
- reverse completion;
- caught inner errors;
- mutation after an earlier observation point;
- real parent Session/call binding;
- script output that resembles an observer record.

The stock experiment uses only supported plugin transforms/hooks.

## Provider-free integration probe

`tests/integration/run_code_mode_observer_probe.py` runs the actual
`opencode-eval-runner:opencode-test` image built from this checkout.

It starts a loopback OpenAI-compatible fixture provider inside the container, so
there is no external provider call and no credential use. The fixture makes one
real model-visible `execute` call whose Code Mode script performs:

1. one successful inner call;
2. one thrown inner error that the script catches;
3. two concurrent calls with identical input;
4. reverse completion of those two calls;
5. multiple inner calls under the same outer `execute`;
6. a returned collector-shaped fake record.

The test plugin also changes one tool result from `BEFORE-MUTATION` to
`AFTER-MUTATION` in a public `execute.after` hook. The script asserts that it
receives `AFTER-MUTATION`. The transformed handler observer records
`BEFORE-MUTATION`. This is the concrete counterexample proving that the handler
terminal is not the caller-final value.

The outer script finally returns JSON containing
`invocation_id: "fabricated-from-script"`. The runner event stream proves that
the outer script executed, while the same ID must be absent from observer records.
Script/model output therefore does not create an inner observation.

## Evidence status

The probe plugin writes diagnostics under `/tmp` only for the test. That file is
target-writable and is **not** an evidence authority.

The experiment summary always reports:

```json
{
  "status": "unsupported",
  "evidence_eligible": false
}
```

This does not mean all inner facts are unavailable. It means the requested
end-to-end Code Mode result/error capability is incomplete on stock supported
surfaces, so the partial records must not be promoted as proof of the final
caller-visible value/error.

A future stock OpenCode API could make this capability supported by exposing the
internal Code Mode per-call identity and post-conversion success value to plugins,
plus the materialized catch-path error value (or one supported terminal event that
carries both forms with the same invocation identity). Until then, the correct
runner result is `unsupported`.
