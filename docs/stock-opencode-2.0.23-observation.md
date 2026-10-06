# Stock OpenCode 2.0.23 observation surface

Purpose: implementation reference for the trusted-checkout evidence profile.

Source checkpoint: stock OpenCode **v2.0.23** (`0fd7e2829449b052abf0078666669302923d77af`). This is distilled from the source assessment performed in superseded PR #43.

OpenCode remains stock and immutable. A missing observation boundary is reported as unsupported; it is not a reason to patch OpenCode or add a hostile-runtime broker.

## Useful stock surfaces

| Observation need | Stock surface | Status |
| --- | --- | --- |
| Live runtime events | `ctx.event.subscribe()` | supported source; ordering/drain must be proven by integration test |
| Session creation / ancestry | `session.created` + Session API | supported |
| Agent for a step | Session step/message events | supported |
| Native tool call identity/input | Tool transform wrapping the decoded executable boundary | implemented and integration-tested |
| Native terminal success/failure | `session.tool.success` / `session.tool.failed` from `ctx.event.subscribe()` | implemented and integration-tested |
| Tool pre-execution hook | `ctx.tool.hook("execute.before")` | supported; occurs before tool decode/execution |
| Tool post-handler hook | `ctx.tool.hook("execute.after")` | supported; occurs after handler result but before later core normalization |
| Tool registration wrapping | `ctx.tool.transform(...)` | supported candidate for reviewed same-process instrumentation |
| Code Mode inner name/input/status | Code Mode metadata + tool hooks | supported source |
| Code Mode unique inner invocation + exact final caller value/error | no single public final boundary demonstrated | **must be proven or marked unsupported** |

## Native calls

The implemented native observer uses two supported stock boundaries:

- a final tool transform wraps direct tools (`options.codemode === false`) and records the value passed to `tool.execute`, after stock input decoding;
- a runner-owned live event subscriber records canonical `session.tool.success` / `session.tool.failed` terminals and correlates them to the start by exact Session/message/call identity.

The observer is injected through `OPENCODE_CONFIG_CONTENT`, which stock 2.0.23 loads as the final local config source. That makes its transform/hook later than discovered global/project plugins rather than relying on filename ordering.

Correlation is only by `(sessionID, messageID, callID)`. Input equality, FIFO pairing, model text, and tool-returned JSON are not correlation sources.

The terminal snapshot is Session-owned: success is the post-truncation Session content/metadata and failure is the canonical Session error. This also covers defects that bypass `tool.execute.after`; no terminal is invented when the Session itself has not settled the call.

## Code Mode

Code Mode executes inner tools through the normal tool registry, so same-process reviewed instrumentation can observe real inner execution without isolating Loom.

The difficult part is not security; it is exact correlation and finality:

- inner calls share the outer `execute` context in stock OpenCode;
- public Code Mode metadata records name/input/status but not each inner returned value/error;
- `execute.after` is before later core normalization;
- concurrent identical inner calls must not be paired by FIFO, input equality, or completion order.

The first implementation should test a runner-owned observer plugin using supported tool transforms/hooks and runtime events. It must allocate a unique observation identity at an actual execution boundary and prove how that identity reaches the final inner value/error.

If that exact binding cannot be demonstrated for a case, the affected result field remains unavailable and the assertion cannot PASS.

## Ordering and completeness

A monotonic observer sequence is useful, but sequence alone is not completeness. The integration must also account for starts, terminals, observer loss, process interruption, and required descendant Sessions.

Absence assertions are eligible only when the relevant scope is complete. Missing capture is never interpreted as "did not happen".

## What is intentionally not required

- plugin/process isolation from the trusted Loom checkout;
- remote PluginHost or capability broker;
- evidence-channel peer authentication against same-authority attackers;
- patched/forked OpenCode;
- cryptographic evidence authenticity after runtime compromise.

Those belong only to a future optional untrusted-plugin profile.
