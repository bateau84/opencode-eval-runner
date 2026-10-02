# Local OpenCode observation patch

This is a downstream patch maintained **in this runner repository**, not an
upstream OpenCode PR and not another Code Mode interpreter. The normal image and
host installation remain unchanged. The experimental image builds the existing
OpenCode CLI from `cd9a14a6b688d4021bee381dfd39d2cef9c0f862` (v2.0.18), with
`apply.py` checking every changed source blob before applying exact substitutions.

## Runtime seam

Set `OPENCODE_EVAL_OBSERVATIONS=1` in the experimental image. A Loom producer can
subscribe with `ctx.tool.hook("execute.observed", callback)`. This local API emits
`opencode-local-observation/v1` events; it is **not** PR #41's HMAC wire protocol or
an agreed replacement for Loom's draft contract.

The patch carries a new child invocation ID through the existing Code Mode tool
bridge. It records actual decoded executable inputs after before-hooks, actual
registration/catalog identities, and actor/session/message/enclosing-call values
from the runtime context. Existing product call IDs are not replaced. Start and
terminal events share the generated identity, not a FIFO/input-equality guess.

Returns are observed after existing output-changing hooks, content conversion,
output validation, and the Code Mode JSON round trip. Failures and interruption
use the interpreter's existing terminal path, including caught throws. The error
representation is explicitly `codemode-catch-name-message/v1`: a shared helper also
constructs the name/message of the Error seen by the interpreter's catch handler.
It is not a claim to serialize host exception identity, stack, or arbitrary causes.

Snapshots own their data and reject unsupported values without invoking getters
or `toJSON`. They are **unredacted in-memory events**. Loom still owns safe producer
redaction before persistence and its actual assertion consumer. There is no raw
trace writer, collector, signer, or positive evidence admission in this patch.
Observer callback failures are counted and suppressed; they must not replace the
tool outcome. A callback that never completes remains an unproved noninterference
case and is not covered by the exception-failure test.

`parent_start` / `parent_end` bracket one Code Mode engine invocation. They do not
pretend to capture the final native outer-tool result or prove run-wide capture
closure. Missing terminals, unsupported dispatches, unavailable fields, and
observer failures remain explicit. The parent-end record sets
`evidence_eligible: false`: a plugin hook alone is not a protected evidence channel.

## Build and test

The `Local runtime observation patch` workflow applies the pinned patch, runs
source tests against the real core/interpreter, builds the CLI, and publishes a
commit-and-run-scoped experimental image. It records the immutable registry digest
in `image.txt`, then probes that exact published image using a deterministic
container-local provider with `--network none` and disposable state.

The image probe adds a diagnostic subscriber and an input-changing fixture hook
to a temporary copy of the existing runner fixture. The original fixture and its
historical artifacts are not overwritten. It covers identical overlapping calls,
reverse completion, actual actor/input bindings, final modified returns, caught
throws, observer exceptions, and a target-written forged sidecar. The forged file
is tested against PR #41's importer; the diagnostic subscriber is not admitted as
a legitimate producer and is not a proof of protected producer feasibility.

This is **not Loom's preserved smoke**. The supplied contract identifies its
producer/smoke/consumer files as uncommitted and does not contain their bytes.
Those exact files must be available and adapted to the agreed local seam before
claiming a preserved Loom producer-to-consumer run. Independent code review,
native-final-result capture, run-wide completeness, and protected export remain
separate requirements. No merge or full-handoff acceptance follows from these tests.
