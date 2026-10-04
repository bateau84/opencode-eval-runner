# Runner pre-output evidence safety (RSP v1)

## Scope and compatibility

This adapter realizes the runner-owned portion of RSP-001–004 under the unchanged
`bun run eval:live -> scripts/run-evals.py -> runner invoke` entrypoint. It does
not change tool implementations, permissions, sessions, runtime call ordering,
OpenCode's binary, or default image pins. It is explicitly opt-in at the host and
ships in a separate immutable image variant.

The ordinary `invoke` result remains unchanged without these options. A safety
invocation uses a **new** result schema, never silently reinterprets older v1
results, and must be consumed by a compatible Loom adapter.

References: Loom's accepted `eval-evidence-safety-projection.md` at
`1a85b1a9e6707f720b95bd81b1e245ffa73202bf`; branch
`functionality-anchor-requirements-coherance` resolved to
`0756f7519fc7791bc31e2ef2aa41ec53168782a9` during implementation. At these fetched
commits `CredentialInventory.private_policy()` is in `scripts/run-evals.py`.
The named `scripts/eval_evidence_safety.py` is not present in the published tree.
No claim is made to have loaded that missing helper or the user's local checkout.

## Private policy and request

Loom owns source/path/role classification. The runner consumes the exact existing
`private_policy()` delivery shape:

```json
{
  "schema": "loom-eval-credential-inventory/v1",
  "policy_version": "source-path-roles/v1",
  "complete": true,
  "sources": {
    "env": "complete",
    "auth": "not_selected",
    "config": "not_selected",
    "models": "not_selected",
    "credential_seed": "not_selected",
    "config_root": "not_selected"
  },
  "values": ["synthetic-credential"]
}
```

Exactly these source categories and `complete`, `incomplete`, `not_selected`
states are supported. Missing/unknown versions, malformed/duplicate JSON keys,
non-UTF-8 bytes, unknown source categories, size overflow, or invalid source states
cannot produce a complete policy. The private policy limit remains **128,000
UTF-8 bytes**; values are bounded to 4,096 distinct-entry candidates. An incomplete
inventory never falls back to using a partial matcher.

The host snapshots these bytes in memory. It audits the normal command's selected
seed categories against the declaration. Runner-resolved default/env-only seed
selection without an explicit corresponding argument downgrades the inventory:
v1 cannot bind a category name to an independently resolved path. Config-root
credential discovery remains unsupported and downgrades retention; it does not
remove the configuration from execution. Loom must classify the same selected
input snapshots it passes, including workspace configuration when credential
bearing. A complete inventory is a trusted input declaration, not new discovery
or a proof that a tool cannot generate other secrets.

The host sends `opencode-eval-runner/evidence-safety-request/v1` on **private
supervisor stdin**, not in argv, a mounted policy file, or the child environment.
It contains `run_id` (fresh 64-hex nonce), `policy` (the shape above or null), and
`binding_key` (private per-invocation 32-byte random value encoded as hex).
Supervisor stdin is consumed before execution. Product subprocess stdin is
`DEVNULL`, so the policy is not inherited as tool/model input. Authorized ordinary
credential seeds are separate execution inputs, not evidence copies.

## Acknowledgement and host admission

The supervisor returns `evidence_safety_ack`:

```text
schema = opencode-eval-runner/evidence-safety-ack/v1
consumer = runner-evidence-safety/v1
run_id = the expected host nonce
policy_schema = loom-eval-credential-inventory/v1
policy_version = source-path-roles/v1
projection_schema = loom-eval-evidence-safety/v1
stages = [container.before_clip, container.before_output]
policy_valid = boolean
inventory_complete = boolean
module_sha256 = digest of the loaded projection module
image_source_revision = image build's source commit
policy_receipt = per-request keyed receipt over the parsed private policy
```

The host validates all fields, types, dispositions, and loss counts before its
first evidence-file write or print. The private binding key never appears in the
result; the keyed receipt permits checking that the same policy bytes were
consumed without exposing a public low-entropy credential hash. This receipt is
**not an observation signature, a signing service, or protection from a malicious
plugin**. It only binds policy acknowledgement within a reviewed installation.

