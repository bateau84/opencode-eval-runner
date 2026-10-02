# Execution observer export v1 — integration candidate

## Status and ownership

This is the **runner-side export implementation and proposed producer contract**
for the Loom feature handoff `Export trustworthy Code Mode inner-call results for
evals`. It is not a claim that Loom's observer already emits this contract.

Inspected upstream baseline:

- Runner: `ad4d6a26fc137202e4f35f2a14503f53b81991ca`.
- Loom branch `functionality-anchor-requirements-coherance`:
  `6e255092388a57f141e609fee954cb7ae5977d4b`. No published observer wire contract was
  found in the inspected eval harness and source tree.
- OpenCode image from the handoff:
  `ghcr.io/bateau84/opencode-eval-runner@sha256:68ef7322c75aede0e8cc76d0e3531e8b82dd417bbb5e5100264a89eab7fe8627`.

**Loom owns observation**, including actual hook results/errors, exact actor and
session, unique invocation correlation, concurrency-safe sequencing, safe
redaction, and proof that no later hook mutates the returned value. The runner
owns authenticated transport admission, bounded parsing, completeness validation,
sanitized projection, and the evidence exit gate. No production hook, tool wrapper,
provider, or second observer is installed here.

The PR stays draft until the Loom Worker agrees/adapts the producer contract and
the real deterministic-provider OpenCode integration tests below pass. Authentication
must not be used to paper over an unsupported observation boundary.

## No image rebuild for this export path

The old host runner accepts arbitrary additional mounts/environment names, but
only copies the container's outer result JSON to the final artifact. It neither
imports a sidecar nor authenticates/completeness-checks one.

The new host runner uses that existing OCI mount/environment mechanism, imports
the sidecar **after invocation**, and adds `observed_execution` alongside existing
fields such as `observed_tool_results`. `container/invoke.py`, `Containerfile`, the
OpenCode executable, and image pins are unchanged. `Containerfile` copies only
`container/`, not `runner/`, into the runtime image. This implementation therefore
needs an updated **host checkout**, not a new image digest. It does not deploy or
claim to update an already published image.

A future upstream hook/runtime change may still require new image bytes. That
change must publish and report its actual immutable digest separately.

## CLI boundary

```sh
bin/opencode-eval-runner invoke \
  --transport opencode \
  --image ghcr.io/bateau84/opencode-eval-runner@sha256:68ef7322c75aede0e8cc76d0e3531e8b82dd417bbb5e5100264a89eab7fe8627 \
  --workspace /disposable/eval-workspace \
  --model fixture/model \
  --prompt-file /disposable/prompt.txt \
  --observer-key-file /trusted-host/observer.key \
  --output /disposable/artifacts/result.json
```

This is an integration example, **not a working fixture provider configuration**.
The observer and deterministic provider must be supplied by the trusted harness.

`--observer-key-file` is OpenCode-only and opts into **required** capture. The
runner creates a fresh private-lifetime capture directory, mounts it read/write at
`/eval-observer`, and supplies only these public values to the target:

| Variable | Meaning |
| --- | --- |
| `EVAL_OBSERVER_PROTOCOL` | `1` |
| `EVAL_OBSERVER_RUN_ID` | Fresh random 256-bit nonce for this invocation |
| `EVAL_OBSERVER_PATH` | `/eval-observer/records.jsonl` |

The corresponding path on the host is a per-run temporary directory. The trusted
observer integration may materialize the file through the mount. The directory is
not a trust boundary; target code may see, overwrite, or delete its contents.
Authenticity comes from the independent producer described below. No key path or
key bytes are added to container arguments or forwarded environment variables.

The key must be a private, regular, single-link file with at least 32 bytes and no
more than 4096 bytes, outside **every** container mount. Do not place it in the
workspace, config root, seeds, or any extra mounted tree. Symlinks/hardlinks,
nonprivate permissions, a directly forwarded raw/hex/base64 key, and colliding
observer environment/mount options are rejected. These checks cannot discover
arbitrary copies of a key: keeping the signer and all key copies outside the
untrusted execution environment remains a deployment obligation.

The container's original fields and semantic results are not reinterpreted. An
otherwise successful invocation exits **4** when required observer evidence is
unavailable, incomplete, unsupported, or invalid. Existing nonzero transport exit
codes are preserved. Timeout/invalid outer JSON writes a non-evidence artifact and
exits 2. This is an **eval evidence gate**, not a change to tool behavior.

Without the flag, no observer mount/environment is added and the old invocation
exit behavior remains. The new field is explicitly unavailable with reason
`capture_not_requested`. Any same-named field supplied by the container is always
replaced: stdout cannot self-attest a trustworthy observer projection.

## Trust boundary — a key in Code Mode is NOT authentication

The key is shared only by the trusted producer and the host verifier. HMAC-SHA256
is used to authenticate a stream, not to establish whether its author observed
reality. The deployment must ensure that evaluated scripts, shell tools, other
untrusted child processes, and plugins under evaluation cannot read/use the key
or ask a signer to authenticate arbitrary claimed results. Merely hiding a key
in a closure, environment variable, workspace file, or same-user sidecar is not a
proof of that isolation.

