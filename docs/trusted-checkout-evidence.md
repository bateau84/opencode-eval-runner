# Trusted-checkout runtime evidence

Status: **replacement direction for TRUST-001**.

This document supersedes the hostile-runtime direction explored in PR #41 and PR #43. Those PRs remain useful research/reference material, but normal Loom evaluation does not require the runner to defend itself from a deliberately malicious Loom checkout that shares its runtime authority.

## Contract

### TRUST-001 — authoritative runtime observation

For evaluation of an explicitly trusted checkout, evidence used for scoring MUST originate from reviewed runtime instrumentation observing actual execution.

The following MUST NOT independently establish that an event occurred:

- model assertions or generated prose;
- tool payloads shaped like collector/evidence records;
- requested or intended actions;
- inferred actor, parent, or execution identity;
- reconstructed results;
- target-writable evidence files.

Required observations MUST preserve enough runtime identity and ordering to evaluate the consumer contract, including actor/session/call identity, input, result or error, parent binding where applicable, and execution order.

Missing, partial, ambiguous, lost, or unsupported required observations MUST make the affected assertion ineligible for PASS. The runner MUST NOT fill gaps from model text, stdout, workspace files, or guessed correlations.

The trusted-checkout profile does not claim protection against malicious modification of the runner, stock OpenCode process, reviewed instrumentation, evaluated checkout, or their dependencies.

## Trust model

Trusted components:

- the selected `opencode-eval-runner` revision;
- pinned **stock OpenCode 2.0.23**;
- reviewed runtime instrumentation;
- the explicitly selected Loom checkout and its reviewed dependencies;
- host-side evidence projection/persistence code.

Not trusted as evidence authority:

- model output;
- agent claims;
- tool-returned collector-shaped data;
- normal product/session/workspace files;
- caller-supplied identity or completeness claims.

This is an evaluation-correctness boundary, not a hostile-code security boundary.

## Required evidence behavior

The target behavior remains strict even though the security scope is smaller:

- **Native calls:** observe the actual runtime call, actor/session/call identity, accepted/executable input, and terminal result/error.
- **Code Mode inner calls:** assign a unique runtime observation identity per actual inner invocation, bind it to the real outer `execute` call, and observe the final value/error that Code Mode exposes to the script.
- **Delegation:** derive child Session identity and ancestry from runtime facts, not a parent result payload.
- **Ordering:** preserve runtime observation order; do not correlate concurrent calls by FIFO or input equality.
- **Completeness:** explicitly report missing starts/terminals, capture loss, unsupported boundaries, and incomplete scope.
- **Confidentiality:** redact or omit credentials before the runner first persists, clips, logs, or exports evidence.
- **Noninterference:** observation must not add product retries or change normal Loom execution semantics.

If stock OpenCode's supported interfaces cannot expose an exact required boundary, the result is `unsupported`/ineligible for that assertion. The response is not to invent evidence and not to turn the normal profile into a hostile-code isolation project.

## Implementation direction

Keep the normal path:

```text
Loom eval harness
  -> opencode-eval-runner invoke
  -> stock OpenCode 2.0.23
     + reviewed runner-owned observation instrumentation
     + trusted Loom checkout
  -> safe host projection
  -> Loom judging
```

The preferred implementation is same-process reviewed instrumentation using supported stock OpenCode plugin/runtime surfaces. It may use a runner-owned observer plugin, tool/session hooks, live runtime events, and reviewed wrappers where those surfaces preserve the required boundary.

OpenCode source patches, forks, remote PluginHost isolation, evidence signing, and a capability broker are not requirements of this profile.

Provider-free integration tests must prove the exact observation/correlation behavior before a field becomes eligible evidence.

## Reuse from PR #41

| Work | Disposition |
| --- | --- |
| Evidence-safety projection/redaction and fail-closed field handling | **Reuse/adapt**; keep the behavior, decouple it from hostile-runtime image/signing assumptions |
| Credential protection before host/file/print sinks | **Reuse** |
| Disposable OpenCode state/profile work | **Reuse where useful** for deterministic eval isolation |
| Normal `invoke` compatibility and provider-free integration probes | **Reuse/adapt** to stock 2.0.23 |
| Native/Code Mode observation schemas and concurrency tests | **Reuse as behavioral requirements/tests** |
| Delegated-session identity/ancestry probes | **Reuse** |
| Patched OpenCode runtime | **Drop** |
| HMAC observer/import trust boundary | **Drop** for the normal profile |
| protected-channel / remote tool service | **Drop** |
| plugin isolation / remote PluginHost work | **Drop** |
| Cosign evidence-authenticity machinery | **Drop** as a TRUST-001 prerequisite |
| adversarial same-authority attack tests | **Move to optional future untrusted profile** |

## Reuse from PR #43

| Work | Disposition |
| --- | --- |
| Stock OpenCode 2.0.23 source/capability assessment | **Reuse** |
| Identification of public Session/event/tool surfaces | **Reuse** |
| Scope/completeness rules that prevent false absence/PASS | **Reuse and simplify** |
| First-sink confidentiality inventory | **Reuse and simplify** |
| Loom callback/capability inventory | **Reference when needed for compatibility** |
| hostile-runtime TCB/authority model | **Drop** from the normal profile |
| isolated Loom execution domain | **Drop** |
| capability/evidence-channel peer-authentication requirements | **Drop** |
| OCI adversarial boundary experiment/gates | **Drop** |

## Implementation sequence

This is normal engineering work, not a multi-authorization security experiment:

1. Pin and verify stock OpenCode 2.0.23.
2. Add the smallest reviewed observation instrumentation that can capture native and Code Mode execution without changing product semantics.
3. Port the useful PR #41 evidence-safety projection so captured values are protected before persistence/export.
4. Add explicit completeness/loss fields and fail closed when required data is missing.
5. Exercise direct, Code Mode, delegation, error, timeout, and concurrent reverse-completion cases provider-free.
6. Compose through Loom's existing `eval:live -> run-evals.py -> invoke` path.
7. Only after those checks pass should Loom consume the new evidence schema for PASS/FAIL decisions.

A future **untrusted-plugin execution profile** may add isolation if there is a real need to evaluate hostile plugin code. It must remain optional and separate from the normal trusted-checkout path.