Before launching product code, the host requires an immutable image reference
and validates the inspected image's adapter version, projection-module hash and
container-entrypoint hash against its checkout. It runs the resolved local image
configuration ID, not a mutable tag. Unsupported images are rejected before they
can run with the new policy; there is no fallback to unprotected legacy execution.
Extra mounts that can replace the interpreter/emitter are unsupported; ordinary
workspace and workspace dependency submounts are retained.

An accepted result includes host-generated `evidence_safety_validation` with
`acknowledged: true` and stages `host.before_write`, `host.before_print`. It also
includes `evidence_load`: immutable image reference, resolved image configuration
ID, image source revision, actual host executable/adapter/module SHA-256 values,
and host checkout revision/clean status when available. These are **code** hashes,
not hashes of policy values or tool payloads. The host never accepts a container's
claim that host verification occurred.

A missing, incompatible, replayed, wrong-policy, or malformed acknowledgement
results only in a fixed omission projection and a nonzero host exit. Raw container
stdout/stderr/exception text is never used as a diagnostic fallback.

## Public projection

Root result schema: `opencode-eval-runner/safe-result/v1`.
Tool-event projection: `opencode-eval-runner/safe-tool-results/v1`, under
`tool_result_evidence`. Native event values come from the actual existing CLI
JSONL stream; no script-source inference or replacement runtime is introduced.
This is not a new producer of Code Mode inner results and does not promote
normal-invoke diagnostic hook records into trustworthy evidence.

`evidence_safety` uses Loom's accepted `loom-eval-evidence-safety/v1` shape:
`policy_version`, `inventory_complete`, `coverage_complete`, `fields`, and the
fixed reason-to-counter `loss_counts` map. Each field entry has `event` (null for
transport fields or a safe zero-based event ordinal), `field`, and `state`.
Non-exact entries also have an accepted fixed `reason` and `stage`.

States are **exact**, **redacted**, and **omitted**. Redacted values are diagnostic
only. Omitted fields have no value slot, preview, original-key list, original-value
hash, prefix, or suffix. Every retained payload/selector has a disposition. Fixed
validated envelope keys, enums, counters and booleans are protocol, not payload.
For example `exit_code: 1` survives a credential equal to `1`; a payload integer
that could disclose that credential is omitted rather than changed to an invalid
JSON token.

Transport fields include `text`, `tools`, `actions`, `skills_loaded`, dynamic model/
agent/session/reasoning identities, and raw-stream omissions. Event fields include
`tool`, actual `call_id` (`callID` or pinned V2 `id`, **not** `partID`), `session_id`,
`input`, `output`, and `error`. Status is validated against the fixed runtime
status vocabulary; `completed` is not interpreted as domain success.

- Structured payloads are copied without mutation. Safe keys stay unchanged;
  credential-bearing keys omit the enclosing field instead of colliding under a
  common replacement key. Numbers, null and strings keep their type when exact.
- String matching protects real short credentials including `0`, `1`, `text`,
  and `low`. There is no word exemption or length floor. Only correctly
  source-classified credentials become match material. Generated mask markers
  are never scanned again.
- Raw and up-to-three-layer JSON-escaped credential forms are supported. A
  declared nested JSON-string adapter may decode and re-encode, retaining the
  original bytes when unchanged. Opaque JSON-looking strings with a match are
  omitted rather than having their syntax rewritten. Unsupported deeper forms,
  cycles, duplicate JSON keys and non-finite values are omitted.
- Identity fields are exact or omitted, never masked into another usable identity.
  Any action selector/input loss omits the whole action list.
- Native output needs the pinned runtime's explicit non-truncation metadata;
  known upstream truncation is `upstream_clipped`, absent/unknown declaration is
  `opaque_payload_unverified`. Host sanitation cannot undo an earlier cut.
- Sanitization occurs **before** runner field-size decisions. An oversized safe
  field is omitted with `size_limit`, never stored as clipped JSON. Limits are
  2,000 encoded UTF-8 bytes for input, 6,000 for tool output/error, and 200,000 for
  assistant text. Up to 64 outer tool events are retained.
