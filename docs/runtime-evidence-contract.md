# Runtime evidence contract v1

Public schema: \`opencode-eval-runner/runtime-evidence/v1\`.

\`runtime_evidence\` is the only authoritative runtime-evidence object in the runner result. Raw observer records are internal adapter input and are not serialized as a competing public result.

The existing \`tools\`, \`actions\`, \`tool_result_evidence\`, stdout/stderr, Session/model text, and workspace files are convenience or diagnostic data only.

## Top-level meaning

The object contains:

- \`status\`: \`complete | incomplete | unsupported | invalid\`;
- \`evidence_eligible\`: whether the capture is usable for assertions over complete supported boundaries;
- \`observations\`: one aggregate record per observed invocation;
- \`coverage\`: closure, process state, counts, loss accounting, unsupported capabilities, and per-boundary status.

Overall \`complete\` does **not** mean every possible assertion is supported. It means the observed supported boundaries are complete and internally consistent. A separately declared unsupported capability does not poison unrelated evidence.

Overall \`incomplete\` or \`invalid\` fails every assertion scope because the capture itself cannot prove completeness.

## Boundary eligibility

v1 exposes three named boundaries:

- \`native\`: direct/native tool execution;
- \`code_mode_execution\`: inner Code Mode identity, tool, executable input, parent binding, outcome, and ordering up to the transformed handler terminal;
- \`code_mode_finality\`: the exact final value/error seen by the Code Mode script.

Each boundary has its own \`status\`, \`evidence_eligible\`, counts, and issues.

This allows a result such as:

\`\`\`text
overall: complete / eligible
native: complete / eligible
code_mode_execution: complete / eligible
code_mode_finality: unsupported / ineligible
\`\`\`

An assertion is eligible only when all boundaries it requires are \`complete\`.

If an assertion also requires an exact field value, that field must be \`available\`. \`redacted\` or \`omitted\` makes that value-dependent assertion incomplete; \`unsupported\` makes it unsupported. Other assertions that do not require that field can still use the same complete boundary.

## Field states

Dynamic observation fields use exactly these public states:

- \`available\`: value is present;
- \`redacted\`: value existed but was removed because it matched protected credential material;
- \`omitted\`: value could not safely or completely be represented;
- \`unsupported\`: the stock runtime does not expose the required fact at the required boundary.

Unknown counts are never converted to \`0\`.

## Native observation

The runner-owned stock OpenCode 2.0.23 observer records:

- opaque invocation identity;
- resolved tool;
- agent/actor;
- Session ID;
- message ID;
- real CallID;
- decoded/executable input;
- start ordering;
- terminal success/error and ordering;
- Session ancestry where applicable.

The normal registered-tool start boundary is the decoded `tool.execute` wrapper. The synthetic Code Mode `execute` registration is created after transforms, so its start is observed at the stock `execute.before` hook instead. For that one tool, `input` is the exact effective hook input before `CodeMode.Input` decode.

The terminal boundary is Session-owned:

\`\`\`text
success -> session.tool.success
error   -> session.tool.failed
\`\`\`

The implementation does not treat \`tool.execute.after\` as a complete native failure boundary and does not correlate by FIFO, input equality, tool name, or completion order.

## Code Mode observation

For Code Mode inner calls the runner can observe, on stock 2.0.23:

- a unique per-inner invocation identity;
- the actual effective tool;
- decoded/executable input;
- Session/message/agent;
- the actual outer \`execute\` CallID;
- parent binding to the authoritative observed outer `execute` invocation;
- start and handler-terminal ordering;
- success-vs-error outcome at the handler boundary.

The earlier handler return/error is **not** promoted as final caller evidence.

The public result therefore emits the final \`result\` or \`error\` field as:

\`\`\`json
{
  "state": "unsupported",
  "reason": "stock_codemode_final_boundary_not_exposed"
}
\`\`\`

The \`code_mode_execution\` boundary can still be complete and eligible.

> Stock OpenCode 2.0.23 does not expose a supported boundary that proves the exact final value/error seen by a Code Mode script for each inner call. That assertion is reported as unsupported.

## Completeness and invalidity

The canonical builder/validator owns all evidence status and eligibility decisions.

It accounts for:

- missing terminals;
- missing capture closure;
- observer/callback failure;
- timeout/interruption;
- capture loss;
- malformed observations;
- duplicate invocation IDs;
- duplicate sequence IDs;
- terminal-without-start;
- identity changes between start and terminal;
- missing, dangling, or identity-mismatched Code Mode outer-parent observations;
- unsupported boundaries;
- assertion-scoped field availability.

There is no second \`evidence_accounting\` or \`native_tool_observations\` public status engine.

## Safety order

Authoritative dynamic values follow this order:

\`\`\`text
raw observation in observer memory
  -> sanitize/redact/omit
  -> size decision
  -> internal capture record
  -> validate/account
  -> result serialization
  -> stdout/host-file persistence
\`\`\`

Credential material is therefore removed before the first observation-file or result-output sink. Oversized or unsafe values become explicit field states rather than clipped authoritative values.

Product outcome remains independent:

- a tool error can still have complete evidence;
- a successful product result can have incomplete evidence;
- \`exit_code\` and timeout status do not become evidence eligibility.

## Trust scope

This is the normal trusted-checkout Loom eval profile. It uses stock OpenCode 2.0.23 and reviewed same-process instrumentation.

It does not require or claim:

- OpenCode patches/forks;
- remote PluginHost;
- protected/authenticated evidence channel;
- HMAC/signing/Cosign;
- capability broker;
- hostile-plugin isolation.
