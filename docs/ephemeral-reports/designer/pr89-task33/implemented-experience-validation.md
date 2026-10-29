---
type: Report
title: PR89 task 3.3 assembled report assessment
description: Browser and CommonMark assessment of the actual two-skill five-iteration and native-read runtime reports; four renderer corrections remain.
tags: [evaluation, reports, design-validation, pr-89, task-3.3]
timestamp: 2026-10-29T19:52:00Z
---

# PR89 task 3.3 — actual assembled reports

## Verdict

**Product assessment: FAIL. QA: FAIL for readable-report completion.** Actual report observation is now available, but Task 3.3 cannot pass: incorrect percentages, raw invocation dumps in the primary reading layer, incomplete readable family outcomes, and runtime HTML reflow failure remain. These are implementation corrections, not requests for a new design. The execution/persistence evidence in Task 3.2 is not invalidated; affected human-readable outputs need regeneration from those same verified runs and reassessment after correction.

This is an independent assessment of implementation, **not a blind assessment**: the accepted design and prior findings were supplied. No production files, accepted design, requirement, plan status, run artifact, or generated report was changed. No eval invocation, provider call, commit or push occurred.

## Authority and actual inputs

- [Completion plan](../../../plans/runner-evaluation-format-contracts.md), Task 3.3 and E2E-001/002.
- [Accepted report baseline](../../../design/eval-format-ownership/multiskill-readable-report-baseline.md): status-first scan; skill → case → iteration; independently visible comparisons; same-report full captures; keyboard and narrow-layout conditions.
- [Prior assessment](../pr89-task23/implemented-experience-validation.md), particularly corrective guidance 1–10 and its later validation scenarios. Its fixture-only observations are not reused as assembled proof.
- [Combined execution evidence](../../product-acceptance/task32-2026-10-29/report.md): run `f47f708d31cf42b489900c870838ea43`, two distinct skills, one selected case each, five iterations each. Actual outputs: `docs/ephemeral-reports/product-acceptance/task32-2026-10-29/renders/skill.{json,markdown,html}`.
- [Runtime execution evidence](../../product-acceptance/task32-runtime-followup-2026-10-29/report.md): run `dd23dedc71614b6082fcbb1cc2038c6b`, actual native read and result assertion. Actual outputs: `docs/ephemeral-reports/product-acceptance/task32-runtime-followup-2026-10-29/renders/agent-runtime.{json,markdown,html}`. The older conversation-response run is not counted as native runtime proof.

Observed checkout: `d2a7c582a0a6e075dbf4bd93df644603ce75921d`, initially clean. These are committed reports produced on the earlier source revisions recorded in their execution reports, not newly executed evaluations at this checkout. Current `runner/eval_output.py` was inspected for correction locations after semantic module discovery.

Only the external provider was deterministic; the reports are actual assembled product outputs, not renderer unit fixtures. The provider-controlled grade does not establish semantic judge quality or live-provider compatibility.

## Observation method and evidence

SynaBun's configured `codex-browser` profile was inspected; navigation failed with “Could not start the shared browser session.” Recovery succeeded with installed Playwright Core and local headless Chromium **156.0.8078.4**. Actual HTML files were opened directly with `file://`, without modifying their DOM or styles for baseline observations. Evidence disclosures were then opened for layout and completeness checks.

Observed conditions: 1280×900 desktop and 320×900 CSS-pixel viewport, default browser font/styles, keyboard Tab/Shift+Tab, Enter and Space, contents/iteration anchors, disclosure focus, and Chromium accessibility-tree names/expanded states. CSS `zoom:200%` was additionally probed, **not actual browser zoom**; actual 200% browser-zoom verification remains open. No screen reader or participant session, forced-colors audit, comprehensive contrast audit or blanket WCAG conformance assessment occurred.

Markdown host: installed **markdown-it-py 4.2.0**, CommonMark preset, HTML enabled, rendered in the same Chromium with default host stylesheet. This establishes one named rendering environment, not GitHub/editor-host compatibility. Generated host renderings are derived directly from the committed Markdown, not mockups. Host-specific Markdown reflow is not attributed to the product's HTML renderer.

