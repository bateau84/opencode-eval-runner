---
type: Requirement
title: Accept both input contract families without collapsing semantics
description: Defines the runner's obligation to accept both evaluation input families while preserving their distinct meanings.
tags: [evaluation, input-contracts, requirements]
timestamp: 2026-10-16T00:00:00Z
---

# BR-001 — Accept both input contract families without collapsing semantics

**Priority:** Must (authorized scope)

**Source:** User-authorized goal; [evaluation format ownership handoff](../../eval-format-ownership-handoff.md), “Existing Loom input formats” and “Intended future direction.”

**Statement:** The runner shall accept and validate cases conforming to each of its two owned input contracts—the existing agent/runtime suite family and skill-owned case family—and evaluate them without treating one family's semantics as interchangeable with the other's.

**Acceptance criteria:**
- The runner is the authoritative owner of a conformance contract for each family, validates the input against the appropriate contract, and does not execute an invalid input as though it were valid.
- The owned contracts do not make the two families interchangeable: an agent/runtime suite retains its execution-mode and runtime/action/tool-result assertion meaning, while skill cases retain their skill-oriented prompt/expectation meaning and, when used for ablation, their baseline/candidate comparison context.
- A case expressed under one family's semantics is not silently reinterpreted as satisfying the other family's assertions or evaluation meaning.
- This requirement does not guarantee compatibility with historical variants beyond the existing input formats or prescribe undocumented legacy aliases/conversions.

The examples in the second criterion describe the families' distinction. Which optional source features are part of the accepted current contract, and the exact fields/encoding/version, are contract-definition details; the runner's two contracts must state their boundaries.

**Verification path:** Submit valid representative inputs from each family and observe that each reaches evaluation under its own meaning; submit malformed/nonconforming examples and observe they are not run as valid cases. Inspect both owned contracts for explicit conformance boundaries. Falsify if either family is not accepted or is interpreted as the other's semantics.

## Derived from
- User-authorized goal for this work.
- [Evaluation format ownership handoff](../../eval-format-ownership-handoff.md).
