---
type: Log
title: Evaluation format ownership architecture change log
description: Changes to the evaluation format ownership architecture bundle.
tags: [architecture, evaluation, log]
timestamp: 2026-10-30T00:00:00Z
---

## 2026-10-30

- Updated [ARS-001](specifications/ars-001-runner-eval-contract.md) and the [index](index.md) to link the authorized [catalog compatibility decision](../opencode-catalog/decisions/adr-001-pin-catalog-through-supported-file-interface.md); distinguished target realization from current implementation and preserved model/reasoning/failure contracts.

- Reconciled current catalog implementation/revalidation status in [ARS-001](specifications/ars-001-runner-eval-contract.md), the [index](index.md), and [runner contracts](../../eval-engine-runner-contracts.md); CI direct-image probes now mount the read-only catalog fixture, and CI explicitly runs catalog pytest coverage.

## 2026-10-16

- **Update**: [ARS-001 — Runner evaluation input, result, and output contract](/specifications/ars-001-runner-eval-contract.md) — Bound each v2 case to its exact source-input occurrence, not a unique skill-name lookup; defined injective comma-safe combined case IDs and selectors while preserving readable source fields and one-input selector compatibility.

- **Update**: [ARD-001 — Runner-owned input and output contracts](/design/ard-001-runner-owned-input-and-output-contracts.md) — Added exact per-input provenance and collision-free composite-identity constraints and verification for delimiter-containing valid input strings.

- **Update**: [Architecture index](/index.md) — Annotated the specification's occurrence attribution and injective selector guarantees.

- **Update**: [ARS-001 — Runner evaluation input, result, and output contract](/specifications/ars-001-runner-eval-contract.md) — Resolved combined top-level-array identity with one explicit ordinally paired `--skill` binding per `--input`; retained raw-array acceptance without filesystem inference, required wrapper/binding agreement, and removed the dependent user question.

- **Update**: [ARD-001 — Runner-owned input and output contracts](/design/ard-001-runner-owned-input-and-output-contracts.md) — Selected explicit per-input CLI identity binding as the minimum-sufficient realization for combined raw arrays; no directory discovery or user-owned behavior decision remains.

- **Update**: [ARS-001 — Runner evaluation input, result, and output contract](/specifications/ars-001-runner-eval-contract.md) — Specified repeated explicit skill inputs, common workspace resolution, complete submitted-child validation, composite duplicate rejection, selection/iteration ordering, per-input provenance, v2 combined output and grouped complete Markdown/HTML presentation; preserved single-input v1 and `--profile`.

- **Update**: [ARD-001 — Runner-owned input and output contracts](/design/ard-001-runner-owned-input-and-output-contracts.md) — Reconciled multi-skill inputs and readable reports with accepted BR-005/OC-001/OC-002/QS-001; selected explicit paths, one workspace, preflight identity invariants and versioned projection without discovery or cross-skill aggregation.

- **Update**: [Architecture index](/index.md) — Linked the combined-skill requirement and governing input/output contracts.

- **Update**: [ARS-001 — Runner evaluation input, result, and output contract](/specifications/ars-001-runner-eval-contract.md) — Replaced the unsupported machine-specific image pin with a required caller-selected immutable local identity, local-only version/adapter compatibility verification, exact identity preservation across target/judge phases, and OCI pull-never; preserved profile-mode image behavior.

- **Update**: [ARD-001 — Runner-owned input and output contracts](/design/ard-001-runner-owned-input-and-output-contracts.md) — Aligned built-in image guarantees and verification evidence with caller-selected immutable local identity and compatibility metadata, with no fallback/pull and unchanged profile-mode behavior.

## 2026-10-15

- **Update**: [ARS-001 — Runner evaluation input, result, and output contract](/specifications/ars-001-runner-eval-contract.md) — Made public-format eligibility require a completed verified evaluation with a family result for every planned job; pre-result errors and not-run jobs remain without fabricated results/classifications and cannot produce a successful conforming-output claim.

- **Update**: [ARD-001 — Runner-owned input and output contracts](/design/ard-001-runner-owned-input-and-output-contracts.md) — Aligned output eligibility, host responsibilities, failure behavior, and composition evidence with ARS-001's per-job family-result precondition.

- **Update**: [ARS-001 — Runner evaluation input, result, and output contract](/specifications/ars-001-runner-eval-contract.md) — Reconciled built-in target/judge execution to OpenCode-only, rejected non-OpenCode transport selection before invocation, retained OpenCode provider/model configuration and profile-mode transport flexibility, and removed Copilot-specific image, judge, and inline skill-methodology claims.

