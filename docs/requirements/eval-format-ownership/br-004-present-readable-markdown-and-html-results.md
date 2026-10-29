---
type: Requirement
title: Present readable Markdown and HTML results
description: Requires readable Markdown and HTML summaries for evaluation results while retaining captured evidence and its existing redaction/truncation state.
tags: [evaluation, output-contracts, readability, requirements]
timestamp: 2026-10-16T00:00:00Z
---

# BR-004 — Present readable Markdown and HTML results

**Priority:** Must (user-authorized scope)

**Source:** User request that Markdown and HTML results be human-readable, together with the user's explicit approval of a readable narrative with full captured results/evidence available in clearly identified details in the same report. The approval preserves existing evidence capture, sanitization/redaction, and truncation behavior; it does not authorize report-only omission or truncation, nor require unlimited output capture.

**Statement:** When producing Markdown or HTML for an eligible completed evaluation, the runner shall communicate the evaluation's outcome and applicable case-level results in readable status text and summaries, so a reader need not decode raw structured data to understand what happened; the same report shall retain the captured supporting evidence and required attempt details specified by OC-002, faithfully preserving existing evidence sanitization/redaction and truncation state.

**Acceptance criteria:**
- The report makes the overall run outcome and each case's outcome understandable from readable text, while preserving the distinction among pass, fail, and non-evidence.
- A reader can identify the represented case(s), attempt/execution history, and applicable family-owned results without interpreting raw JSON/YAML field-value structure. For skill ablation, this includes understandable baseline and candidate outcomes and their comparison; for agent/runtime cases, this includes applicable authored assertion outcomes.
- Supporting evidence is associated with the relevant run, case, and attempt. A reader can distinguish evidence content from a summary or classification.
- Captured runtime stdout/evidence and required attempt details remain available in clearly identified supporting details in the same report. Existing sanitization/redaction and truncation metadata remain accurate and visible; rendering adds no omission or truncation for presentation convenience. This requirement does not expand evidence capture limits or require unlimited raw bytes.
- Readability does not change evaluation behavior, provider/image choices, result fields or semantics, or JSON/YAML contracts. This requirement does not require polished branding, new report capabilities, or a prescribed visual layout.

**Verification path:** Inspect Markdown and rendered HTML for representative eligible agent/runtime and skill-ablation results. Without decoding raw serialized data, verify a reader can state the run and per-case status, identify attempts and applicable family-specific results/comparison, and locate associated supporting evidence. Compare the captured evidence and attempt details in each report with the corresponding verified result, including sanitization/redaction and truncation indicators; any report-only omission/truncation, wrong association, misleading metadata/status, or need to decode raw structures to learn the results falsifies this requirement.

## Derived from
- [Evaluation format ownership handoff](../../eval-format-ownership-handoff.md), as amended by the user's current readability request and explicit approval of complete supporting evidence alongside a readable narrative.
- [OC-002 — Evaluation output conformance](oc-002-evaluation-output-conformance.md).
