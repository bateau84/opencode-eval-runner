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
only in the separate container. The eval.2 patch disables the script `fetch`
extension in this profile, with observation on or off. The trusted adapter alone
can contact the tool service; it rejects HTTP redirects and limits response bytes.
Tool responses may contain arbitrary JSON, but
are treated as results, never observer envelopes or collector instructions.

There is **no HMAC and no signing service**. Origin follows from the private mount
and the trusted launcher/container arrangement. A SHA-256 footer is only a stream
corruption check; it does not authenticate arbitrary files. There is no CLI to
import an unsigned target file as trusted evidence. Calling the parser directly
outside the protected launcher is not an attestation. The target cannot access
the collector or submit collector messages; arbitrary host access is explicitly
outside the threat model. An attacker controlling the host could rewrite a whole
stream and recompute its checksum, so these are not malicious-host guarantees. Exported artifacts are
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

Both images require immutable references. The launcher pulls each digest and
compares the resulting image configuration IDs with `docker inspect` for the
actual containers. Image signature/signer verification remains separate and is
not implemented by this command. `observe` is provider-free: its fixed
local provider asks the real OpenCode CLI to execute the supplied program. The
normal `invoke` command and default image remain unchanged. `--no-observe` runs
the same profile with capture disabled for behavior comparison. This fixed
provider is not a general multi-turn model transport; the normal `invoke` command
has not silently acquired this profile.

The target image's entrypoint serves `GET /health` and `POST /call` on port 8080.
Calls are `{name,input,context}`; replies are either `{outcome:"returned",result:<JSON>}`
or `{outcome:"threw",error:<message>}`. This is a small remote execution adapter,
not a Code Mode runtime. `context` carries the runtime-assigned invocation ID,
dispatch ordinal, agent, session, message and enclosing call ID. The tool service
must not supply replacement identities in its reply. This metadata is separate
from the exact dispatched `input`. Actual registered identities are `isolated_<name>` and
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

Wire schema: `opencode-protected-observation/v2`. The header binds the fresh run
nonce, profile, policy digest and launcher-owned `launch_id`. Each frame retains the original
`opencode-local-observation/v1` event, with sanitized field descriptors and both
source and wire sequences. Actor/session/message, exact parent invocation,
runtime call ID, inner invocation ID, registration and catalog path remain
separate. No input-equality, FIFO, parent-ID or output-text pairing is performed.

The launcher reads program, tool catalog and policy bytes once, writes private
read-only snapshots, and binds their SHA-256 hashes, selected image digests, image
configuration IDs, fresh run ID and host collector-source hashes into `launch`.
`launch_id` is the SHA-256 of its sorted compact JSON. The runtime checks that
manifest and includes its ID in the capture header; the host compares it with
its own expected value. Editing the original inputs after snapshotting does not
change what is executed. Result replacement is atomic and does not follow a
pre-existing output-file symlink. Docker logging is disabled for both containers.

The supervisor seals only after the runtime's process group has exited. The host
checks the footer, byte checksum, consecutive source/wire sequences, parent
starts/ends, every inner terminal and source accounting. Missing data, unsupported
snapshots, redaction, clipping, interruption or transport failure cannot be
eligible. A per-parent close is not treated as a run footer. The supported scope
is explicitly one direct session's inner Code Mode calls, not all native or
child-session activity.

Projection: `observed_execution`, **version 3**, with required `profile`, retained
bindings, `parents`, `records`, `issues` and `coverage`. `evidence_eligible` is
strictly for this named profile; `full_handoff_eligible` is always false. Coverage
explicitly marks native results, delegated sessions and in-process untrusted
plugins unsupported. Existing v1/v2 consumers must not silently accept v3. A future
Loom consumer must explicitly match version/profile/run/images/policy and only
assert outcomes within supported coverage. The actual Loom consumer is unchanged.

## Verification design

`tests/integration/test_protected_connection.py` drives real Docker, the compiled
runtime and host importer. It tests legitimate capture, overlapping identical
calls, discarded results, caught throws, denial strings/objects, null, target
attempts to read/replace/delete the capture, and target-produced lookalike files
and stdout. A separate host-only receive shim corrupts **new real runtime streams**
with result replacement, cross-run replay, middle/footer deletion, truncation,
reordering and appending, including a deleted terminal with recalculated outer
checksum/counts that still fails the source-sequence/accounting checks. These are transport fault-injection tests, not a claim
that a target accessed the protected mount. Original and altered streams are
kept separately; no historical artifact is edited or promoted into new evidence.

Further runs test capture I/O failure without changing the script result,
redaction before capture storage, encoded/structured secrets, unknown values and
multibyte clipping. Unit parser fixtures remain distinct from this integration
proof. The publication workflow records exact runtime/tool image digests, source
revision, source checksums and raw sanitized captures. Test outcomes must come
from the completed run, not from this document.

## Loom integration

See [the Loom handoff](loom-protected-channel-handoff.md). The architecture is
primarily runner-owned, but adapting real Loom execution is not just a script
flag: its untrusted executable plugin code must be outside the trusted collector
process. The supplied prototype and actual Loom assertion composition have not
been substituted or declared accepted.

## Completed connection run (2026-10-03)

Tested implementation: `c1629415a814476f7b62f159530e7edd29fde738`.
[Protected-channel run #3](https://github.com/bateau84/opencode-eval-runner/actions/runs/37112938698)
passed **33 real-connection checks**. The full Python suite passed **96 tests**;
[regular CI #149](https://github.com/bateau84/opencode-eval-runner/actions/runs/37112938582)
also passed on that implementation. The downstream runtime build/source tests
passed separately. This is not an independent implementation review.

Published and tested protected runtime:

```text
ghcr.io/bateau84/opencode-eval-runner@sha256:658f4a53fba33c74f653abb613a6f38f82ec763891bc7f8c09ce1c7b7b19483d
```

Published adversarial **fixture tool image**, not a Loom implementation:

```text
ghcr.io/bateau84/opencode-eval-runner@sha256:1e1c58ac92edace961246ce577bb293c2cbcc57fabdb282aa93b6f4c481ffac0
```

The runtime includes `opencode v2.0.18-eval.2`, built from pinned upstream
`cd9a14a6b688d4021bee381dfd39d2cef9c0f862` plus the downstream patches. Default
images and installed OpenCode were not changed. These images are experimental;
Cosign signing/verification is not claimed.

[Raw evidence artifact](https://github.com/bateau84/opencode-eval-runner/actions/runs/37112938698/artifacts/11270611290)
ZIP SHA-256: `1bff745c9db5f9921f93add9eb4613c1262b38f985420b0fef0b91747250b6ed`.
It retains original and fault-injected captures separately, finalized JSON,
independent fixture diagnostics, image inspections, source archive and hashes.
The eight legitimate observations matched the actual fixture's inputs/outcomes
by runtime-carried IDs. The same public `observe` CLI succeeded with capture on
and retained the same script outcome with capture off or capture I/O failure.

The original-image diagnostic deliberately remains non-passing against
`68ef7322...`; its missing-boundary evidence has not been erased. Accordingly,
this report is not an all-checks-green PR claim or full Loom handoff acceptance.
