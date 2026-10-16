---
type: Requirement
title: Evaluate multiple skill inputs together
description: Requires one combined skill-family evaluation to preserve per-skill, case, and iteration attribution without cross-skill aggregation.
tags: [evaluation, skill-inputs, multi-skill, requirements]
timestamp: 2026-10-16T00:00:00Z
---

# BR-005 — Evaluate multiple skill inputs together

**Priority:** Must

**Verification path:** Observe one public invocation with at least two skill inputs, including distinct inputs for the same skill, selected and all-case execution, multiple iterations, and a duplicate composite case identity. Confirm that unique selected cases/iterations and per-skill comparisons are attributable, no cross-skill aggregate is emitted, and duplicate identities are rejected before any evaluation invocation rather than merged, omitted, or misattributed. Compare all four output formats for the same completed verified run, including full captured answers/evidence; separately confirm existing one-skill and `--profile` behavior is preserved.

**Source:** User-approved multi-skill scale request, including the user's “yes, please” approval to support multiple skill eval inputs and one combined report (Loom task `readable-report-baseline`, Action `bc9c80e4-24c9-4404-bc8c-8539d56237a1`).

**Statement:** A single public `eval` invocation shall be able to evaluate multiple skill-owned evaluation inputs as one combined run and report, while preserving each skill's and case's identity, per-skill comparison meaning, and each case/iteration outcome. The combined result shall not introduce a cross-skill score, ranking, or aggregate verdict. This capability applies only to the skill input family; agent/runtime inputs are not combined into the same run.

**Acceptance criteria:**
- One public invocation can evaluate two or more skill-owned evaluation inputs as one run. Each input's skill identity and each contained case identity remain distinguishable in the resulting run and outputs.
- Repeated skill identity across different inputs is allowed when every contained case has a unique composite identity formed from its skill identity and stable case identity. Before any evaluation invocation begins, the complete submitted child set shall be checked for duplicate composite identities. If two or more submitted occurrences have the same composite identity, the invocation is rejected; it shall not merge, omit, overwrite, or attribute their outcomes as if they were one child. This rule also rejects submitting the same case-bearing input more than once when that repeats its composite identities.
- When all cases are selected, or a subset is selected, every selected case and every requested iteration has an individually attributable outcome. No invalid or conflicting input/child is silently omitted: validation failure prevents evaluation work from starting and is reported as a failed invocation.
- For each skill, its baseline result, candidate result, and comparison remain attributable to that skill and its case/iteration; no cross-skill score, ranking, rate, verdict, or other aggregate claim is presented.
- The combined human-readable report presents a run-level summary and the skill/case/iteration outcomes beneath it, and retains the complete captured target/judge answers and supporting captured evidence/details required by the existing output contract. It does not present an incomplete child set as a complete combined run.
- JSON, YAML, Markdown, and HTML outputs describe the same completed verified combined run and preserve the existing meanings of evaluation results and one-skill runs. Any added multi-skill provenance does not reinterpret existing fields or results.
- Existing one-skill evaluation behavior and legacy `--profile` behavior remain unchanged.

**Verification semantics:** The verification path above is the required observable evidence. Include two different inputs declaring the same skill but disjoint case identities and observe acceptance with distinct case attribution; then submit a duplicate `(skill identity, stable case identity)` in two inputs and observe rejection before any target or judge invocation. Repeat an input containing cases and confirm the same rejection. Output parity and preservation of verified-result meanings are subject to [OC-002](oc-002-evaluation-output-conformance.md); report readability and complete captured-detail visibility are subject to [BR-004](br-004-present-readable-markdown-and-html-results.md) and [QS-001](qs-001-readable-multi-skill-five-iteration-reports.md).

## Derived from
- User-approved multi-skill scale request: one combined skill-family run/report; distinguish skill, case, and iteration; retain per-skill comparison; no mixed agent/runtime family or cross-skill scoring; invalid child inputs must not disappear; preserve one-skill and profile behavior.
- User-approved readable-report baseline: summary-first presentation with complete captured answers/evidence available in the report.
- Specification choice within the authorized combined-run scope: composite identity is `(skill identity, stable case identity)` across the whole submitted run; collisions are rejected before invocation, while repeated skill identity with non-colliding cases remains allowed. This avoids silently coalescing distinct submitted child occurrences without imposing a one-document-per-skill rule.
