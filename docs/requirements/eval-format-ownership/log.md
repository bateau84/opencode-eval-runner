---
type: Log
title: Evaluation format ownership requirements change log
description: Changes to the evaluation format ownership requirements bundle.
tags: [evaluation, requirements, log]
---

## 2026-10-29

- **Update**: [Requirements bundle index](/docs/requirements/eval-format-ownership/index.md) — Reconciled the superseded single-input architecture conflict with the repeated explicit skill-input realization in ARD-001/ARS-001, and recorded user acceptance of the historical GHCR transfer as a non-blocking exception without making a no-egress claim.

## 2026-10-16

- **Update**: [BR-005 — Evaluate multiple skill inputs together](/docs/requirements/eval-format-ownership/br-005-evaluate-multiple-skill-inputs-together.md) and [OC-001 — Evaluation case input conformance](/docs/requirements/eval-format-ownership/oc-001-evaluation-case-input-conformance.md) — Defined full-run uniqueness by composite skill/case identity: repeated skill identity across distinct inputs remains allowed for disjoint cases; duplicate composite identities reject before invocation rather than being merged, omitted, or misattributed.
- **Update**: [Requirements bundle index](/docs/requirements/eval-format-ownership/index.md) — Recorded duplicate-child semantics and retained the architect-owned ARS-001 input-selection conflict.
- **Add**: [BR-005 — Evaluate multiple skill inputs together](/docs/requirements/eval-format-ownership/br-005-evaluate-multiple-skill-inputs-together.md) — Captured the user's approval for a combined skill-family run, with per-skill/case/iteration identity and comparison preserved and no cross-skill aggregate.
- **Update**: [Requirements bundle index](/docs/requirements/eval-format-ownership/index.md) — Added BR-005 and recorded the unresolved ARS-001 single-input architecture conflict and architect-owned input-selection surface.
- **Update**: [BR-004 — Present readable Markdown and HTML results](/docs/requirements/eval-format-ownership/br-004-present-readable-markdown-and-html-results.md) and [OC-002 — Evaluation output conformance](/docs/requirements/eval-format-ownership/oc-002-evaluation-output-conformance.md) — Clarified evidence retention as preserving existing capture, sanitization/redaction, and truncation behavior without report-only omission/truncation or an unlimited-capture promise.
- **Add**: [QS-001 — Keep multi-skill five-iteration reports understandable](/docs/requirements/eval-format-ownership/qs-001-readable-multi-skill-five-iteration-reports.md) — Added the user-requested scale condition and measurable per-iteration attribution criteria without adding aggregation semantics.
- **Update**: [Requirements bundle index](/docs/requirements/eval-format-ownership/index.md) — Recorded the scale amendment and evidence boundary.
- **Update**: [BR-004 — Present readable Markdown and HTML results](/docs/requirements/eval-format-ownership/br-004-present-readable-markdown-and-html-results.md) and [OC-002 — Evaluation output conformance](/docs/requirements/eval-format-ownership/oc-002-evaluation-output-conformance.md) — Added user-approved readable summaries for Markdown/HTML while retaining complete raw runtime evidence as supporting details; evaluation semantics and JSON/YAML contracts are unchanged.
- **Update**: [Requirements bundle index](/docs/requirements/eval-format-ownership/index.md) — Recorded the readability amendment, provenance, and remaining report-scope boundary.
- **Update**: [BR-001 — Accept both input contract families without collapsing semantics](/docs/requirements/eval-format-ownership/br-001-accept-both-input-contract-families.md), [BR-002 — Own output contracts across named formats](/docs/requirements/eval-format-ownership/br-002-own-output-contracts-across-named-formats.md), [BR-003 — Provide one user-facing evaluation interface](/docs/requirements/eval-format-ownership/br-003-provide-one-user-facing-evaluation-interface.md), [OC-001 — Evaluation case input conformance](/docs/requirements/eval-format-ownership/oc-001-evaluation-case-input-conformance.md), and [OC-002 — Evaluation output conformance](/docs/requirements/eval-format-ownership/oc-002-evaluation-output-conformance.md) — Added required OKF metadata without changing normative requirement content or relationships.
- **Update**: [Requirements bundle index](/docs/requirements/eval-format-ownership/index.md) — Added the applicable bundle change-log entry.
