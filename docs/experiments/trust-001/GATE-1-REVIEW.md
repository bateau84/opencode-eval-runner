# Gate 1 independent architecture review

**Current gate verdict: PASS**

The complete Wave-1 planning package was independently reviewed as one architecture package before any correction was made. Source checks were performed against pinned Loom `149406d` and stock OpenCode v2.0.23.

The review found correctable planning gaps in legacy-storage lifetime, capability/evidence channel separation, plugin-source closure, cancellation semantics, first-sink wording, and completeness sealing. Those corrections were traced across the affected artifacts and then the full package was reread.

This PASS is a **design-readiness verdict only**. It does not authorize construction or execution.

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
2. Can either evaluated domain duplicate/inherit/impersonate the evidence connection?
3. Is the capability channel distinct from the evidence channel so capability compromise cannot manufacture eligible evidence?
4. Are evidence storage and runner control endpoints absent from evaluated authority?
5. Does suppression/crash remain incomplete rather than false-complete?

### Plugin loading

6. Can evaluated workspace/config mutation cause stock OpenCode to import another untrusted in-process plugin?
7. Does the plugin-source closure manifest include every config document/root, discovery directory, configured source, and watched input that can change the effective add/remove operation set?
8. Is that complete source closure immutable to evaluated authority for the generation without changing required Loom semantics?

### Broker authority

9. Is every remote capability tied to a concrete pinned Loom use, including runtime lazy legacy-storage compatibility rather than a false setup-only assumption?
10. Can any operation become arbitrary code execution or generic OpenCode dispatch in trusted core?
11. Are identity, parentage, sequence, scope, terminal, and completeness exclusively trusted-side facts?

### Fidelity

12. Is the synchronous `agent.transform` strategy sufficiently bounded for the experiment?
13. Can tool transform/function identity be represented without moving Loom code into trusted core?
14. Are hook mutation order, cancellation, late responses, remote side effects, and at-most-once behavior specified sufficiently for a prototype?
15. Does the design preserve Loom product logic outside the trusted adapter?

### Observation

16. Are stock live Session events sufficient for the claimed native terminal evidence?
17. Is public `ctx.event.subscribe()` only claimed as a source-supported access surface, with ordering/drain left for provider-free proof?
18. Is Code Mode inner finality correctly left `UNPROVEN` rather than assumed?
19. Does concurrency use trusted unique correlation or explicit ambiguity rejection?
20. Does completeness require a trusted admission close, contiguous final collector sequence, and generation seal rather than quiescence alone?

### Confidentiality

21. Are all proposed candidate-controlled first sinks enumerated, including diagnostics/logging/export paths?
22. Does any proposed candidate-controlled path persist/clip raw credential-bearing observation data before safety projection?
23. Are ordinary stock/Loom product stores kept distinct from runner evidence claims unless candidate code copies/exports them?

## Known unresolved experimental questions

These do not automatically prevent Gate 1 PASS for a bounded feasibility prototype, but they MUST remain explicit:

- Code Mode per-inner final caller result/error: `UNPROVEN`;
- effective channel resistance to stock shell subprocess authority: `UNPROVEN`;
- remote function identity for Loom attestation: `UNPROVEN`;
- dynamic agent-transform reload parity: outside initial bounded claim unless independently solved;
- trusted root Session admission for scope: `UNPROVEN` until provider-free candidate preflight;
- stock public-event ordering/correlation and seal/drain behavior under concurrency: `UNPROVEN` until provider-free candidate preflight;
- remote cancellation side-effect fidelity: `UNPROVEN` until provider-free candidate preflight.

## Gate 1 verdict vocabulary

- `PASS` — sufficiently specified and bounded to consider Authorization A.
- `FAIL` — candidate design already violates a requirement or cannot preserve required semantics.
- `UNPROVEN` — review cannot establish enough to authorize the next stage.
- `NOT RUN` — independent review has not occurred.

A Gate 1 PASS does **not** establish TRUST-001 feasibility and does not authorize candidate execution. It only permits the owner to consider the separate Authorization A for construction/named provider-free preflights.

## Independent Gate 1 assessment

**GATE 1: PASS.**

The corrected planning package is sufficiently coherent, bounded, source-grounded, and falsifiable for the owner to consider a **separate Authorization A** for prototype construction and explicitly named provider-free preflights.

This PASS does not establish TRUST-001 feasibility. No implementation, candidate OCI execution, model inference, provider credential use, merge, default-pin change, Loom modification, or OpenCode modification was performed by this Gate-1 review.