- Raw stdout/stderr, plugin preflight detail, and arbitrary metadata are deliberately
  omitted before runner clipping/output. There is no claimed safe adapter for
  their arbitrary encodings. Consequently whole-projection `coverage_complete`
  remains false; per-field exactness does not imply a complete capture.

Reasons match the architecture: `credential_match`, `sensitive_key`,
`inventory_incomplete`, `upstream_clipped`, `unsupported_schema`,
`unsupported_representation`, `opaque_payload_unverified`, `size_limit`, `missing`,
`invalid`, `write_failed`. Container losses use stage `runner`; host admission
failures use `transport`. No raw error/credential/path is inserted into reasons.

## First sinks and failures

Covered runner-owned boundaries are field rendering/size decisions, raw-stream
prefix creation, container result stdout, host result-file creation/replacement,
and `--print-result`. Capture stays in memory until projection. The host writes
an already-validated projection into a mode-0600 temporary file and replaces the
requested result atomically; no raw intermediate result file is created. Docker
logging is disabled for the safety invocation, avoiding a second daemon log copy.

Success, nonzero product exit, caught tool failure, timeout with partial output,
invalid JSON, unknown policy, missing acknowledgement and output write failure
have explicit omission behavior. Product return values and exit status remain
separate from evidence eligibility. Argument-parser errors in this mode use a
fixed diagnostic, not reflected arguments. No tool retry is added.

Not covered or changed: OpenCode's own product Session database/tool-output
storage, arbitrary tool filesystem writes, Loom-owned observer sidecars, general
live-data encoding discovery, Issue 42 plugin isolation, or signing. Those are
not certified by this acknowledgement. A newly discovered runner-owned earlier
sink must be added to this contract before it can be claimed covered.

## Loom integration and invocation

Loom should retain `bun run eval:live ...` and add the following internally to its
normal runner invocation after creating the private inventory file:

```sh
/path/to/runner/bin/opencode-eval-runner invoke \
  --image ghcr.io/bateau84/opencode-eval-runner@sha256:<safety-image-digest> \
  --require-evidence-safety \
  --evidence-policy-file /private/disposable/inventory.json \
  --model <existing-model> --workspace <existing-workspace> \
  --prompt-file <existing-prompt> --output <host-result.json>
```

All existing model/agent/permission/seed options remain normal `invoke` options.
The policy file is consumed by the host and is not mounted for the target. Missing
policy on a compatible image still allows ordinary product execution, but all
matcher-dependent evidence is omitted. Unknown image support fails before launch.

Loom must explicitly recognize the new result/event schemas, validate the
acknowledgement and loaded revisions, and consume dispositions for every scoring
path. Exact fields alone do not authorize PASS; redacted/omitted required fields
and unknown absence coverage remain indeterminate. Do not fall back to old
`observed_tool_results`, raw stdout, or marker absence. No historical artifact is
rewritten or promoted.

## Verification boundary

The new CI workflow builds/publishes a separate safety image from the existing
OpenCode eval.4 digest plus changed runner Python files. Build and verification
have no package/OIDC signing authority; publication is a separate job that does
not execute the workload. The resulting immutable digest must match the tested
source; a repository commit does not change an old image.

Unit tests invoke the actual container result emitter and host writer, with
synthetic inventories. The image probe exercises the public host CLI, real
OpenCode binary and deterministic loopback provider. It compares product outcomes
with safety off, then checks actual file/print output for short and escaped
credentials, pre-clip redaction, size omission, native errors, and policy failures.
The deliberately unsafe baseline uses disposable synthetic data only and is not
published as admitted evidence. These runner tests do not replace Loom's own
composition tests. Both publication and test results must be checked on the
actual PR source before acceptance.


## Disposable OpenCode state profile

For provider-free composition that must exclude installed auth/database state,
use `--opencode-state-profile disposable`. The complete lifecycle and policy
source-state contract are defined in
[`disposable-opencode-state.md`](disposable-opencode-state.md).

The disposable profile is opt-in. It does not change ordinary `invoke` defaults.
In RSP mode its `opencode-eval-runner/runtime-state/v1` attestation is carried as
an exact protocol field and must be understood by the Loom consumer before that
composition can be admitted.