Reproduction/evidence retained on this host:

- `/tmp/opencode/pr89-task33-probe.mjs` → `/tmp/opencode/pr89-task33/browser-observations.json` (outline, anchor targets, keyboard focus, layout measurements).
- `/tmp/opencode/pr89-task33-static.py` → `/tmp/opencode/pr89-task33/static-observations.json` (input hashes, Markdown JSON backstop equality).
- `/tmp/opencode/pr89-task33-detail.mjs` → `/tmp/opencode/pr89-task33/detail-observations.json` (capture scalar inclusion, native accessibility state, CommonMark rendering).
- Selected screenshots retained beside this report (binary evidence assets, not indexed knowledge documents): `skill-desktop.png`, `skill-commonmark-desktop.png`, `runtime-open-detail-320.png`. Additional screenshots remain under `/tmp/opencode/pr89-task33/`; scripts and unarchived observations are ephemeral, not guaranteed after host cleanup.

The initial probe's skill disclosure had already been opened during keyboard navigation, so its Enter closed and Space reopened it; its label “Space closes” is inaccurate. The separate detail probe starts afresh and confirms Enter opens / Space closes both reports. No PASS rests on that mislabeled intermediate step.

## What now works

| Journey/check | Directly observed result |
| --- | --- |
| Identify run and outcome | Both formats identify the correct run, creation time and explicit pass classification. Combined report shows 10 jobs, all pass; runtime report shows 1 job, pass. No per-skill/cross-skill aggregate was invented. |
| Locate both skills and all iterations | Combined HTML and Markdown group `python-testing` / `asyncmock-for-awaitable`, then `python-error-handling` / `domain-error-to-409`. Each has five independently labeled pass iterations in ascending order and its own canonical identity. |
| Distinguish candidate from comparison | Each combined iteration explicitly separates baseline/candidate classification, candidate absolute pass, compared status, delta, neutral skill value and trap change. The score magnitude is wrong (F1). |
| Navigate combined HTML | All 14 contents/iteration links have existing targets. Keyboard activation reaches report sections; Tab/Shift+Tab and native disclosures work. Focus outline is visible; Chromium exposes `DisclosureTriangle`, meaningful text and expanded true/false. These observations do not establish screen-reader announcements. |
| Preserve report reading order and non-color status | Semantic HTML headings follow run → skill → case → iteration → comparison; source/visual order agree. Runtime HTML uses a combined case/iteration heading. Status is explicit black text, not color-only. |
| Retain same-report capture facts | All 10 combined Markdown iteration JSON fences and the runtime fence decode exactly equal to their respective same-run JSON case projections. For all 11 HTML disclosures, every primitive case value is present with matching multiplicity after parsing JSON scalar text (numeric formatting normalized). No missing scalar capture was found. This is a completeness backstop, not approval of navigability or literal presentation outside it. |
| Reflow combined HTML | With all evidence open, document scrollWidth is 320 at viewport 320, and 1280 at viewport 1280; no right-edge overflowing element was detected. Visible focus and wrapped capture/IDs were observed. Runtime HTML fails the same check (F4). |

All actual jobs here pass, all comparisons are neutral, all attempt counts are one, and no capture truncation was exercised. This dataset cannot prove readable FAIL/NON-EVIDENCE/error/retry handling, nonzero/negative delta, differing iteration verdicts, unavailable comparison, or redacted/truncated capture behavior. Those states remain unverified here, not implicitly approved by successful neighboring checks.

## Required corrections

### F1 — Scores are displayed 100 times too small

