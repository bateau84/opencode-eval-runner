# Stock native tool observer

Runtime: stock OpenCode **2.0.23**.

This observer is the production native/direct-call adapter for the trusted-checkout profile. It is not a second public evidence contract.

## Boundary

The runner injects a reviewed Promise plugin through stock \`OPENCODE_CONFIG_CONTENT\` so its transform is applied after project/global transforms.

For registered native/direct tools it observes:

1. decoded/executable input at the transformed \`tool.execute\` boundary;
2. Session-owned terminal events:
   - \`session.tool.success\`
   - \`session.tool.failed\`.

Stock Code Mode's model-facing `execute` tool is synthetic: OpenCode creates it inside `Tool.snapshot` after registration transforms have run. The observer records that outer invocation at the stock `execute.before` hook. Its input is the exact effective value seen by that hook, before `CodeMode.Input` decode. The same Session terminal events settle it.

The Session terminal is intentional. A rejected transformed handler can bypass \`tool.execute.after\` while stock OpenCode still settles the invocation through \`session.tool.failed\`.

## Identity and ordering

The adapter correlates using the real runtime identity tuple:

\`(sessionID, messageID, callID)\`

It never correlates by FIFO, input equality, tool name, or completion order.

The public invocation ID is opaque. Code Mode inner records reference the invocation ID of the observed outer `execute` record; a dangling or identity-mismatched parent is invalid evidence. Dynamic identity/input/result/error fields are sanitized before the internal capture file is written.

The canonical \`runtime_evidence\` builder then validates:

- unique invocation identity;
- tool;
- actor;
- Session;
- message;
- CallID;
- executable input;
- Session ancestry;
- terminal success/error;
- start/terminal ordering;
- capture closure and loss accounting.

## Public representation

Raw adapter records remain internal.

They are mapped to:

\`opencode-eval-runner/runtime-evidence/v1\`

under the \`native\` boundary.

No \`native_tool_observations\` result object is emitted.

## Failure behavior

Missing capture/end, missing terminal, sequence loss, identity mismatch, duplicate/ambiguous invocation, observer/callback failure, timeout/interruption, or unavailable required fields fail closed through the canonical runtime-evidence implementation.

Product outcome remains independent. A real tool error can have complete evidence.

## Non-authoritative data

Model output, tool-returned JSON, \`tools\`, \`actions\`, \`tool_result_evidence\`, and stdout/stderr are never parsed or promoted into native runtime observations.