An execution-hook observer in OpenCode needs a reviewed, protected connection to
the signing/export boundary. **This runner PR does not implement or claim that
connection exists.** If the current hook implementation cannot establish it, do
not enable positive evidence: report unsupported capture or allow missing capture
to fail closed. There is deliberately no `trust-unsigned` escape hatch.

The trust model includes the host launcher, host verifier, and final host artifact
storage. It does not claim protection from a compromised host or a dishonest
trusted producer. A final artifact is not a standalone signed attestation; keep it
outside evaluated workloads. Do not retrofit this projection into historical
artifacts.

## Authenticated JSONL wire contract

Each newline-terminated frame is a JSON object with exactly two string keys:

```json
{"payload":"<base64 of exact UTF-8 event JSON bytes>","mac":"<lowercase hex HMAC-SHA256>"}
```

For frame `i`, compute:

```text
mac_i = HMAC-SHA256(
  key,
  UTF8("opencode-eval-observer/v1") || 0x00 || ASCII(run_id) || 0x00 ||
  previous_mac_bytes || payload_bytes
)
```

`previous_mac_bytes` is 32 zero bytes for frame zero; subsequently it is the
previous frame's 32-byte MAC. The payload is the **exact original bytes**, not
re-serialized JSON, so producers need not share Python's number or key-order
formatting. `payload` uses standard base64. Each payload contains `run_id`, integer
`seq` starting at zero with no gaps, and `kind`.

The nonce rejects cross-run replay; chaining and sequence validation reject
removed/reordered/duplicated records; a mandatory authenticated footer makes
interrupted suffixes incomplete. Appending anything after the footer invalidates
the capture. Signatures must cover redacted records, not raw secrets.

### Header (`seq: 0`)

```json
{
  "kind":"capture_start", "version":1, "run_id":"<nonce>", "seq":0,
  "source":"loom-execution-hook",
  "boundary":"tool-return-to-caller",
  "correlation":"execution-invocation-id",
  "ordering":"monotonic-sequence"
}
```

These are producer commitments, not magic strings that grant trust. The producer
must demonstrate that `tool-return-to-caller` is the **final** native/Code Mode
return or throw boundary, independent of script return values and after any
output-changing hook. A `tool.execute.after` observation is insufficient if a
later hook can still change the result. Unknown versions/boundaries are rejected.

### Call start

```json
{
  "kind":"call_start", "run_id":"<nonce>", "seq":1,
  "invocation_id":"observer-unique-inner-1", "tool":"sentinel",
  "mode":"code_mode",
  "actor":{"agent":"worker","session_id":"actual-child-session"},
  "parent":{"session_id":"actual-parent-session","call_id":"execute-call"},
  "input":{"state":"available","redaction":"safe","value":{"n":42}}
}
```

`mode` is `native` or `code_mode`. Native calls may use `parent: null`; Code Mode
calls require a parent. Parent identity is the pair `(session_id, call_id)`. The
producer-assigned `invocation_id` must be unique **across the entire capture** and
must be carried through the actual execution context to its terminal callback.
Do not derive it by pairing tool name/input, arrival order, parent call ID, or
requested actor. All identifiers are nonempty bounded ASCII tokens (up to 256
characters; letters, digits, `_ . : / @ -`). Unsafe/unsupported identity is not
silently guessed, normalized, clipped, or repaired.

### Call terminal

```json
{
  "kind":"call_end", "run_id":"<nonce>", "seq":2,
  "invocation_id":"observer-unique-inner-1", "outcome":"returned",
  "result":{"state":"available","redaction":"safe","value":"raw sentinel"}
}
```

A throw uses `outcome: "threw"` and `error` instead of `result`. Exactly one terminal
is allowed per invocation. A terminal references the authenticated start binding,
not a new actor/input supplied by the script. Completion may occur in any order.

Result values stay their observed JSON types. In particular, a string containing
JSON stays a string. JSON `null` is an actual value. Non-JSON values/JS `undefined`
must be explicitly omitted by the producer, not coerced into invented JSON.
Domain-denial JSON is still `returned`, **not** a thrown failure or a successful
domain operation. The consumer must inspect the actual value.

### Field availability and redaction

`input`, `result`, and `error` each use a field descriptor:

| State | Meaning |
| --- | --- |
| `available` | Exact representable JSON value with authenticated `redaction: "safe"` |
| `redacted` | Safe value remains but it is no longer exact original evidence |
| `omitted` | No trustworthy/safely serializable value is available |
| `truncated` | The complete value was not retained |

The producer must establish safe redaction **before persistence/signing**. A
missing safe-redaction claim causes omission, with no preview or raw reason text.
The runner additionally scrubs known host secrets (including encoded verifier
key forms) and sensitive structured keys recursively, before checking field size.
It does not pretend that generic regexes can discover every unknown secret in
free text; that is why authenticated producer redaction is mandatory. Oversized
fields are marked truncated with no misleading partial value. Producer-supplied
omission reasons/previews are not copied. Redacted, missing, or truncated fields
make this v1 capture ineligible for positive deterministic assertions.

