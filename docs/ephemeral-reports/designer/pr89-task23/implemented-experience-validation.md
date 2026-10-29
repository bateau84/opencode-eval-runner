---
type: Report
title: PR89 task 2.3 report experience assessment
description: Bounded pre-fix assessment and implementation guidance against the accepted readable-report design at c62295b; not assembled-product acceptance.
tags: [evaluation, reports, design-validation, pr-89]
timestamp: 2026-10-29T18:49:00Z
---

# PR89 task 2.3 — report experience assessment

## Disposition and observation boundary

**Mode: validation with corrective guidance, not a new design. Product assessment: FAIL for current readable-report completion. QA: local renderer evidence only; assembled-product/design acceptance remains UNPROVEN.**

Observed checkout: `feat/evaluation-format-contracts`, HEAD `c62295b`, initially clean. No production source edits, commits, provider calls, or OCI invocations were made. Existing provider-free tests generated actual renderer output through test-substituted invocation and real local persistence/verifier/render paths. These are fixtures, not real evaluations. No browser, Markdown-host rendering, keyboard, accessibility-tree, zoom, or reflow observation was performed. This cannot close tasks 3.2 or 3.3 or certify accessibility.

Authority reviewed:

- [Completion plan](../../../plans/runner-evaluation-format-contracts.md), particularly task 2.3 and the task 3.2/3.3 proof boundary.
- [BR-004](../../../requirements/eval-format-ownership/br-004-present-readable-markdown-and-html-results.md), [OC-002](../../../requirements/eval-format-ownership/oc-002-evaluation-output-conformance.md), and [QS-001](../../../requirements/eval-format-ownership/qs-001-readable-multi-skill-five-iteration-reports.md).
- [Accepted report design](../../../design/eval-format-ownership/multiskill-readable-report-baseline.md), especially information architecture, evidence/status semantics, and accessibility conditions.
- [ARS-001](../../../architecture/eval-format-ownership/specifications/ars-001-runner-eval-contract.md), especially result distinctions, closed family records, unavailable values, and combined provenance.

## Reproducible local evidence

Commands executed successfully with system Python / pytest 9.1.1:

```text
python -m pytest tests/test_eval_builtin_cli.py::test_skill_eval_runs_four_phases_and_preserves_comparison_and_pair_integrity tests/test_eval_builtin_cli.py::test_combined_markdown_and_html_render_five_iterations_under_repeated_skill_inputs --basetemp=/tmp/opencode/pr89-task23-design-fixtures-c62295b -q
# 2 passed
python -m pytest tests/test_eval_builtin_cli.py::test_render_run_projects_one_verified_result_without_invocation --basetemp=/tmp/opencode/pr89-task23-agent-design-fixtures-c62295b -q
# 1 passed
```

Evidence directories (ephemeral; preserve before cleanup):

- `/tmp/opencode/pr89-task23-agent-design-fixtures-c62295b/test_render_run_projects_one_v0/`: `result.json`, `result.markdown`, `result.html`, `result.yaml`, and `artifacts/`. Run `42297ebf12884d0ab16028d96687c4a3`, one agent/runtime role-decision case, one iteration, PASS. This fixture has no authored runtime assertions; it does not exercise their presentation.
- `/tmp/opencode/pr89-task23-design-fixtures-c62295b/test_skill_eval_runs_four_phas0/`: `skill.json`, `skill.markdown`, `skill.html`, `skill.yaml`. Run `b76a8e2f568b4b05b74737712177797c`, one skill/case/iteration: baseline FAIL, candidate PASS, comparison PASS, 66.67% versus 100.00%, +33.33 pp, material-improvement. The test deliberately corrupts the persisted pair after producing the reports; do not use its final artifact directory as an eligible render source.
- `/tmp/opencode/pr89-task23-design-fixtures-c62295b/test_combined_markdown_and_htm0/`: `combined.json`, `combined.markdown`, `combined.html`, `combined.yaml`, and `combined-five/`. Run `e51a597d48464d0db6e2317e9aee4df2`, two input occurrences of the **same** skill, two cases, five iterations each, ten PASS jobs. First iteration: baseline/candidate 100%, +0.00 pp, neutral; undeclared trap values are null. This is not the required two-distinct-skill acceptance workload.

