# Loom handoff: isolated capture profile

> **Superseding compatibility boundary:** Loom's external entrypoint remains
> `bun run eval:live ...`, with existing case behavior and
> `scripts/run-evals.py -> opencode-eval-runner invoke` unchanged. Runner/runtime
> work belongs underneath that contract. The `observe` command and remote-tool
> profile below are supplemental restricted-smoke machinery, **not** the migration
> path for normal Loom agent/session evals. See
> [host-semantics feasibility](loom-host-semantics-feasibility.md).

## Scope of this change

The runner owns the isolated launch, private transport, collector adapter, import
validation and finalized host artifact. Its downstream OpenCode patch owns the
existing interpreter's final inner-return observation point. No second interpreter
or synthetic inner-result extractor is introduced.

The working profile is **`codemode-inner/direct-session/v1`**, exposed by the
runner's **`observe`** command. It is a provider-free, direct-session profile for
Code Mode programs calling isolated remote tools. The current result projection
is **`observed_execution.version = 5`**, with
`collection_profile = "private-supervisor-receipt/v1"`.

This is not a drop-in protected replacement for Loom's normal `invoke` path.
Arbitrary evaluated plugins cannot share the trusted OpenCode/collector process.
Native final results, delegated sessions and full Loom acceptance remain open.
The scope restriction is the same with observation on and off; it is not a claim
that restricting the profile leaves an unrestricted product environment unchanged.

## Runner-side boundary

The launcher snapshots program, tool definitions and redaction policy once. Its
launch record binds their exact hashes, the requested immutable runtime/tool
image digests, Docker's resolved image config digests, the fresh run ID, profile,
and host collector source hashes. Docker's actual started containers are checked
against that launch record. Input originals are never reopened for execution.

Only the trusted runtime receives private `/input` and `/capture` mounts. The
evaluated tool server gets neither, no host workspace or Docker socket, and no
shared PID namespace. The runtime loads only its image-owned adapter. Code Mode
has no direct network extension in this profile; external calls go through that
adapter. Remote redirects are rejected, including the tool readiness endpoint.
Both containers are non-root with read-only roots, bounded resources, dropped
capabilities, and no retained raw container logs. The provider binds only loopback.

The adapter records existing runtime events and redacts before writing. After the
runtime writer exits, the supervisor seals the file and returns a receipt
`{sha256, bytes}` over its separate, trusted control output. The host requires that
receipt as well as the file's header/footer, exact run/launch/policy bindings,
source/wire sequencing, real invocation IDs, parent identity and complete counts.
Recomputing the file's own checksum cannot replace the control receipt.

**No HMAC or signing service is used by this connection.** A checksum alone is not
authentication. The host launcher, selected trusted runtime image, immutable
adapter, and Docker/kernel isolation protect both paths. A compromised host,
collector runtime or container escape is outside this claim. Calling a parser
with invented bytes and an invented receipt does not reproduce the protected
launcher. The final JSON is a host artifact, not a portable signed attestation.

## Required Loom work

The next normal-host step is **not** to move Loom behind the remote tool service.
First preserve the existing eval entrypoint and wait for a runner/runtime path
whose protection does not replace the in-process host semantics. Loom may use the
restricted profile below only as a supplemental smoke.

### 1. Preserve and pin the actual producer and smoke

Commit or otherwise supply the exact bytes of Loom's existing
`scripts/fixtures/eval-tool-observer.ts`,
`scripts/fixtures/eval-observer-smoke-tools.ts`, and
`scripts/test_eval_observer_image.py`, plus its assertion consumer and any imports.
The previously supplied Architect draft explicitly said those prototype files
were uncommitted. A surrounding Loom HEAD does not pin their contents.

Keep that original smoke and its past artifacts intact. Add a separate integration
variant for this profile; do not relabel a runner fixture run as the original
Loom smoke, backfill old results, or reconstruct missing records from script output.

### 2. Supplemental restricted-profile pilot only: move evaluated code out of collector authority

This section does **not** define the normal `eval:live` migration. For a
fixture/tool-level supplemental pilot only, package the actual evaluated tool implementations
as an isolated tool-server image. It must serve `GET /health` and `POST /call` on
port 8080. The request is:

```json
{
  "name": "tool_name",
  "input": {},
  "context": {
    "invocation_id": "runtime-allocated-id",
    "ordinal": 0,
    "agent": "actual-agent",
    "session_id": "actual-session",
    "message_id": "actual-message",
    "call_id": "enclosing-runtime-call"
  }
}
```

Returned data uses `{"outcome":"returned","result":<JSON>}`; a remote failure
uses `{"outcome":"threw","error":"message"}`. The same code path and permissions
must be exercised in the pilot with observation on and off. Keep tool business
logic in its existing owner; do not write separate toy replacements to claim Loom
integration. The runtime/adapter chooses execution identity; identity echoed by
the untrusted server is never admitted as an observation.