- **Drift / impact:** behavioral presentation; **major**.
- **Location:** both combined readable reports, every iteration; `runner/eval_output.py:1085–1114`.
- **Accepted intent:** baseline outcome/comparison and prior guidance 4 require truthful percentages from recorded comparison facts.
- **Observed:** first visible comparison says “Baseline: pass (1.00%); candidate: pass (1.00%).” All ten JSON comparisons contain `baseline_score=1.0`, `candidate_score=1.0`; the stored decision summary explicitly says “baseline 100.00%; candidate 100.00%; delta +0.00 pp; neutral.” The raw supporting comparison contradicts the opening sentence.
- **Consequence:** the quick-review layer misrepresents measured quality; readers must discover the contradiction in supporting data.
- **Owner / correction:** renderer implementation. Render normalized scores as percentages consistently with the verified decision summary; keep `delta_pp` in percentage points (do not apply the score conversion to it). Recheck both output versions/formats and nonzero deltas, not only this zero-delta run.

### F2 — Attempt summaries dump full invocation/capture dictionaries into the primary layer

- **Drift / impact:** structural and visual, with literal-capture presentation drift; **major**.
- **Location:** both families and both readable formats; `runner/eval_output.py:1148–1155, 1221–1237, 1294–1304, 1366–1369, 1383–1385`.
- **Accepted intent:** baseline §§16–23, 119–143 and prior guidance 7–9: concise phase history outside details; full answers/raw streams separately labeled in supporting details, preserving literal content.
- **Observed:** each phase prints `attempt 1 result {<entire invocation result>}; retry None`. This includes answer, raw stdout JSON, tool results, runtime evidence and plugin diagnostics. Runtime HTML joins target/judge/check/readiness summaries into one enormous paragraph; the initial 900 px view is consumed by the target dictionary. Combined HTML similarly places the full four-phase dump before its supporting disclosure. The disclosure does not prevent a duplicate capture wall above it.
- **Markdown-specific observation:** in the named CommonMark host, missing block separation folds “Candidate result” into the final baseline expectation bullet, and folds the attempt dump into the final candidate bullet. Captured skill Markdown inside the unfenced dictionary becomes host Markdown: 120 links are rendered in the combined report, including captured pytest documentation links; backtick content is interpreted as inline code instead of remaining a literal captured stream. The exact fenced case record is still intact, so this is not a claim of total evidence loss or an executed exploit.
- **Consequence:** reviewers cannot scan an attempt history without traversing raw records; copied captured content is confused with report structure, and its literal delimiters are not faithfully displayed in that duplicate narrative.
- **Owner / correction:** renderer implementation. Summarize phase/attempt/result and actual retry decision/reason using recorded outcome facts, not the entire result object and not success inferred solely from host exit code. Keep full capture data in labeled same-report supporting material; provide distinct side/phase/attempt answer, judge, stdout/stderr, authoritative-evidence and marker sections so locating them does not require tracing a field tree. Separate Markdown blocks and keep captured text literal. No new invocation or synthesized answer interpretation is needed.

### F3 — Important family outcomes still require decoding supporting records

- **Drift / impact:** structural; **major**.
- **Location:** combined HTML `_combined_html` at `runner/eval_output.py:1292–1304`; runtime `_agent_narrative` at `1137–1145` and HTML/Markdown callers.
- **Accepted intent:** baseline readable evidence association and prior guidance 5–6, 8–9; BR-004-readable family outcomes, not merely data retention.
- **Observed:** combined Markdown has direct baseline/candidate expectation-met lists, but combined HTML omits those readable lists and judge interpretation, exposing them only through the full dictionary/tree. Runtime summary says only `tool_results — pass: required tool result observed`: the authored predicate (`read`, path `runtime-proof.txt`, success, required marker) and matching observation are not made into a readable assertion entry. The suite name and authored agent `general`, the two semantic expectations with their outcomes/reasons, the forbidden-rule outcome and declared trap observation/evidence are available in the JSON/backstop (or duplicated raw attempt text), not an organized readable family result.
- **Consequence:** a reviewer can see PASS, but cannot explain what passed or distinguish deterministic evidence from semantic grading without decoding captures and field keys. HTML and Markdown do not offer equivalent readable family explanations.
- **Owner / correction:** renderer implementation. Expose the already-recorded rule/expectation outcomes and reasons with baseline/candidate attribution in HTML as in Markdown. For runtime, present suite/agent/execution, each authored assertion with associated observed evidence, deterministic checks versus semantic expectations/violations/trap and recorded summary as labeled linear entries. Preserve full backing records; do not invent judge conclusions or assertions absent from the run.