- **Update**: [ARD-001 — Runner-owned input and output contracts](/design/ard-001-runner-owned-input-and-output-contracts.md) — Aligned the built-in architecture and proof obligations to OpenCode-only target/judge execution while preserving existing profile transport behavior and family-specific skill-ablation semantics.

- **Update**: [ARS-001 — Runner evaluation input, result, and output contract](/specifications/ars-001-runner-eval-contract.md) — Removed unsupported claims about unreachable internal threshold behavior; made the optional public field's absence, accepted range, and pre-invocation rejection explicit.

- **Update**: [ARD-001 — Runner-owned input and output contracts](/design/ard-001-runner-owned-input-and-output-contracts.md) — Clarified the public threshold boundary while retaining pinned URL intersection and literal-forbids semantics.

- **Update**: [ARS-001 — Runner evaluation input, result, and output contract](/specifications/ars-001-runner-eval-contract.md) — Corrected source URL assertions to pinned unique exact-match prompt/answer intersection semantics and clarified malformed threshold handling and literal `output.forbids` behavior.

- **Update**: [ARD-001 — Runner-owned input and output contracts](/design/ard-001-runner-owned-input-and-output-contracts.md) — Recorded the corrected URL assertion boundary as runner-owned agent/runtime semantics.

- **Update**: [ARS-001 — Runner evaluation input, result, and output contract](/specifications/ars-001-runner-eval-contract.md) — Restored zero default retries and specified deterministic judge gating plus exact generic classification precedence, including mixed fail/non-evidence outcomes.

- **Update**: [ARD-001 — Runner-owned input and output contracts](/design/ard-001-runner-owned-input-and-output-contracts.md) — Recorded zero-retry default, family-specific judge gates and the stale inventory statement for later reconciliation.

- **Update**: [ARS-001 — Runner evaluation input, result, and output contract](/specifications/ars-001-runner-eval-contract.md) — Specified pinned phase invocation settings/defaults, agent/runtime prompt/workspace/judge behavior, and runner-owned paired skill-ablation construction, evidence gates and comparison semantics.

- **Update**: [ARD-001 — Runner-owned input and output contracts](/design/ard-001-runner-owned-input-and-output-contracts.md) — Assigned invocation resolution and the detailed family lifecycle to runner-owned adapters while retaining the shared single-invocation executor.

- **Update**: [ARS-001 — Runner evaluation input, result, and output contract](/specifications/ars-001-runner-eval-contract.md) — Added pinned tool-only action assertion matching, evidence-uncertainty behavior, and corrected `args` to subset matching while retaining selected-argument comparator semantics.

- **Update**: [ARD-001 — Runner-owned input and output contracts](/design/ard-001-runner-owned-input-and-output-contracts.md) — Recorded the corrected runtime action assertion semantics at the family-adapter boundary.

- **Update**: [ARS-001 — Runner evaluation input, result, and output contract](/specifications/ars-001-runner-eval-contract.md) — Closed the accepted v1 suite and skill wrapper/field allowlists from Task 1.1, defined typed output and summary semantics, and required additive preservation of existing `--profile` behavior.

- **Update**: [ARD-001 — Runner-owned input and output contracts](/design/ard-001-runner-owned-input-and-output-contracts.md) — Reconciled profile-mode coexistence and bounded remaining v1-consumer and historical-input compatibility questions.

- **Creation**: [ARS-001 — Runner evaluation input, result, and output contract](/specifications/ars-001-runner-eval-contract.md) — Defined the built-in input modes, stable family/case identity, verified result projection, four format contracts and explicit compatibility boundaries.

- **Update**: [ARD-001 — Runner-owned input and output contracts](/design/ard-001-runner-owned-input-and-output-contracts.md) — Reconciled the architecture with ARS-001's selected interface and v1-preserving projection realization.

- **Creation**: [ARD-001 — Runner-owned input and output contracts](/design/ard-001-runner-owned-input-and-output-contracts.md) — Added it to reconcile runner-owned input families and multi-format outputs with the current eval engine.

- **Update**: [ARD-001 — Runner-owned input and output contracts](/design/ard-001-runner-owned-input-and-output-contracts.md) — Added minimum accessibility constraints for Markdown and HTML result views; left the precise conformance target and report semantics open for downstream design/specification and user authority respectively.
