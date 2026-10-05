# Gate 1 independent review request

**Current gate verdict: NOT RUN**

The Wave-1 planning artifacts are ready for independent review. This document does not self-approve the candidate.

## Candidate under review

Runner-only experiment using:

- immutable stock OpenCode v2.0.23;
- runner-owned trusted bridge plugin loaded through the supported OpenCode plugin API;
- isolated Loom plugin execution domain;
- host-side trusted collector/evidence safety;
- bounded typed capability protocol.

No OpenCode patch/fork/upstream PR is allowed.

## Required reviewer inputs

- [STOCK-OPENCODE-2.0.23.md](STOCK-OPENCODE-2.0.23.md)
- [TCB.md](TCB.md)
- [AUTHORITY-MANIFEST.md](AUTHORITY-MANIFEST.md)
- [CAPABILITY-MANIFEST.md](CAPABILITY-MANIFEST.md)
- [CALLBACK-LIFECYCLE.md](CALLBACK-LIFECYCLE.md)
- [SCOPE-COMPLETENESS.md](SCOPE-COMPLETENESS.md)
- [EVIDENCE-SINKS.md](EVIDENCE-SINKS.md)
- [PLANNING-EVIDENCE-PROVENANCE.md](PLANNING-EVIDENCE-PROVENANCE.md)

## Load-bearing review questions

### Effective authority

1. Does the proposed channel/mount/process model prevent isolated Loom and stock shell subprocesses from manufacturing eligible evidence?
2. Can either evaluated domain duplicate/inherit/impersonate the bridge/collector connection?
3. Are evidence storage and runner control endpoints absent from evaluated authority?
4. Does suppression/crash remain incomplete rather than false-complete?

### Plugin loading

5. Can evaluated workspace/config mutation cause stock OpenCode to import another untrusted in-process plugin?
6. Is the proposed preflight + read-only discovery-path fencing sufficient for the bounded profile without changing required Loom semantics?

### Broker authority

7. Is every remote capability tied to a concrete pinned Loom use?
8. Can any operation become arbitrary code execution or generic OpenCode dispatch in trusted core?
9. Are identity, parentage, sequence, scope, terminal, and completeness exclusively trusted-side facts?

### Fidelity

10. Is the synchronous `agent.transform` strategy sufficiently bounded for the experiment?
11. Can tool transform/function identity be represented without moving Loom code into trusted core?
12. Are hook mutation order, cancellation, late responses, and at-most-once behavior specified sufficiently for a prototype?
13. Does the design preserve Loom product logic outside the trusted adapter?

### Observation

14. Are stock live Session events sufficient for the claimed native terminal evidence?
15. Is Code Mode inner finality correctly left `UNPROVEN` rather than assumed?
16. Does concurrency use trusted unique correlation or explicit ambiguity rejection?

### Confidentiality

17. Are all proposed first sinks enumerated?
18. Does any proposed path persist/clip raw credential-bearing evidence before safety projection?

## Known unresolved experimental questions

These do not automatically prevent Gate 1 PASS for a bounded feasibility prototype, but they MUST remain explicit:

- Code Mode per-inner final caller result/error: `UNPROVEN`;
- effective channel resistance to stock shell subprocess authority: `UNPROVEN`;
- remote function identity for Loom attestation: `UNPROVEN`;
- dynamic agent-transform reload parity: outside initial bounded claim unless independently solved;
- trusted root Session admission for scope: `UNPROVEN` until provider-free candidate preflight;
- stock public-event ordering/correlation under concurrency: `UNPROVEN` until provider-free candidate preflight.

## Gate 1 verdict vocabulary

- `PASS` — sufficiently specified and bounded to consider Authorization A.
- `FAIL` — candidate design already violates a requirement or cannot preserve required semantics.
- `UNPROVEN` — review cannot establish enough to authorize the next stage.
- `NOT RUN` — independent review has not occurred.

A Gate 1 PASS does **not** establish TRUST-001 feasibility and does not authorize candidate execution. It only permits the owner to consider the separate Authorization A for construction/named provider-free preflights.

## Current planner assessment

**READY FOR INDEPENDENT REVIEW; GATE 1 NOT RUN.**

No implementation, candidate OCI execution, model inference, credential use, merge, or default-pin change has been performed by this planning branch.