These three passing tests establish bounded current renderer behavior, not readability acceptance. Existing assertions largely check field/key presence and heading counts (`tests/test_eval_builtin_cli.py:669–675, 881–913`).

## Findings

### F1 — v1 outcomes require field-tree decoding

- **Drift / impact:** structural and behavioral presentation; major.
- **Location:** `runner/eval_output.py:1253–1288`; generated agent report lines 5–47 and 49 onward; generated single-skill reports.
- **Accepted intent:** BR-004 criteria 18–21; OC-002 readable family-specific outcomes.
- **Observed:** v1 emits the run and each full case through `_pretty` / `_html_tree`, without a readable overview, assertion/judge summary, or ablation summary. Skill reports do not receive the accepted skill → case → iteration organization just because they contain one input.
- **Consequence:** readers must reconstruct the outcome and attempt history from serialization labels, and one-input reports fail the same reading task that combined reports partially support.
- **Owner / correction:** implementation fix; apply the accepted summary-first experience to both families and both output versions, without changing schemas.

### F2 — v2 has the right outer grouping but incomplete reading hierarchy

- **Drift / impact:** structural; major.
- **Location:** `runner/eval_output.py:1085–1101, 1148–1162, 1217–1225`; generated combined Markdown lines 24–61.
- **Accepted intent:** accepted design section hierarchy and per-iteration outcome/comparison; task 2.3.
- **Observed:** visible candidate/baseline/comparison status is useful. However, the next block is the complete comparison field tree. Scores, delta, trap change and skill value are not presented together as direct readable labels; attempts, checks, side outcomes and evidence readiness require entering the full iteration tree. The useful stored decision summary is buried inside that tree.
- **Consequence:** a reviewer can find an iteration but still must decode the record to explain what happened or locate a particular phase's evidence.
- **Owner / correction:** implementation fix; retain existing grouping and replace field-tree dependence in the primary reading layer with the guidance below. Keep complete records as supporting material.

### F3 — Markdown input-derived labels can be interpreted as markup

- **Drift / impact:** suspected rendered-content loss; potentially major.
- **Location:** generated combined Markdown line 13 is `#### Case helper: <first case>`; `runner/eval_output.py:1136`.
- **Accepted intent:** recognizable readable case identities, escaped input-derived content, same-report fact preservation.
- **Observed:** literal angle-bracket input is placed in Markdown headings; HTML output escapes it. No Markdown host was exercised, so actual rendered loss is not established here.
- **Consequence:** a Markdown host may consume the label as HTML rather than showing the authored identity. New summary labels introduce the same risk for punctuation, links, newlines and code fences unless treated as captured text.
- **Owner / correction:** implementation fix and renderer/Markdown-host check; preserve literal text meaning in both formats. Do not treat captured text as report markup or narrative authority.

## Exact corrective guidance for task 2.3

This operationalizes existing accepted design; it adds no product capability or aggregation.

