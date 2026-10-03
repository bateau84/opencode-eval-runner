# Loom handoff: protected direct-session capture

## What the runner owns

The runner now supplies a restricted, opt-in connection from the locally patched
OpenCode runtime to the host importer. The trusted runtime and collector are in
one container; evaluated tool implementations execute in another. Only the
runtime receives the private capture and launch-input mounts. The existing Code
Mode interpreter is retained; its script network extension is disabled for this
profile, regardless of whether observation is enabled.

This is **primarily a runner/runtime change, but it is not a drop-in flag for the
current in-process Loom plugin**. An untrusted plugin cannot remain in the
collector's process and still satisfy this threat model. Loom needs an execution
adapter as well as script/consumer changes. No Loom repository files are modified
by this PR, and no native or delegated-session coverage is claimed.

The runtime supplies actual `execute.observed` events. The fixed trusted bridge
is a transport/redaction adapter for that seam, not another interpreter. This
implementation has not incorporated the uncommitted Loom observer prototype or
claimed that its original bytes were tested. Preserve and pin those bytes before
adapting it; do not run a competing target-writable logger and promote its output.

## Tested runner baseline

Use implementation commit `c1629415a814476f7b62f159530e7edd29fde738` or its
reviewed descendant, and this protected runtime image:

```text
ghcr.io/bateau84/opencode-eval-runner@sha256:658f4a53fba33c74f653abb613a6f38f82ec763891bc7f8c09ce1c7b7b19483d
```

The runner's 33-check connection run used adversarial fixture tools, not the real
Loom plugin. See [the validation record](protected-channel.md#completed-connection-run-2026-10-03).
The architecture and implementation remain draft pending independent review.

## 1. Isolate actual Loom execution

Package the actual evaluated Loom tool implementations behind a service in a
separate non-root image. Do not copy or reimplement their behavior in a sentinel
fixture. Keep any needed mutable state disposable and inside that tool boundary;
there is no mount for the user's installation-wide Loom database.

The initial runner adapter expects a service on port 8080:

- `GET /health` returns HTTP 200.
- `POST /call` receives `{name,input,context}`. `input` is the exact dispatched
  input, not modified to carry observation metadata.
- `context` contains `invocation_id`, `ordinal`, `agent`, `session_id`,
  `message_id`, and `call_id` from the trusted runtime dispatch. It is not supplied
  by Code Mode source or reconstructed from a reply. `ordinal` is dispatch order,
  not network arrival order and not a replacement for invocation identity.
- Replies use either `{outcome:"returned",result:<JSON>}` or
  `{outcome:"threw",error:<message>}`. The trusted adapter retains its own context;
  target replies cannot replace actor or invocation identity.

The current adapter registers names as `isolated_<name>` and exposes catalog
paths `isolated.<name>`. **Do not relabel them as native Loom registrations.** A
future mapping must preserve the actual registration identity and be explicitly
versioned/reviewed. Session delegation and permissions that depended on an
in-process plugin require real integration work; this transport alone does not
preserve every Loom behavior. Do not bypass those checks to make a smoke pass.

## 2. Adapt the launcher in `scripts/run-evals.py`

For cases explicitly declaring the supported profile, invoke the PR checkout:

```sh
bin/opencode-eval-runner observe \
  --image <approved-protected-runtime@sha256:digest> \
  --tool-image <actual-isolated-Loom-tools@sha256:digest> \
  --program-file <preserved-smoke-program.js> \
  --tools-file <selected-tool-catalog.json> \
  --policy-file <reviewed-redaction-policy.json> \
  --output <host-artifact.json>
```

The runner reads inputs once, creates a private read-only snapshot, and records
its hashes and the actual launched image identities. Do not reopen mutable source
files after verification. Keep the result file on the trusted host, not in a
workspace the evaluated code can write.

`observe` currently uses a deterministic loopback provider that asks the real
OpenCode CLI to execute one supplied program. It is **not** a replacement for the
normal multi-turn `invoke` transport. Do not route arbitrary existing agent evals
through it and claim equivalent agent/session behavior.

`--no-observe` executes the same restricted profile without capture for comparison.
The capture switch does not enable/disable additional product permissions.

## 3. Agree redaction and explicitly consume the projection

The current conservative policy is:

```json
{"version":1,"secrets":[],"allowed_values":[]}
```

Known secret forms and sensitive structured keys are scrubbed before capture
persistence. Only exact host-approved safe values are retained; changed values
are marked redacted, unknown values omitted, and oversized values truncated
without a preview. All such losses prevent positive evidence. **This exact-value
policy is intended for deterministic smoke fixtures, not yet a general live-eval
redactor.** A broader policy must be reviewed and demonstrated before deployment.

Wire schema is `opencode-protected-observation/v2`. Exported `observed_execution`
uses **version 3**, profile **`codemode-inner/direct-session/v1`**. These are not
aliases for the earlier v1 HMAC importer or v2 projection.

Adapt the existing Loom deterministic assertion consumer to require the agreed
version/profile and the expected launcher-owned `run_id`, `launch_id`, images,
input hashes and policy. A result cannot choose its own trust policy. Require
`status == "complete"`, `evidence_eligible is true`, no issues, complete coverage,
and eligible matching records with exact available fields before an assertion.
Then evaluate the actual outcome; returned denial JSON is not operation success.
Check `start_sequence` and `terminal_sequence` separately. A complete capture is
not itself an eval PASS, and an empty capture cannot satisfy an expected call.

`full_handoff_eligible` remains false. Required native calls, delegated actors or
in-process untrusted plugins must stay unsupported, not silently ignored. Never
fall back to source text, target stdout, outer script output, requested actor,
legacy metadata, or exit zero. Nonzero runner outcomes also require non-PASS.

## 4. Preserve and rerun Loom's own smoke

Pin the actual revisions/bytes of:

- `scripts/fixtures/eval-tool-observer.ts`
- `scripts/fixtures/eval-observer-smoke-tools.ts`
- `scripts/test_eval_observer_image.py`
- the actual deterministic assertion consumer and adapter.

The supplied Architect draft said those prototype files were uncommitted; the
old Loom HEAD is not a pin for them. Retain the old smoke and reports. Add a new,
explicit profile-specific run rather than weakening assertions or rewriting old
artifacts. Use the newly published runtime digest plus the actual isolated Loom
image and record loaded configuration and all revisions.

Exercise legitimate capture, reversed completion of identical overlapping calls,
discarded/transformed results, caught errors, returned strings/objects/null,
target forgery attempts, replay/deletion/interruption, redaction and I/O failure.
Compare observation on/off, then run the real Loom predicates. The runner's own
fixture/oracle tests are not a substitute for this composition test.

## Remaining review and signing

The host launcher/importer, pinned runtime/collector image, host storage and
Docker/kernel isolation are trusted. Target code has no collector endpoint or
signing capability. The checksum is for corruption detection, not protection
against a malicious host that can rewrite and rehash the whole stream.

Image Cosign verification and finalized-result signing remain separate follow-up
work; this profile does not perform them. Do not infer signer approval from an
image label, digest pin, fixture test, or an `evidence_eligible` field. A future
verifier must get allowed signer identities from trusted policy, and sign results
only after protected collection/finalization. HMAC is not required by this path.

Independent implementation review, native/delegated-session support, production
redaction, and full Loom acceptance remain distinct open requirements. Nothing
in this handoff authorizes a merge.
