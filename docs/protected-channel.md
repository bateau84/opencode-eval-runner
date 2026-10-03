# Protected runtime channel

## Supported scope

**This profile is supplemental. It is not the implementation path underneath
Loom's normal `bun run eval:live` entrypoint.** Normal-host feasibility and the
fixed `opencode-eval-runner invoke` compatibility boundary are documented in
[loom-host-semantics-feasibility.md](loom-host-semantics-feasibility.md).

`observe` connects the existing patched OpenCode final inner-call observations to
the host importer. Profile: **`codemode-inner/direct-session/v1`**. The projection
is **`observed_execution.version = 5`**, with collection profile
**`private-supervisor-receipt/v1`**. Runtime events remain
`opencode-local-observation/v1`; wire frames use
`opencode-protected-observation/v2`.

Evaluated tool code runs in a separate container. Only the selected immutable
runtime and its image-owned adapter receive the private input and capture mounts.
The runtime uses fixed configuration, no arbitrary plugin root, and the existing
confined interpreter with its direct network extension disabled. The same scope
restrictions apply with capture on and off. The normal `invoke` command, default
image and user's installed runtime are unchanged.

**This is not protected execution of Loom's current in-process plugin.** Native
results, delegated sessions and arbitrary in-process untrusted plugins are
unsupported. `full_handoff_eligible` is always false. See
[the Loom handoff](loom-protected-channel-handoff.md) for the required split.

## Protection and trust assumptions

Trusted: launcher/importer, selected runtime image, immutable adapter, host artifact
storage, Docker and the host kernel. Untrusted: interpreted program, remote tool
code, tool responses, target stdout and target-writable files. A compromised host,
trusted runtime or container escape is outside this model.

The target gets neither `/input` nor `/capture`, no host workspace, no Docker
socket and no shared PID namespace. Both containers are non-root, read-only,
resource-limited and capability-restricted, with raw container logging disabled.
The provider listens only on runtime loopback. The bridge accepts only host-listed
tools and rejects response redirects; the readiness check also rejects redirects.

The launcher reads each input once and hashes the exact snapshot it executes.
The launch ID binds run, profile, images, collector source hashes and input/policy
hashes. The actual started container image identities are checked through Docker.

The adapter redacts runtime-owned snapshots before writing the capture. After the
writer process group exits, the supervisor seals the transcript and returns a
SHA-256/length receipt over a separate trusted control path. The host requires
that receipt before parsing. It also validates the header/footer, run and launch
IDs, policy, source/wire sequences, parent relationships, each terminal and counts.
An edit followed by recomputing the file's own checksum is still rejected.

**No HMAC or signing service is used by this collection path.** Neither a checksum
nor a fabricated receipt authenticates an arbitrary file. Origin follows from
the isolated launch and protected control/data paths. The parser alone is not an
attester and there is no unsigned-target-file import command. Final host artifacts
are not portable signed proofs; image and result signing remain separate.

## Host interface

```sh
bin/opencode-eval-runner observe \
  --image <trusted-protected-runtime@sha256:digest> \
  --tool-image <isolated-tool-server@sha256:digest> \
  --program-file fixture.js \
  --tools-file tools.json \
  --policy-file policy.json \
  --output result.json
```

This command uses a deterministic local provider, not a paid model. `--no-observe`
runs the same restricted execution profile without collection. Both image references
must be immutable. Exact image digests from each completed publication/test workflow
are preserved in its artifact; they are not interchangeable with a mutable tag or
local image ID.

The target serves `GET /health` and `POST /call` on port 8080. The request contains
`name`, unchanged `input`, and runtime-selected `context` (invocation ID, ordinal,
agent/session/message/enclosing call). Returned JSON and remote failure replies are
defined in [the handoff](loom-protected-channel-handoff.md). Target-supplied identity
or observer-shaped response fields remain ordinary data, never collector claims.

`tools.json` is the host-selected list of names and input schemas. `policy.json`
contains `version: 1`, configured `secrets`, and exact `allowed_values` for safe
fixture retention. Known literal/encoded secrets and sensitive structured keys are
redacted before persistence and size checks. Unknown values are omitted; changed
fields stay redacted and oversized fields have no preview. Allowed values permit
retention only: they never replace an actual unexpected result.

No raw CLI stdout/stderr or tool logs become evidence artifacts. The separate
`script_output` field is a sanitized behavior-test diagnostic, not inner evidence.

## Admission and verification

Consumers must explicitly accept version 5 and this profile, match the trusted
launch record, require complete eligible capture/records, and inspect actual tool
outcomes. A returned denial is not domain success; a JSON-looking string remains
a string. Any unsupported scope, missing terminal, failed receipt, omitted field,
redaction, interruption, corruption or unknown accounting prevents positive
assertion. An empty capture cannot satisfy an expected call.

`tests/integration/test_protected_connection.py` runs real Docker, the compiled
runtime, public host CLI and importer. Target attacks and host receive-side fault
injection are separate: the former attempt mount/process access and fake outputs;
the latter alter newly collected streams, including replay, deletion, reordering
and a result edit with recomputed checksum. Original and altered captures are
stored separately. Source/runtime tests, fixture integration, independent review
and actual Loom composition remain distinct requirements.

[Complete Loom integration instructions and remaining scope](loom-protected-channel-handoff.md).


## Review hardening

Capture accounting is separate from evidence eligibility. `coverage.starts` and
`coverage.terminals` retain counts from the validated prefix on a later semantic
failure; `missing_terminals` is unknown (`null`) until that accounting starts.
`accounting_complete` stays false unless all source accounting is validated.
Unknown omissions remain null, and invalid captures still admit no records.
These counters are diagnostic, never a way to promote a valid-looking prefix.
Parent and child invocation IDs share one capture-wide uniqueness requirement.
The host enforces the 16 KiB sanitized-value bound using compact UTF-8 JSON.

Image-declared volumes are rejected before any container is launched. Tools that
need temporary state must use the profile's existing disposable writable space,
not an inherited image `VOLUME`. Cleanup removes anonymous volumes associated
with this launch's containers; it does not prune unrelated host volumes. Fixed
launcher-policy failures retain their non-sensitive reason codes.

The experimental image workflows separate read-only build/test jobs from fresh
publication jobs that have no checkout and never execute their image artifacts.
A further read-only job tests the published digests. Publication is not code
approval, a Cosign signature, or a change to default image pins. Repository owners
and authorized workflow editors remain trusted; this boundary prevents tested
code/process residue from sharing publication credentials, not malicious edits to
the publisher workflow itself.


Projection version 5 makes the accounting change explicit; consumers written for
version 4 must not silently accept it. The runtime-event and wire schema versions
and the receipt collection profile are unchanged. Historical v4 artifacts retain
their original version and meaning; a new host checkout does not rewrite them.
