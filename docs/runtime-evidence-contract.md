# Runtime evidence result contract

Schema: `opencode-eval-runner/runtime-evidence/v1`

This is the authoritative runtime-observation contract for the trusted-checkout profile. It defines result shape and validation only. It does **not** implement the OpenCode observer.

Until that observer is implemented and proven, the runner emits:

```json
{
  "runtime_evidence": {
    "schema": "opencode-eval-runner/runtime-evidence/v1",
    "status": "unsupported",
    "evidence_eligible": false,
    "observations": [],
    "coverage": {
      "starts": {"state": "unsupported", "reason": "observer_not_implemented"},
      "terminals": {"state": "unsupported", "reason": "observer_not_implemented"},
      "missing_terminals": {"state": "unsupported", "reason": "observer_not_implemented"},
      "losses": [],
      "unsupported": ["observer_not_implemented"]
    }
  }
}
```

The unsupported state is intentional. `0` would incorrectly claim that a complete observer saw zero calls.

## Authority

Only `runtime_evidence` may carry authoritative runtime observations for the trusted-checkout profile.

Existing result fields remain useful product/diagnostic data, but are not substitutes:

- `tools` and `actions` are projections from OpenCode product events;
- `tool_result_evidence` is a bounded legacy projection of tool-result-shaped product events despite its historical name;
- `stdout`, `stderr`, `text`, exported/session data, model prose, workspace files, and caller/tool-provided JSON are not runtime authority.

Those fields may help debugging or presentation. They must not independently establish that a tool ran, which actor/session/call ran it, what final result/error the runtime returned, or that a call was absent.

No HMAC, signing, protected channel, peer authentication, patched OpenCode, or hostile-plugin isolation is part of this schema. The trust boundary is the reviewed runner/runtime/instrumentation and explicitly trusted checkout described by TRUST-001.

## Top-level fields

| Field | Meaning |
| --- | --- |
| `schema` | Exact schema identifier. Consumers must reject unknown versions. |
| `status` | `complete`, `incomplete`, `unsupported`, or `invalid`. |
| `evidence_eligible` | Whether the captured **scope** is complete enough to be used as runtime evidence. Field-level availability must still be checked by each assertion. |
| `observations` | Tool invocations in strictly increasing `start_sequence` order. |
| `coverage` | Completeness accounting for starts, terminals, capture loss, and unsupported boundaries. |

### Status

- `complete`: coverage counts are known; no terminal is missing; no capture loss or unsupported observation boundary is reported.
- `incomplete`: some observations may be usable, but the captured scope is not complete. Assertions that require complete/absence evidence cannot PASS.
- `unsupported`: the runner cannot establish this runtime-evidence boundary. Observations are empty and coverage counts are explicitly `unsupported`, not zero.
- `invalid`: capture or projection was malformed, ambiguous, internally inconsistent, or otherwise unsafe to consume.

`evidence_eligible` is `true` only for `status: complete` with complete coverage and no unsupported observation field. It does not make every observation field available. An assertion must also require `state: available` for every field value it depends on.

This allows, for example, a call-existence assertion to remain usable when a result value had to be redacted, while a result-content assertion is ineligible.

## Field states

Fields whose value can be unavailable use one of these exact forms:

```json
{"state": "available", "value": <any JSON value>}
{"state": "redacted", "reason": "<code>"}
{"state": "omitted", "reason": "<code>"}
{"state": "unsupported", "reason": "<code>"}
```

Meanings:

- `available`: exact projected runtime value is present. JSON `null` is a real available value, not a missing value.
- `redacted`: the runtime value was observed but must not be exposed, for example because of credential protection.
- `omitted`: the field is intentionally absent or not applicable. It must never be interpreted as `""`, `[]`, `{}`, `0`, `false`, or `null`.
- `unsupported`: the reviewed observation boundary cannot establish the field. The corresponding boundary must also appear in `coverage.unsupported`.

Missing keys are invalid. Unknown or unavailable values must never be converted to empty/default values.