The registered runtime name is `isolated_<name>` and its catalog path is
`isolated.<name>`. Do not rename these records as native `loom_*` invocations.
The error view is explicitly `codemode-catch-name-message/v1`, not preservation of
arbitrary JavaScript exception identity, stack or cause.

**For Loom's whole in-process plugin, this is architecture work, not script glue.**
Loom operations that require OpenCode plugin/session APIs need an explicit,
restricted broker before they can run in the tool container. This runner does not
provide a generic session API tunnel. Do not mount the collector state, move the
observer into the tool container, expose its callbacks, or grant a signing oracle
to make the plugin work. The whole-plugin/delegation profile remains unsupported
until that separate interface and its identity/permission semantics are reviewed.

### 3. Supply reviewed redaction policy

Materialize host-selected `tools.json` and `policy.json`. Policy v1 contains
`secrets` and `allowed_values`. The latter permits retention of exact safe values
for deterministic fixtures; it never substitutes expected values for observations.
A real unexpected return remains omitted/ineligible, not replaced with a sentinel.
Include both positive and denial/error outcomes where safe.

Unknown free text is not automatically declared safe. The collector scrubs known
literal/encoded secrets and sensitive structured keys before persistence/limits.
Changed fields remain `redacted`; unsupported, unknown and oversized fields cannot
be exact evidence. A general Loom redactor must be explicitly reviewed and placed
on the trusted side, reusing Loom's owned logic where appropriate. Do not forward
raw Loom observer files and assume host-side scrubbing undoes prior disclosure.

### 4. Call the host command and enforce the new admission rule

Use tested immutable digests from the completed **Protected runtime channel**
workflow's `protected-image.txt` and `fixture-tools-image.txt` (the latter is a
runner fixture only; substitute Loom's independently pinned actual tool image).
Record the runner/producer/consumer revisions and launch hashes.

```sh
bin/opencode-eval-runner observe \
  --image "$VERIFIED_PROTECTED_RUNTIME_DIGEST" \
  --tool-image "$PINNED_LOOM_TOOL_IMAGE_DIGEST" \
  --program-file program.js \
  --tools-file tools.json \
  --policy-file policy.json \
  --output results.json
```

The consumer must explicitly support projection version 5 and this profile. Require
matching expected run ID, launch ID, image/input/policy hashes, complete coverage,
no issues and eligible matching records before checking an outcome. Distinguish
`returned` from domain success. Interpret JSON-looking result strings only through
an explicit predicate; preserve their recorded type. The shared `runtime_call_id`
is not the unique child ID: use `invocation_id` and the full parent identity.

An eligible restricted capture still has `full_handoff_eligible: false` and explicit
native/delegated/in-process-plugin exclusions. A case requiring any excluded
surface must be BLOCKED/unsupported, not PASS. No expected call can pass on an empty
record set. Required incomplete capture exits nonzero. Never recover eligibility
from prose, outer script results, old metadata, or model claims.

### 5. Run the preserved integration composition

Run the real producer → patched image → runner host CLI/importer → actual Loom
predicates. Test overlapping identical calls with reversed completion, actual
actor/input/parent bindings, discarded returns, caught errors, denial data/null,
replayed/edited/deleted/incomplete capture, and I/O failure with unchanged outcomes.
Compare observation on/off in the same restricted profile. Preserve new and altered
fault-injection captures separately. Run with disposable HOME/XDG/workspace state
and local deterministic provider only, no installation-wide database or paid model.

Runner tests and independent Loom composition are separate evidence. Independent
code/security review remains outstanding; no merge or full acceptance follows
from CI or the fixture proof alone.

## Signing remains separate

The result explicitly reports `image_signatures_verified: false` and
`artifact_signed: false` until signing and identity verification are implemented.
Cosign should authenticate the image from the expected approved build workflow
and the finalized host JSON from the expected results signer. The trusted verifier
policy must name those identities; target JSON does not choose trusted signers.
Keep signing/OIDC authority outside both evaluated code and arbitrary artifact
submission. Signed eval input files must be verified before executing the same
snapshot. These steps complement, not replace, the protected collection path.


### Importer review clarifications

Consumers must not treat diagnostic prefix counts as evidence: require complete,
eligible capture and validated accounting. `coverage.accounting_complete` is false
on invalid/unfinished accounting; `missing_terminals` may be null when unknown.
The host now rejects inherited image volumes before launch and enforces its 16 KiB
sanitized-value limit. These fixes do not add native or delegated-session support,
turn the restricted receipt profile into full Loom proof, or supply signing.


Projection version 5 makes the accounting change explicit; consumers written for
version 4 must not silently accept it. The runtime-event and wire schema versions
and the receipt collection profile are unchanged. Historical v4 artifacts retain
their original version and meaning; a new host checkout does not rewrite them.
