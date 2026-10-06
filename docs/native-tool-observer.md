# Stock native-tool observer

This is the reviewed runtime observer for **native/direct tool calls** on stock OpenCode **2.0.23**.

Source checkpoint: `0fd7e2829449b052abf0078666669302923d77af`.

It does not patch or fork OpenCode. Loom and the evaluated checkout remain trusted in this profile.

## Boundaries

The observer is a runner-owned in-process Promise plugin.

For tools whose effective definition has `options.codemode === false`:

1. `ctx.tool.transform(...)` wraps the effective tool definition.
2. Stock OpenCode decodes the accepted input and then calls that wrapped `tool.execute`.
3. The wrapper records a **start** with:
   - resolved/effective tool name;
   - Session ID;
   - agent;
   - assistant message ID;
   - real tool call ID;
   - the decoded input actually passed to the tool.
4. A runner-owned `ctx.event.subscribe()` consumer records the stock Session terminal:
   - `session.tool.success` with the canonical post-truncation content/metadata; or
   - `session.tool.failed` with the canonical Session error representation.

Stock 2.0.23 loads inline `OPENCODE_CONFIG_CONTENT` after project/global config sources. The runner registers the observer there so its tool transform is applied after evaluated local plugin transforms rather than depending on filename order.

The terminal boundary is deliberately Session-owned. This matters for failures: a Promise-plugin rejection can escape before `tool.execute.after`, while the stock Session runner still settles the real call with `session.tool.failed`. Success is likewise taken from `session.tool.success` after stock output truncation, so the observer does not reconstruct a later result from an earlier hook.

## Correlation and ordering

Start and terminal records correlate only on:

`(sessionID, messageID, callID)`

The observer never pairs calls by input equality, FIFO position, tool name, or completion order.

Each attempted observer write receives a monotonic sequence. The host projection requires a contiguous sequence and preserves both start and terminal sequence numbers. A gap is invalid evidence.

## Completeness and loss

A normal plugin lifetime writes:

- `capture_start`;
- zero or more start/terminal records;
- `capture_end` with start, terminal, outstanding, observer-failure, and unavailable-field counts.

The projection is evidence-eligible only when the capture is structurally valid, ended cleanly, has no missing terminals, no observer failures, and no unavailable required fields.

A missing file, missing end marker, sequence gap, count mismatch, duplicate call, terminal without a start, oversized/unsupported field, or observer I/O loss fails closed.

Observer failures do **not** change a tool's return value/error and do not trigger product retries. Loss is reflected only in observation eligibility.

## Payload separation

The projection reads only `/tmp/runtime/native-tool-observer.jsonl`, produced by the runner-owned plugin.

It never scans:

- model text;
- `opencode run --format json` prose/content fields;
- tool-returned strings;
- collector-shaped JSON embedded in any of those.

The provider-free integration test explicitly places collector-shaped JSON in both a native tool result and model output and proves that the observation count does not change.

## Scope

This implementation covers native/direct calls only.

Code Mode inner-call finality remains a separate problem because stock inner calls have different identity/finality constraints. This observer does not claim Code Mode coverage.

## Verification

`tests/test_native_observer.py` checks the parser and fail-closed rules.

`tests/integration/run_native_observer_probe.py` builds/runs the actual repository image with stock OpenCode 2.0.23 and a loopback fake OpenAI-compatible provider under `--network none`. It proves:

- native success;
- native failure;
- accepted/executable input after a pre-hook rewrite;
- resolved tool + Session + agent/message + real call ID;
- start/terminal correlation;
- ordering across multiple calls;
- collector-shaped payload separation;
- no observer-induced model retry.
