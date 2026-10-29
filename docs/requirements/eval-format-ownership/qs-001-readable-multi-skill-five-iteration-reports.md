---
type: Quality Scenario
title: Keep multi-skill five-iteration reports understandable
description: Requires Markdown and HTML result views to remain readable and unambiguous for a run with multiple skill evaluations repeated five times.
tags: [evaluation, readability, quality-scenarios, scale]
timestamp: 2026-10-16T00:00:00Z
---

# QS-001 — Keep multi-skill five-iteration reports understandable

**Priority:** Must (user-authorized scope)

**Source:** User's scale question: Markdown/HTML must remain understandable for all evaluations across multiple skills and five iterations. The user also approved keeping full captured results/evidence in the same report after its readable narrative, subject to existing capture, sanitization/redaction, and truncation behavior.

**Statement:** When a completed eligible skill evaluation includes multiple skills with five iterations per evaluated case, the Markdown and HTML reports shall let a reader understand the overall run outcome and locate every skill/case iteration's result without decoding raw machine data. The report shall distinguish run-level status from the separate iteration results, present each skill iteration's applicable baseline and candidate outcomes and comparison, and keep its attempts and captured evidence attributable to the relevant iteration. This scenario adds no per-skill pass-rate or other aggregate verdict.

**Acceptance criteria:**
- A reader can identify the overall run outcome, every represented skill/case, and each of its five iterations and status from readable text.
- For each skill iteration, its baseline outcome, candidate outcome, and comparison are distinguishable and attributable to that iteration; repeated iterations are not presented as additional run-level or per-skill aggregate verdicts.
- A reader can locate the attempt history and captured supporting evidence for a selected skill iteration without decoding raw JSON/YAML field-value data. Existing sanitization/redaction and truncation indicators remain accurate; the report adds no presentation-only omission or truncation.
- The report does not invent per-skill pass rates, collapse semantics, or evaluation meaning beyond the existing run and case results.
- The report's human-readable status does not change the verified run/case classifications or other output semantics required by BR-004 and OC-002.

**Verification semantics:** Use an eligible, verified skill evaluation with at least two distinct skills and five iterations per evaluated case, with known run-level and per-iteration outcomes, including distinguishable baseline/candidate comparisons and captured evidence/attempts. Inspect each generated Markdown and HTML report without decoding its raw serialized details. Check that a reader can name the run outcome, find all skills/cases and their five iterations, correctly match each status and comparison to its iteration, and locate that iteration's attempts and captured evidence. Compare displayed statuses and evidence metadata to the verified result. Any unlocatable or conflated iteration, misleading aggregate, incorrect family-specific outcome, evidence misassociation, or report-only loss/truncation falsifies this scenario. This measures report coverage and unambiguous attribution for the stated workload; it does not impose a time limit, a new aggregation rule, or an unlimited evidence-capture requirement.

## Derived from
- The user's explicit scale question for multiple skills and five iterations.
- [BR-004 — Present readable Markdown and HTML results](br-004-present-readable-markdown-and-html-results.md).
- [OC-002 — Evaluation output conformance](oc-002-evaluation-output-conformance.md).
