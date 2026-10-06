# Trusted-checkout runtime evidence

Status: **implemented integration on PR #45**.

This document supersedes the hostile-runtime direction explored in PR #41 and PR #43 for normal Loom evaluation.

## TRUST-001 scope

For evaluation of an explicitly trusted checkout, evidence used for scoring must originate from reviewed runtime instrumentation observing actual execution.

The following do not independently establish that an event occurred:

- model assertions or generated prose;
- tool payloads shaped like collector/evidence records;
- requested/intended actions;
- inferred identity;
- reconstructed results;
- target-writable evidence files.

Missing, partial, ambiguous, lost, or unsupported required observations make the affected assertion ineligible for PASS.

The normal profile does not claim protection from a deliberately malicious evaluated plugin that compromises the shared trusted OpenCode process. Hostile-plugin isolation is a separate optional profile.

## Integrated architecture

\`\`\`text
Loom eval harness
  -> opencode-eval-runner invoke
  -> stock OpenCode 2.0.23
     + runner-owned same-process observer
     + trusted evaluated checkout
  -> sanitized internal observer capture
  -> canonical runtime_evidence v1 builder/validator
  -> one runner result
  -> host-side v1 revalidation
  -> Loom judging
\`\`\`

The public authority is only:

\`opencode-eval-runner/runtime-evidence/v1\`

There is no public \`native_tool_observations\` or \`evidence_accounting\` authority. Existing \`tools\`, \`actions\`, \`tool_result_evidence\`, stdout/stderr, model text, and similar fields remain convenience/diagnostic data. They expose no runtime-evidence eligibility signal and are never promoted into \`runtime_evidence\`.

## Native boundary

The integrated stock observer uses:

- a transformed decoded \`tool.execute\` wrapper for the actual executable input;
- Session-owned \`session.tool.success\` / \`session.tool.failed\` events for terminal success/error;
- identity-based correlation using Session/message/CallID internally;
- an opaque public invocation identity;
- Session lookup for delegated-session ancestry;
- monotonic observer ordering.

It does not use FIFO, input equality, or completion order to correlate calls.

A tool/product error does not automatically make evidence incomplete. Evidence completeness and product outcome are separate.

## Code Mode boundary

The stock 2.0.23 experiment proved a useful partial boundary.

Supported:

- unique execution identity for each inner call;
- actual selected tool;
- decoded/executable input;
- Session/message/agent;
- actual outer \`execute\` CallID and parent invocation binding;
- start and handler-terminal ordering;
- concurrency and reverse completion identity;
- handler success-vs-error outcome.

Unsupported:

- exact final success value delivered to the Code Mode script;
- exact final error representation seen by the script catch path.

The public contract therefore keeps:

\`code_mode_execution: complete\`

when those supported facts are complete, while reporting:

\`code_mode_finality: unsupported\`

No earlier transform-wrapper value/error is promoted as caller-final evidence.

> Stock OpenCode 2.0.23 does not expose a supported boundary that proves the exact final value/error seen by a Code Mode script for each inner call. That assertion is reported as unsupported.

## Completeness and assertion eligibility

The canonical runtime-evidence implementation folds in the useful accounting behavior from PR #46:

- explicit \`complete | incomplete | unsupported | invalid\`;
- capture closure;
- missing terminals;
- observer/callback failures;
- timeout/interruption;
- malformed and duplicate observations;
- identity ambiguity;
- per-boundary coverage;
- assertion-scoped eligibility.

An unsupported boundary does not poison an unrelated complete boundary.

A redacted or omitted field also does not make an unrelated assertion fail. An assertion that requires that exact field remains ineligible.

Unknown coverage is represented as unknown field state, never numeric zero.

## Evidence safety

The evidence-safety work from PR #47 is applied before authoritative observation persistence and output sinks.

\`\`\`text
raw value in observer memory
  -> sanitize/redact/omit
  -> size decision
  -> internal capture
  -> canonical validation/accounting
  -> result serialization
  -> stdout/file persistence
\`\`\`

Public field states are only:

- \`available\`
- \`redacted\`
- \`omitted\`
- \`unsupported\`

The internal safety helper does not expose a competing \`exact\` public vocabulary.

Product \`exit_code\`, timeout, and product success/failure remain separate from evidence eligibility.

## Provider-free gates

PR #45 carries provider-free tests for:

- native success;
- native error;
- executable input;
- actor/Session/message/CallID identity;
- Code Mode observed facts;
- explicit unsupported Code Mode finality;
- concurrent identical calls with reverse completion;
- foreground delegated Session ancestry;
- incomplete/missing terminal;
- timeout;
- credential redaction before output;
- collector-shaped model/tool payload rejection.

The diagnostic Code Mode probe remains as the stock-runtime proof for the unsupported final boundary.

## Explicit unsupported areas

- Exact Code Mode caller-final value/error is unsupported on stock OpenCode 2.0.23.
- GitHub Copilot CLI invocations expose a canonical \`runtime_evidence\` object with status \`unsupported\`; they do not have the OpenCode runtime observer.
- The trusted-checkout profile does not defend the observer from a deliberately hostile plugin sharing the OpenCode process.

## Out of scope

The integrated normal profile does not introduce:

- OpenCode patch/fork;
- remote PluginHost;
- protected channel;
- HMAC or signing trust boundary;
- Cosign requirement;
- capability broker;
- hostile-plugin isolation.

Those remain optional future work only if Loom later needs to evaluate actively hostile plugin code.
