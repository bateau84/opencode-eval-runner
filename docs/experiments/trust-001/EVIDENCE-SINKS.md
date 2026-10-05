# Provisional first-sink inventory

Status: **Wave-1 planning**.

A path is in scope because it actually persists, clips, logs, or exports candidate evidence—not because of component ownership or filename.

## Rule

Synthetic credentials that enter candidate observation or diagnostic paths must be protected **before** the first candidate-controlled persistence, clipping, logging, or export boundary.

Calling a stream "non-evidence" is not permission for candidate code to persist or export raw sensitive values. A later checksum/rejection can protect integrity/eligibility but cannot undo disclosure.

Normal stock OpenCode and Loom product stores are separate product semantics. They are outside the runner evidence-safety claim unless the candidate copies, exports, or relies on their contents; such a copy/export becomes a new first sink.

## Proposed candidate paths

| Path | Kind | Raw evidence allowed? | First protection requirement | Status |
|---|---|---:|---|---|
| bridge callback/event objects in process memory | transient trusted memory | yes, bounded | no persistence/logging before handoff; bounded input validation | design |
| bridge → host collector evidence socket | transient trusted IPC | yes, bounded | distinct collector-only endpoint/protocol; no disk/log clipping; bounded frames; trusted peer/channel authority | design |
| bridge ↔ isolated Loom capability socket | transient product IPC | yes, bounded | separate endpoint/protocol; no raw transcript; **never** accepted as evidence authority | design |
| host collector in-memory correlation table | trusted memory | yes, bounded | safety projection before any persistence/preview | design |
| collector temporary/intermediate evidence file | evidence persistence | **no** | only projected safe representation may be written | required |
| runner final result file | evidence persistence | no | existing safe atomic writer/admission pattern | existing design to reuse |
| `--print-result` stdout | evidence export | no | print only validated projected result | existing design to reuse |
| broker/bridge diagnostic logs | diagnostic persistence/stream | no payload | fixed reason codes/IDs only; never raw callback/product payload | required |
| OCI engine logs for candidate containers | persistence | no raw candidate payload | disable/raw-log-driver path for the confidentiality profile or prove projection before persistence; never rely on raw logs as evidence | required |
| Loom isolated stdout/stderr | product/diagnostic stream | transient product data may exist | if runner/engine persists or exports it, that path becomes a first sink and must be disabled or projected first | required |
| OpenCode raw stdout/stderr | product/diagnostic stream | transient product data may exist | if runner/engine persists or exports it, that path becomes a first sink and must be disabled or projected first | required |
| crash/core dump | persistence | no | disable or ensure unavailable/non-persistent | required |
| source/image/component metadata | provenance | safe metadata only | no credential-bearing paths/values | design |

## Explicit non-evidence product stores

The candidate should **not** make these stores authoritative evidence sources:

- Loom's `execution-state.sqlite`;
- stock OpenCode Session database;
- shell output files;
- arbitrary workspace files;
- dashboard state;
- model transcript prose.

These stores may contain ordinary product data under stock/Loom semantics. The runner confidentiality claim does not retroactively sanitize them. If candidate code copies, clips, logs, exports, or promotes their contents, that new path enters this sink inventory.

State-dependent Loom assertions should use a later trusted runtime tool/query whose invocation/result is itself observed, rather than reading these stores directly as runner evidence.

### Stock Session events

The trusted bridge may consume the **live stock event stream** as a runtime observation source. This is distinct from replaying the Session database as evidence after the fact.

Normal OpenCode persistence of its own product Session history remains product behavior. If a future design reads that stored history as runner evidence, it becomes a new evidence path and must return to sink review.

## Capability channel versus evidence channel

The Loom capability channel transports product callbacks and results. It is **not** an evidence-authority channel.

Requirements:

- physically/logically distinct endpoint and accepted descriptor from the evidence channel;
- no collector authentication material or evidence framing on the capability channel;
- no raw channel transcript persisted;
- no debug payload logging;
- bounded frame size before allocation growth;
- oversize/malformed requests rejected with fixed diagnostics;
- compromise or replay on the capability channel can only fail/unresolve product work and completeness;
- trusted collector records only observations received through the admitted evidence channel and its own correlated/safe projection.

## Clipping

No raw evidence field may be clipped and then described as complete.

Order:

```text
raw trusted observation
  -> safety projection/redaction/omission
  -> size decision
  -> persistence/export
```

Unsupported/oversized values are omitted before evidence persistence.

## Candidate construction obligation

Wave 2 must replace this provisional table with the **actual** sink inventory.

Discovery of any unreviewed first sink is a checkpoint stop condition. The candidate must update the sink manifest and rerun affected confidentiality review before later evidence is usable.