### Footer

```json
{
  "kind":"capture_end", "run_id":"<nonce>", "seq":3,
  "calls_started":1, "calls_ended":1,
  "omitted_records":0, "truncated":false, "unsupported":[]
}
```

Counts must match the records actually emitted. The producer must set omissions,
truncation, and unsupported coverage truthfully and must not sign a complete
footer while any invocation/flush is still pending. `unsupported` contains bounded
non-sensitive reason identifiers. A missing footer, missing terminal, omitted
record, unsupported segment, or truncated field/capture cannot be evidence for
PASS. Merely having some valid calls does not make a partial capture complete.

Limits: 8 MiB total capture, 256 KiB per frame, 10,001 frames, and 16 KiB per
sanitized field. Limit breaches explicitly reject/mark the capture; no clipped
prefix is promoted to complete evidence. Duplicate JSON keys, non-finite numbers,
invalid encoding, unsupported record shapes, and unsafe filesystem objects fail
closed. The importer reads only its fresh capture path, never a Loom database.

## Exported projection and consumer rule

```json
{
  "observed_execution": {
    "kind":"execution-observer-projection", "version":1,
    "run_id":"<fresh nonce>", "status":"complete", "evidence_eligible":true,
    "records":[{
      "invocation_id":"observer-unique-inner-1", "tool":"sentinel",
      "actor":{"agent":"worker","session_id":"actual-child-session"},
      "parent":{"session_id":"actual-parent-session","call_id":"execute-call"},
      "mode":"code_mode", "start_sequence":1, "terminal_sequence":2,
      "input":{"state":"available","value":{"n":42}},
      "outcome":"returned", "result":{"state":"available","value":"raw sentinel"},
      "evidence_eligible":true
    }],
    "issues":[],
    "coverage":{
      "capture_started":true, "capture_ended":true,
      "observed_starts":1, "observed_terminals":1, "missing_terminals":0,
      "omitted_records":0, "truncated":false, "unsupported":[]
    }
  }
}
```

Records are in **start order**. `terminal_sequence` captures completion order;
there is no claim that overlapping calls executed serially. Missing terminals
use `outcome: "missing"` and no result/error. Valid authenticated prefixes may be
retained for diagnosis, but every record remains ineligible when the overall
capture is incomplete. Invalid/authentication-failed captures export no records.

The consumer must require version 1, `status == "complete"`,
`evidence_eligible is true`, no issues, complete coverage, and eligible matching
records **before** asserting the requested tool outcome. Eligibility is necessary,
not sufficient for PASS: an empty capture does not satisfy an expected call; a
completed/returned call does not imply domain success. Never fall back to execute
source, parent output, CLI status, or old metadata when inner evidence is absent.
The Loom consumer still needs to adopt this rule; this PR does not silently change
Loom's existing judge or historical artifacts.

## Verification and acceptance gaps

Run the provider-free runner tests with:

```sh
python -m unittest discover -s tests -p 'test_observer.py' -v
```

The test-only producer independently encodes authenticated frames. Real local
subprocesses emulate OCI transport and exercise the actual host CLI, mounts,
environment forwarding, result-file export, and exit codes. Tests use disposable
HOME/XDG/workspace/key state, no real provider, and no installation-wide database.
The fake engine's access to a fixture-only signing key is **not evidence of signer
isolation in OpenCode**.

Covered exporter properties include native/nested-shaped sentinel preservation,
script-controlled outer-output independence, denial strings vs throws, identical
inputs/shared parents/reverse completion, no guessed pairing, missing footer and
terminal, replay/forgery/reordering, malformed input, symlinks/FIFOs/hardlinks,
redaction before clipping, explicit unsafe-field omission, fresh nonces, unchanged
product arguments/results, key non-forwarding, and nonzero indeterminate gates.

Before marking CAP-AC-001 through CAP-AC-004 end-to-end complete, Loom must supply:

1. Its real observer implementation/revision and the agreed/adapted wire contract,
   with a protected producer/signing boundary. No duplicate observer should be
   added to this repository.
2. An actual supported execution-context identity shared by start/end callbacks,
   including overlapping identical calls and actual subagent session/actor.
3. Proof that the hook sees the final returned value or thrown error, not a value
   subsequently changed by another plugin or the Code Mode runtime.
4. A deterministic provider fixture running OpenCode 2.0.18 native and Code Mode
   tools: discard/transform returns, catch exceptions, return denial JSON,
   reverse completion order, and inject interrupted/forged capture. Run with
   observer on/off and verify unchanged tool behavior/permissions. Consume the
   exported projection through Loom's real deterministic assertion path.

Runner fixture tests support the export contract. They do **not** discharge those
real-runtime capture, signer-isolation, or Loom-consumer acceptance obligations.
No live provider run or rebuilt/published image is claimed.
