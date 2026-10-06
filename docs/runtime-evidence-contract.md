# Runtime evidence contract v1

Public schema: \`opencode-eval-runner/runtime-evidence/v1\`.

\`runtime_evidence\` is the only authoritative runtime-evidence object in the runner result. Raw observer records are internal adapter input and are not serialized as a competing public result.

The existing \`tools\`, \`actions\`, \`tool_result_evidence\`, stdout/stderr, Session/model text, and workspace files are convenience or diagnostic data only. They do not publish runtime-evidence eligibility and must not be used as substitutes even when their contents look like runtime-evidence JSON.

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

## Consumer decision rule

A consumer must decide evidence eligibility per assertion, not from the top-level flag alone:

1. Validate the `runtime_evidence` object against this schema before using it.
2. If overall status is `incomplete` or `invalid`, no runtime assertion is eligible for PASS.
3. Declare the boundary or boundaries required by the assertion. Every required boundary must be `complete`.
4. If the assertion depends on an exact observation field, that field must be `available`. `redacted` or `omitted` makes that value-dependent assertion incomplete; `unsupported` makes it unsupported.
5. Never fill a missing authoritative fact from `tools`, `actions`, `tool_result_evidence`, stdout/stderr, model text, or workspace files.

For example, an assertion that a direct tool ran can depend on `native`. An assertion about a Code Mode inner tool identity/input can depend on `code_mode_execution`. An assertion about the exact final value or error seen by a Code Mode script depends on `code_mode_finality` and is therefore unsupported on stock OpenCode 2.0.23.


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
  -> runner-owned one-connection stream
  -> validate/account
  -> result serialization
  -> stdout/host-file persistence
\`\`\`

Credential material is therefore removed before the first authoritative observation transport or result-output sink. Oversized or unsafe values become explicit field states rather than clipped authoritative values.

Product outcome remains independent:

- a tool error can still have complete evidence;
- a successful product result can have incomplete evidence;
- \`exit_code\` and timeout status do not become evidence eligibility.

## Operational bounds

The current stock observer bounds authoritative capture to 8 MiB and at most 20,001 JSONL events, and bounds each projected dynamic field to 256 KiB. Crossing an aggregate capture bound makes the capture invalid/ineligible; the runner does not truncate it into apparently complete evidence. A field that exceeds its field bound is explicitly `omitted` with reason `size_limit`, so assertions requiring that exact value remain ineligible.

These are current adapter safety limits, not provider or model guarantees.


## Compatibility and migration

The outer result schema remains `opencode-eval-runner/v1`, but `runtime_evidence` is now mandatory. The host CLI validates it after container execution and rejects a result that omits it or violates this v1 contract.

Official OpenCode and Copilot images in this revision emit the required object. A legacy or custom image built against the older result shape must be upgraded together with the host runner. This does not require any OpenCode modification: the supported OpenCode profile uses stock 2.0.23. Copilot results satisfy the result-shape requirement by reporting runtime evidence as explicitly `unsupported`.

## Unsupported areas

- \`code_mode_finality\`: stock OpenCode 2.0.23 does not expose the exact final value/error seen by each Code Mode script call.
- \`github-copilot-cli\`: this transport has no OpenCode runtime observer, so its \`runtime_evidence\` object is explicitly \`unsupported\`.
- hostile evaluated plugins: same-process instrumentation is not protected from a plugin that deliberately compromises the trusted runtime.

## Trust scope

This is the normal trusted-checkout Loom eval profile. It uses stock OpenCode 2.0.23 and reviewed same-process instrumentation.

It does not require or claim:

- OpenCode patches/forks;
- remote PluginHost;
- protected/authenticated evidence channel;
- HMAC/signing/Cosign;
- capability broker;
- hostile-plugin isolation.