## Observation fields

Each observation has exactly these fields:

| Field | Meaning |
| --- | --- |
| `invocation_id` | Non-empty observer-assigned identity for one actual invocation. Unique within the capture. |
| `tool` | Field-state value containing the actual runtime tool name. |
| `mode` | `native` or `code_mode`. |
| `actor` | Field-state value containing the runtime-selected agent/actor identity. |
| `session_id` | Field-state value containing the runtime Session identity. |
| `message_id` | Field-state value containing the runtime message/step identity associated with the invocation. |
| `call_id` | Field-state value containing the runtime call identity. It is not assumed globally unique; `invocation_id` is the observation identity. |
| `parent` | Field-state value. When available it is `{"kind":"invocation"|"session","id":"..."}` and comes from runtime facts, never a child/result payload guess. Root calls use `omitted` with an explicit reason. |
| `input` | Field-state value containing the accepted/executable input at the observed execution boundary, not model prose or a requested action. |
| `outcome` | `success`, `error`, or `missing`. |
| `result` | Field-state final value returned to the caller for `success`; `omitted` for `error`/`missing`. |
| `error` | Field-state final error returned to the caller for `error`; `omitted` for `success`/`missing`. |
| `start_sequence` | Non-negative monotonic sequence assigned at actual invocation start. |
| `terminal_sequence` | Field-state non-negative sequence for the matching terminal. It must be later than `start_sequence`; it is `omitted` for `outcome: missing`. |

Observations are ordered by `start_sequence`, never by completion order, input equality, FIFO matching, or result value. Concurrent identical calls therefore remain distinct.

For Code Mode, `result`/`error` means the final value/error exposed to the Code Mode script. If stock OpenCode cannot expose and correlate that value exactly, the field/boundary is `unsupported`; it must not be reconstructed.

## Coverage

`coverage` has exactly:

```text
starts
terminals
missing_terminals
losses
unsupported
```

`starts`, `terminals`, and `missing_terminals` are field-state integers. A known count is `available`; an unknown count is `unsupported`. Counts never default to zero.

When counts are available:

```text
missing_terminals == starts - terminals
starts == len(observations)
terminals == number of observations with outcome success|error
```

`losses` is a list of stable reason codes for capture loss or incompleteness, for example `capture_interrupted` or `record_limit`.

`unsupported` is a list of stable reason codes for observation boundaries that the reviewed runtime cannot establish, for example `code_mode_final_result_unavailable`.

A complete scope requires:

```text
missing_terminals == 0
losses == []
unsupported == []
```

Completeness is what permits absence assertions. An empty `observations` list is evidence of "no calls" only when status is `complete`, coverage counts are available and zero, and `evidence_eligible` is true.

## Validation and fail-closed behavior

The validator rejects:

- missing or unknown keys;
- unknown schema/status/mode/outcome/field states;
- duplicate invocation IDs;
- out-of-order or reused sequences;
- terminal sequences that precede their starts;
- impossible result/error/outcome combinations;
- inconsistent coverage counts;
- `evidence_eligible: true` when completeness rules are not satisfied;
- unsupported observation fields that are not reflected in `coverage.unsupported`;
- unavailable values represented as empty/default values instead of an explicit field state.

The container validates `runtime_evidence` immediately before emitting the result, and the host runner validates it again before persistence or printing. An alternate or stale image that omits or corrupts the contract is therefore rejected as infrastructure failure rather than accepted as behavioral evidence.

## Relationship to PR #41

This contract reuses the useful fidelity ideas from PR #41:

- unique invocation identity;
- start/terminal pairing;
- start-order preservation;
- explicit completeness accounting;
- field-level redaction/omission rather than fabricated defaults;
- fail-closed validation.

It intentionally drops PR #41's hostile-runtime assumptions: no evidence signing, HMAC chain, protected channel, peer authentication, patched OpenCode, or separate hostile PluginHost is required for the trusted-checkout profile.
