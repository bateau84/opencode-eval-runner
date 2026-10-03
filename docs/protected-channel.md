# Restricted protected runtime channel

## Scope, not a full-handoff claim

This is an explicit `codemode-inner/direct-session/v1` profile. It connects the
existing locally patched OpenCode `execute.observed` runtime events to the host
importer without trusting target stdout or a target-writable sidecar. It reuses
the compiled runtime and its invocation IDs, snapshots and final-result seam.
It does not implement another Code Mode interpreter or reconstruct observations.

**Arbitrary in-process plugins are not supported by this profile.** OpenCode runs
plugin code in its own process. Giving such code the observer's filesystem or
signing authority would invalidate the isolation claim. This profile instead
runs target tools in a second container and loads only the immutable trusted
transport adapter inside OpenCode. It is not a drop-in protected mode for Loom's
current in-process plugin. That integration remains open, as do native results,
delegated sessions, the preserved Loom smoke and independent code review.

## Actual protection

The trusted components are the host launcher/importer, the explicitly selected
immutable runtime image (including its adapter), host artifact storage, and the
Docker/kernel isolation boundary. Selecting a digest is a host trust decision,
not proof of safety from an image's own label. A compromised host/runtime or a
kernel/container escape is outside this threat model.

The launcher creates a fresh mode-0700 host directory. Only its `input` and
`capture` children are mounted into the trusted runtime container. The target
tool container gets neither mount, no host workspace, no Docker socket, and no
shared process namespace. Both use non-root users, read-only root filesystems,
dropped capabilities, no-new-privileges and an internal network. The provider
fixture listens only on runtime-container loopback. The runtime launches with
fresh HOME/XDG state and fixed config; no host credentials, database seeds,
extra plugin directories, command overrides or arbitrary mounts are accepted.

The fixed adapter removes unrelated tool registrations and rejects execution of
anything except the host-declared isolated tools and `execute`. That restricted
profile is identical with observation enabled or disabled. Code Mode source is
untrusted data for the existing confined interpreter. Target tool code executes
only in the separate container. Tool responses may contain arbitrary JSON, but
are treated as results, never observer envelopes or collector instructions.

There is **no HMAC and no signing service**. Origin follows from the private mount
and the trusted launcher/container arrangement. A SHA-256 footer is only a stream
corruption check; it does not authenticate arbitrary files. There is no CLI to
import an unsigned target file as trusted evidence. Calling the parser directly
outside the protected launcher is not an attestation. Exported artifacts are
trusted host artifacts, not portable cryptographic proofs.

## Runner interface

```sh
bin/opencode-eval-runner observe \
  --image <trusted-protected-runtime@sha256:digest> \
  --tool-image <isolated-tool-server@sha256:digest> \
  --program-file fixture.js \
  --tools-file tools.json \
  --policy-file policy.json \
  --output result.json
```

Both images require immutable references. `observe` is provider-free: its fixed
local provider asks the real OpenCode CLI to execute the supplied program. The
normal `invoke` command and default image remain unchanged. `--no-observe` runs
the same profile with capture disabled for behavior comparison.

The target image's entrypoint serves `GET /health` and `POST /call` on port 8080.
Calls are `{name,input}`; replies are either `{outcome:"returned",result:<JSON>}`
or `{outcome:"threw",error:<message>}`. This is a small remote execution adapter,
not a Code Mode runtime. Actual registered identities are `isolated_<name>` and
catalog paths `isolated.<name>`; they must not be relabelled as native Loom tools.
The adapter's error crosses the existing runtime error-mapping boundary and is
captured in the labelled `codemode-catch-name-message/v1` view.

`tools.json` is a host-selected list of `{name,description?,input:<JSON schema>}`.
`policy.json` is `{version:1,secrets:[...],allowed_values:[...]}`. Its digest binds
the run's redaction policy. Only exact host-approved safe values may be retained;
this is deliberately conservative and suited to deterministic fixtures. Known
literal, base64, hex and URL-encoded secrets and sensitive structured keys are
redacted **before capture persistence and before size checks**. Unknown values
are omitted rather than assumed safe. Changed values are redacted, not exact
available evidence. Oversized values have no preview. No raw runtime stdout,
stderr, tool logs or model requests are exported by the supervisor.

## Identity, completeness and eligibility

Wire schema: `opencode-protected-observation/v1`. The header binds the fresh run
nonce, profile and policy digest. Each frame retains the original
`opencode-local-observation/v1` event, with sanitized field descriptors and both
source and wire sequences. Actor/session/message, exact parent invocation,
runtime call ID, inner invocation ID, registration and catalog path remain
separate. No input-equality, FIFO, parent-ID or output-text pairing is performed.

The supervisor seals only after the runtime's process group has exited. The host
checks the footer, byte checksum, consecutive source/wire sequences, parent
starts/ends, every inner terminal and source accounting. Missing data, unsupported
snapshots, redaction, clipping, interruption or transport failure cannot be
eligible. A per-parent close is not treated as a run footer. The supported scope
is explicitly one direct session's inner Code Mode calls, not all native or
child-session activity.

Projection: `observed_execution`, **version 2**, with required `profile`, retained
bindings, `parents`, `records`, `issues` and `coverage`. `evidence_eligible` is
strictly for this named profile; `full_handoff_eligible` is always false. Coverage
explicitly marks native results, delegated sessions and in-process untrusted
plugins unsupported. Existing v1 consumers must not silently accept v2. A future
Loom consumer must explicitly match version/profile/run/images/policy and only
assert outcomes within supported coverage. The actual Loom consumer is unchanged.

## Verification design

`tests/integration/test_protected_connection.py` drives real Docker, the compiled
runtime and host importer. It tests legitimate capture, overlapping identical
calls, discarded results, caught throws, denial strings/objects, null, target
attempts to read/replace/delete the capture, and target-produced lookalike files
and stdout. A separate host-only receive shim corrupts **new real runtime streams**
with result replacement, cross-run replay, middle/footer deletion, truncation,
reordering and appending. These are transport fault-injection tests, not a claim
that a target accessed the protected mount. Original and altered streams are
kept separately; no historical artifact is edited or promoted into new evidence.

Further runs test capture I/O failure without changing the script result,
redaction before capture storage, encoded/structured secrets, unknown values and
multibyte clipping. Unit parser fixtures remain distinct from this integration
proof. The publication workflow records exact runtime/tool image digests, source
revision, source checksums and raw sanitized captures. Test outcomes must come
from the completed run, not from this document.