1. **Opening:** run identity, creation timestamp, family/execution mode, plain-language run status and the existing planned-job counts. Explain a `verdict` status with those counts rather than relabeling it PASS/FAIL or implying missing evidence is failure. Keep provenance/configuration in run details, not the opening field tree. Use the verified summary; do not independently recompute verdicts.
2. **Organization:** every skill report, including v1, uses skill → case → ascending iteration. Group repeated occurrences of the same skill together; keep case source attribution intact. Show readable case name/source ID with canonical ID retained nearby. A case gets only its actual iterations, each individually labeled and indexed; never pad one iteration into five. Preserve source-derived ordering within groups. For agent/runtime, use case → iteration with suite, authored agent, optional skill and execution mode identified; do not invent a tested-skill group for cases without one.
3. **Visible iteration outcome:** show execution state and recorded classification as distinct concepts. PASS, FAIL and NON-EVIDENCE remain explicit text. For skill ablation, present baseline classification, candidate absolute classification, comparison availability/status and comparison decision separately; neither skill value nor positive delta means candidate correctness.
4. **Readable skill comparison:** when compared, show baseline score and candidate score as percentages, signed delta in **percentage points**, candidate absolute pass, skill-value label, and trap change together. A direct sentence plus short labeled bullets is sufficient. For the recorded one-skill fixture: “Baseline: FAIL (66.67%). Candidate: PASS (100.00%). Comparison: PASS; delta +33.33 percentage points; skill value: material-improvement. Trap: neither fixed nor regressed.” Use the source facts, not these fixed values. For undeclared traps say “No trap declared; trap change not applicable,” not “not observed.” For invalid/non-evidence comparison show its actual status and failure reason, retain both side outcomes, and say scores/comparison decision are unavailable where applicable; never substitute zero, neutral or a successful comparison.
5. **Baseline and candidate result sections:** keep their checks/readiness and judge outcomes distinct. Show authored positive rules with met/not met and reason, negative rules with violated/not violated and reason, declared trap observation/evidence, and recorded judge summary where available. These are existing family facts, not new grading or generated answer interpretations. The full captured answers remain below; do not write model-generated answer summaries or add another invocation.
6. **Agent/runtime result sections:** state execution mode; present each applicable authored assertion with its own status and reason, and retain its authored/observed detail association. Present deterministic checks separately from semantic judge expectations, forbidden-rule results, trap result and judge summary. A missing judge is “not run/unavailable,” not PASS; only explain why it was skipped when recorded facts support that explanation. An absent assertion category is “None authored/applicable,” not a synthetic passing check.
7. **Attempts and checks:** provide a short, directly readable phase-by-phase history outside the evidence disclosure: phase name, actual attempt number, result or recorded failure, and retry/no-retry decision/reason when recorded. Show each phase's recorded checks and evidence readiness/reasons in its own context. Do not claim invocation success from host exit code alone or infer judge execution from a null semantic record. Full timestamp/duration/effective invocation/result/failure/retry data remains in supporting detail. Keep target/judge and baseline/candidate attribution even when their text happens to be identical.
8. **Captured answers and evidence:** clearly name side, phase, attempt and iteration so a reader can locate a capture without tracing machine keys. Separate assistant answer, judge result, raw stdout, raw stderr and authoritative runtime evidence. Place captured text and its own redaction/truncation/loss markers together. Full verified field trees may remain as completeness backstops, but not as the only route to answers, attempt history or family outcomes. Do not drop “duplicate” fields, limit lists, clip long text, or link to external artifacts instead of including required captured detail. Use no additional sanitization/capture policy in this presentation change.
9. **HTML and Markdown:** same facts and logical order. HTML native disclosures are for full captured supporting material only; outcome, comparison, attempts/checks/readiness summaries remain visible. Retain contents links to skill/case sections and iteration-index links with unique targets. Use semantic headings without flattening same-numbered iterations into one global list. Escape all input-derived values; Markdown labels and captures also stay literal rather than executing as HTML/Markdown. Preserve evidence characters/line breaks through a safe text representation, not semantic omission.
10. **Accessibility:** retain accepted WCAG 2.2 AA design conditions, not a new conformance claim: semantic relationships/source order (1.3.1/1.3.2), explicit non-color status (1.4.1), 320 CSS px and 200% text/zoom availability without horizontal loss (1.4.10/1.4.4), keyboard-reachable native links/disclosures and visible focus in reading order (2.1.1/2.4.3/2.4.7), meaningful labels (2.4.6), native name/state (4.1.2). Long IDs, paths and open captures need the same narrow-layout treatment as summaries. No dashboard, filters, custom widgets, charts, branding system, cross-skill comparison, new recovery controls, or new aggregates.

