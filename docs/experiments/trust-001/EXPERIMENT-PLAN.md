# TRUST-001 bounded experiment plan — stock OpenCode revision

Status: **planning only**.

## Goal

Test whether `opencode-eval-runner` can satisfy the TRUST-001 producer boundary for the selected Loom surface while:

- using stock OpenCode v2.0.23 unchanged;
- preserving normal Loom semantics;
- changing only runner-owned implementation;
- keeping TRUST feasibility separate from full Loom consumer-contract delivery.

## Authorization boundaries

### Currently allowed

- source/history inspection;
- existing artifact inspection;
- planning documents/manifests;
- pure/provider-free tests of already-existing planning/test surfaces.

### Not authorized by this plan

- candidate implementation;
- candidate OCI execution;
- model-backed `eval:live`;
- provider credential use;
- merges/default-pin changes;
- OpenCode source/binary changes.

## Wave 0 — checkpoint/provenance

Planning source checkpoint:

- Loom `149406dfa0a01f94491d17054e50a1bc84bb97be`;
- runner research `002aba96441da8c69c5ce19ac77de298cfeb28d2`;
- stock OpenCode v2.0.23 `0fd7e2829449b052abf0078666669302923d77af`.

Historical PR #41 images remain reported/reference profiles only.

Baseline rerun is execution and requires explicit authorization; model-backed rerun additionally requires inference authorization.

## Wave 1 — candidate definition

Completed planning outputs in this directory:

1. TCB;
2. effective-authority manifest;
3. bounded capability manifest;
4. callback/request lifecycle;
5. scope/completeness contract;
6. provisional first-sink inventory;
7. stock OpenCode 2.0.23 assessment;
8. evidence provenance ledger.

### Gate 1

Independent review only.

Verdicts:

- PASS;
- FAIL;
- UNPROVEN;
- NOT RUN.

Current state: **PASS**.

## Authorization A — construction

Only after Gate 1 PASS.

Must identify:

- exact candidate source branch/checkpoint;
- stock OpenCode image/version;
- exact TCB;
- reviewed capability surface, including generation-lifetime legacy storage bounds;
- plugin-source closure manifest: effective add/remove operation set plus every config/source input that can change it;
- distinct evidence-channel and capability-channel endpoints, peer admission, descriptor policy, and no-reconnect rule;
- generation close/seal and contiguous collector-sequence protocol;
- mount/process/network policy;
- candidate-controlled diagnostic/first-sink policy;
- candidate files allowed to change;
- named provider-free local preflights;
- reviewers.

Authorization A does not authorize model inference.

## Wave 2 — candidate construction

If authorized:

1. runner-owned bridge plugin using stock API only;
2. isolated Loom plugin runtime;
3. reviewed declarative transform/proxy machinery;
4. at-most-once request correlation;
5. trusted live event collector;
6. trusted scope accounting;
7. evidence safety before first candidate-controlled sink;
8. immutable plugin-source closure fences;
9. generation admission close + trusted final-sequence seal/drain;
10. distinct capability and evidence channels;
11. no OpenCode patch.

### Gate 2

Independent source/authority review.

### Gate 2C

Provider-free confidentiality/transport preflight.

Must prove at least:

- no raw secret at any candidate-controlled first sink, including diagnostics/logging;
- no evidence-channel FD/listener inheritance, duplication, or impersonation by evaluated subprocesses;
- an unadmitted process cannot impersonate the capability peer; replay/identity/integrity loss makes affected evidence ineligible;
- no plugin-source operation-set change or loading escape;
- duplicate/replay/stale/late response rejection;
- generation close/seal, contiguous final sequence, and post-seal late request/event rejection;
- cancellation/late-response behavior does not overclaim remote side-effect rollback;
- capability/evidence channel loss before/after product completion;
- no automatic product retry.

FAIL rejects the exact checkpoint.

UNPROVEN/NOT RUN blocks Authorization B.

## Authorization B — candidate execution

Separate from construction.

Names exact candidate checkpoint and scenarios.

Does not imply model/provider inference authorization.

## Wave 3 — semantic scenarios

Report independently:

- baseline parity;
- Loom conformance;
- evidence integrity.

Allowed verdicts: PASS / FAIL / UNPROVEN / NOT RUN.

Scenarios:

- SCN-00 callback/transform fidelity;
- SCN-01 native Loom tool;
- SCN-02 Code Mode return/transform/discard/caught throw;
- SCN-03 permission denial + trusted state query;
- SCN-04 foreground delegation;
- SCN-05 background delegation;
- SCN-06 OQ continuation/reconciliation;
- SCN-07 identical concurrent calls with reverse completion under same and different parents.

## Wave 4 — adversarial authority

Provider-free where possible.

Test:

- collector-shaped product data;
- evidence-path modification;
- shared-workspace path aliases;
- plugin load/reload escape;
- process/proc/ptrace/fd attacks;
- container-engine/control access;
- broker/network bypass;
- malformed/code-bearing protocol payload;
- Loom/shell child attacker;
- duplicate/replay/stale/late responses;
- evidence deletion/reordering;
- fake terminal/completeness;
- crash/hang/channel loss;
- cancellation + late response and remote side-effect timing;
- post-seal late request/event and sequence-gap attempts.

## Wave 5 — confidentiality

Reconcile every actual first persistence/clipping path.

For each test literal, short, escaped, deep-key, sensitive-key, boundary-spanning and failure-path synthetic credentials.

Report confidentiality, integrity and eligibility separately.

## Wave 6 — runner→Loom composition

Use only normal consumer path.

Runner fixture success is supporting evidence, not composition proof.

Verify state-dependent assertions, descendants/background scope, concurrency and non-evidence vetoes.

Any real model run requires explicit inference authorization.

## Wave 7 — independent adjudication

Final dimensions:

- baseline parity;
- Loom conformance;
- TRUST-001 tested feasibility;
- confidentiality;
- scoped completeness.

Success means feasibility only for the tested checkpoint/surface.

## Rejection/recovery

On a rejection criterion:

1. stop exact candidate checkpoint;
2. preserve evidence;
3. mark checkpoint REJECTED;
4. record reproducer/reason;
5. corrections create a new checkpoint;
6. rerun rejecting and affected reviews;
7. authority/scope/sink/protocol changes return to earlier gates.

No silent continuation under a rejected checkpoint.

## Remaining program after TRUST

Even a successful experiment leaves the rest of the Loom contract delivery plan, including any remaining CAP-005/006/007, EVAL-001/002/003, ART-001, and full assembled acceptance gaps.
