# Stock OpenCode 2.0.23 observation surface

Purpose: implementation reference for the trusted-checkout evidence profile.

Source checkpoint: stock OpenCode **v2.0.23** (`0fd7e2829449b052abf0078666669302923d77af`). This is distilled from the source assessment performed in superseded PR #43 and the bounded Code Mode experiment in this branch.

OpenCode remains stock and immutable. A missing observation boundary is reported as unsupported; it is not a reason to patch OpenCode or add a hostile-runtime broker.

## Useful stock surfaces

| Observation need | Stock surface | Status |
| --- | --- | --- |
| Live runtime events | `ctx.event.subscribe()` | supported source; ordering/drain must be proven by integration test |
| Session creation / ancestry | `session.created` + Session API | supported |
| Agent for a step | Session step/message events | supported |
| Native/direct decoded input | transformed registered `tool.execute` | supported |
| Synthetic outer Code Mode `execute` identity/effective input | `execute.before` + Session terminal | supported partial input boundary; pre-decode |
| Native terminal success/failure | Session tool success/failed events | supported source |
| Tool pre-execution hook | `ctx.tool.hook("execute.before")` | supported; occurs before tool decode/execution |
| Tool post-handler hook | `ctx.tool.hook("execute.after")` | supported; occurs after core tool execution but before Code Mode final conversion |
| Tool registration wrapping | `ctx.tool.transform(...)` | supported |
| Code Mode unique inner invocation/tool/input/outer binding | transformed leaf handler + real `Tool.Context` | **supported partial boundary** |
| Code Mode exact final caller value/error | internal `@opencode/codemode` `tool.after`; not exposed to plugins | **unsupported on stock public surfaces** |

## Native calls

Stock Session events are the preferred source for native terminal facts because they represent the runtime's own Session lifecycle rather than model or tool payload claims.

The observer must bind call identity, Session, agent/message context, input and terminal result/error without reconstructing them from prose or matching by value.

The model-facing Code Mode `execute` tool is not in the transformed registry: stock OpenCode creates it later inside `Tool.snapshot`. Its real invocation is therefore recorded from `execute.before` and settled by the same Session terminal event. This prevents a Code Mode run from disappearing from the native boundary. The hook input is exact at that stock surface but is before `CodeMode.Input` decode.

## Code Mode

Code Mode executes inner tools through the normal tool registry, so same-process reviewed instrumentation can observe real inner execution without isolating Loom.

The bounded stock-2.0.23 experiment establishes a useful partial path:

- `ctx.tool.transform(...)` can wrap the actual effective leaf registration;
- core decodes input before entering that wrapper, so the wrapper sees executable input;
- the real outer `execute` `Tool.Context` reaches each inner handler, providing actual Session, agent, message and outer CallID;
- that same outer call is independently present as an authoritative native observation, and each inner parent ID must resolve to it;
- the wrapper can allocate a unique per-inner observation ID at handler entry, so identical concurrent calls and reverse completion do not require input/FIFO correlation.

However, this wrapper is not the final Code Mode caller boundary. After it returns, core can encode the result, run mutating `tool.execute.after` hooks, normalize content, and Code Mode can select its return representation and perform output validation plus a JSON stringify/parse round trip.

The later public `tool.execute.after` hook is also insufficient for exact correlation: every inner call reuses the outer `execute` `Tool.Context.id`. Concurrent identical inner calls therefore have the same public CallID.

For successful calls, the last converted value exists internally: `packages/codemode/src/tool-runtime.ts` invokes Code Mode's `tool.after` after output validation and its JSON round trip. But `packages/core/src/codemode/tool.ts` supplies only private `progressHooks(record)` there. Those hooks expose name/input/status for UI progress and do not export the value. Stock plugin APIs do not provide a supported registration point for another Code Mode hook.

Errors have an additional private step. After the tool promise fails, `packages/codemode/src/interpreter/interpreter.ts` materializes that host failure into the JavaScript error value used by a `catch` clause. No public plugin/runtime hook observes that materialized error with a unique inner invocation identity.

Therefore:

- unique inner identity, actual tool, executable input, outer binding, and start/handler-terminal ordering are observable;
- exact final value delivered to the script and exact final error seen by its catch path are **unsupported**;
- no earlier result may be promoted, paired, or reconstructed to fill that gap.

See [Code Mode inner-call observation experiment](code-mode-observer-experiment.md) for the source trace and provider-free counterexamples.

## Ordering and completeness

A monotonic observer sequence is useful, but sequence alone is not completeness. The integration must also account for starts, terminals, observer loss, process interruption, and required descendant Sessions.

Absence assertions are eligible only when the relevant scope is complete. Missing capture is never interpreted as "did not happen".

For Code Mode specifically, a complete transformed-handler trace still does not make final caller-value assertions eligible: that capability is unsupported on the stock public surface.

## What is intentionally not required

- plugin/process isolation from the trusted Loom checkout;
- remote PluginHost or capability broker;
- evidence-channel peer authentication against same-authority attackers;
- patched/forked OpenCode;
- cryptographic evidence authenticity after runtime compromise.

Those belong only to a future optional untrusted-plugin profile.