### Minimum local QA coverage to accompany the correction

- Assert readable sentences/labels **outside** full-record trees/disclosures, not just key presence, for v1 agent/runtime, v1 skill and v2 skill.
- Cover PASS, observed FAIL and NON-EVIDENCE; compared versus invalid/non-evidence comparison; positive/zero/negative delta; unavailable scores; absent versus declared trap; candidate FAIL despite a favorable comparison metric; judge skipped/unavailable; retries and failures with distinct phase/attempt captures.
- Assert per-iteration facts differ correctly across a five-iteration fixture; include two distinct skills and repeated same-skill input occurrences, readable duplicate display names with distinct canonical IDs, and source provenance preservation.
- Compare report-captured content and metadata to the same verified projection, including long text, literal markup/code fences, redaction and truncation indicators, and runtime evidence. Both summary truth and supporting-detail completeness matter. JSON/YAML and closed schema remain unchanged.
- No fabricated family result or terminal not-run placeholder merely to make a report render: ineligible runs remain output failures under OC-002 / ARS-001.

## Later task 3.3 validation scenarios

Use the real task 3.2 reports and their same verified persisted results, recording final HEAD, run IDs and source paths. Do not close these with the fixtures above.

1. **Scan and explain:** in actual agent/runtime and single-skill reports, state run/case/iteration outcomes, execution mode, assertions or paired outcomes, attempts and readiness without reading a raw field tree. Compare each statement with that run's verified result.
2. **Navigate a real combined run:** identify both distinct skills, each case, all five independently visible iteration statuses; choose an iteration and state its own baseline/candidate scores/classifications, comparison/skill value and trap state. Confirm no per-skill aggregate or copied first-iteration values.
3. **Follow evidence:** locate that iteration's own phase/attempt history, checks, full answers, judge results, raw streams, authoritative evidence and capture markers without leaving the report. Confirm exact association and completeness against the same result. Include a recorded non-evidence/failure/retry case where available; missing state coverage stays explicitly unverified.
4. **Use HTML without a mouse:** navigate contents and iteration links, Tab/Shift+Tab through native disclosures, activate them, inspect visible focus, accessible names/expanded states and heading outline. Essential outcomes remain visible before opening details. Check sequential reading preserves context.
5. **Read narrow and enlarged:** inspect 320 CSS px and 200% zoom with evidence open; exercise long canonical IDs, paths and captured lines. Verify no horizontal loss, clipping or color-only status. Check rendered Markdown in a named host, including literal angle brackets and punctuation in labels/captures.

## Design authority and handoff

No user-owned choice remains. The existing accepted summary-first nested hierarchy wins over the already rejected wide table, global iteration ordering, separate-evidence artifacts and collapsed-all-details alternatives. Corrections belong to the renderer owner; real execution/provenance belongs to task 3.2 and rendered experience proof to task 3.3. No missing backing capability was found for the bounded guidance: inspected result models already contain the relevant facts. Actual assembled capability remains unproven, not approved by this assessment.

The accepted design artifact is unchanged; no new stories/scenarios are needed for this conformance correction. The checks above reuse its accepted journeys, with BR-004's agent/runtime coverage. Skills loaded: `design-validation`, `accessibility-design`, `okf-authoring`. Style-guide lookup for this workspace returned “Project not registered”; no branding direction was introduced. This ephemeral report records findings, not new authoritative design or requirements.

Documentation checks: single-file OKF validation returned zero errors/warnings/notifications. Corpus dangling-link inspection returned 11 existing findings in architecture, requirements and plan sources, none from this report; no graph profile was loaded, so typed graph conformance is not claimed. No existing authoritative bundle index/log/design was modified. This task-specific ephemeral evidence report has no existing local index/log to reconcile; no redundant design bundle was created.