### F4 — Runtime HTML loses narrow-layout accessibility when evidence is open

- **Drift / impact:** accessibility and visual; **major**.
- **Location:** actual runtime HTML supporting disclosure; v1 HTML document at `runner/eval_output.py:1384–1388` and nested `_html_tree` at `983–1007`.
- **Accepted intent:** baseline WCAG 2.2 SC 1.4.10 / 1.4.4 design conditions: IDs, paths and open captures available at 320 CSS px without horizontal scrolling/loss.
- **Observed:** with evidence open, runtime document scrollWidth is **1520 px at a 320 px viewport**, and still 1520 at 1280. Nested default definition-list margins push deep fields beyond the visible page; the saved 320 px screenshot shows a mostly blank viewport with clipped text at the right edge. The v1 HTML has no corresponding wrap/indent treatment applied by combined HTML. Combined HTML passed this same measured check.
- **Consequence:** a narrow-view reader must pan horizontally through deeply indented evidence; ordinary sequential reading cannot expose the facts within the viewport.
- **Owner / correction:** renderer implementation. Apply bounded indentation and wrapping to v1 as well as combined reports, including long scalar strings and open nested captures. Recheck the same actual runtime report at 320 CSS px and actual 200% browser zoom, with evidence open; do not merely hide horizontal overflow.

## Advisory and boundaries

- Native disclosure behavior and the combined heading/anchor system should be retained. No dashboard, branding, filters, charts, new aggregation, or custom controls are justified by these findings.
- Same-numbered disclosures are distinguishable in their surrounding case sections; additional full-context labels might help a flattened control list, but this is advisory, not a new blocking design direction.
- The raw-stream disclaimer and exact same-report backing records are useful. Correcting the primary layer should not discard “duplicate” capture facts or change capture/redaction policy.
- Actual 200% browser zoom, assistive-technology announcements, diverse failure/retry states, and adversarial literal labels/captures beyond those present in these runs remain unproven. CSS zoom is not substituted for browser zoom. No blanket WCAG or independent semantic-judge-quality claim is made.

## Handoff

Renderer owner: correct F1–F4 in `runner/eval_output.py`, with focused tests that assert readable facts outside raw trees/disclosures and named-host literal rendering. Product integrator: regenerate affected Markdown/HTML through public persisted-run rendering of the **same** two verified runs; keep previous output provenance honest. Designer/follow-up reviewer: reassess regenerated outputs, particularly numeric truth, family explanations, attempt scan, capture attribution and runtime open-evidence reflow. No new model run is implied by these presentation corrections.

There is no user-owned taste/scope decision or identified missing backing capability: the needed facts already exist in these actual projections. No new stories/scenarios were authored; this validates accepted journeys, not new behavior. Task 3.3 stays not accepted until findings are corrected and rechecked. Task 3.2's machine-path proof is separate from this report-experience failure, and neither establishes PR merge readiness.

Skills loaded: `design-validation`, `accessibility-design`, `accessibility-implementation`, `okf-authoring`. Installed `design-validation/ASSESSMENT.md` and `QA.md` lenses were read directly after Loom companion calls were denied because the configured designer lacks assessment/qa roles. No role configuration was altered and no privileged QA registration is claimed; these are the designer's own evidence-backed product assessment/QA judgments. The QA pass through alternate family, narrow viewport, raw-data parity and actual CommonMark rendering found failures despite improved status headings and preserved data.

This task-specific ephemeral report has no existing local index/log; no new design bundle or shared plan/index/log was introduced. Shared status reconciliation belongs to the integrator. Single-file OKF validation with the existing `Report` vocabulary passes; default single-file validation otherwise warns that `Report` is unknown. Dangling-reference inspection reports 11 existing findings outside this report; screenshot assets are identified as file references, not knowledge-document edges. No graph profile is loaded, so typed graph conformance is not claimed.
