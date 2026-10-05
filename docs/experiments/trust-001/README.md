# TRUST-001 stock-OpenCode experiment planning

Status: **planning only**. No prototype construction, candidate execution, inference, merge, default-pin change, or OpenCode modification is authorized by this directory.

## Program goal

The delivery goal remains full `opencode-eval-runner` compliance with Loom's consumer contract. This work addresses the producer-trust gap only and does not turn TRUST-001 feasibility into full consumer-contract acceptance.

## Hard scope constraints

- OpenCode is an immutable external dependency.
- Target stock OpenCode version for planning: **v2.0.23** (`0fd7e2829449b052abf0078666669302923d77af`).
- No OpenCode source patch, fork, custom binary, or upstream PR is part of this work.
- All candidate implementation, if later authorized, belongs to `opencode-eval-runner`.
- Loom production semantics remain unchanged. Loom changes only as required by its consumer contract.
- PR #41 patched-runtime work is research/reference evidence only, not an allowed runtime dependency.

## Pinned planning inputs

- Loom consumer/product checkpoint: `149406dfa0a01f94491d17054e50a1bc84bb97be`
- Runner research checkpoint: `002aba96441da8c69c5ce19ac77de298cfeb28d2`
- Stock OpenCode: `v2.0.23` / `0fd7e2829449b052abf0078666669302923d77af`
- Historical safety image reported by Loom: `ghcr.io/bateau84/opencode-eval-runner@sha256:8d7c90223f43bb3c9954918caf1e0a578745c5db2f18dd8f5b69f00a0c6d4723`
- Historical normal-observation image: `ghcr.io/bateau84/opencode-eval-runner@sha256:df50c03b1efc5d42eb94cf7ffcb7d4ee5c51b7c4970fa20585b8048713ed05d9`

The two images above demonstrate different historical profiles. Neither is a permitted dependency for a stock-OpenCode candidate without renewed checkpoint proof.

## Wave-1 outputs

- [PLANNING-EVIDENCE-PROVENANCE.md](PLANNING-EVIDENCE-PROVENANCE.md)
- [STOCK-OPENCODE-2.0.23.md](STOCK-OPENCODE-2.0.23.md)
- [TCB.md](TCB.md)
- [AUTHORITY-MANIFEST.md](AUTHORITY-MANIFEST.md)
- [CAPABILITY-MANIFEST.md](CAPABILITY-MANIFEST.md)
- [CALLBACK-LIFECYCLE.md](CALLBACK-LIFECYCLE.md)
- [SCOPE-COMPLETENESS.md](SCOPE-COMPLETENESS.md)
- [EVIDENCE-SINKS.md](EVIDENCE-SINKS.md)
- [GATE-1-REVIEW.md](GATE-1-REVIEW.md)

Gate 1 remains `NOT RUN` until an independent reviewer evaluates the completed manifests.
