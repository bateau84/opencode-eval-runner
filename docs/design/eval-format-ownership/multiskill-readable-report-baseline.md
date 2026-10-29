---
title: Combined skill report baseline
type: Design
description: Human-readable information architecture for combined skill evaluation reports, including per-skill comparisons, five visible iterations, and same-report evidence.
tags: [evaluation, reports, readability, multi-skill, design]
---

# Combined skill report baseline

**Status:** User-approved design baseline; implementation-independent. This is
not a claim that the combined report is implemented or that the sample below
represents a multi-skill or five-iteration run.

## Experience context

An evaluator reviewing results needs to answer, without reverse-engineering
serialized fields: did this run complete, which skills and cases were covered,
what happened in each iteration, and what evidence supports the conclusion?
They may be scanning a short report or investigating one specific outcome. The
same document must support both tasks: a concise status-first scan and a
traceable path into the full captured record. Repeated answers in an overview
would obscure status; hiding evidence in a separate artifact would break the
approved same-report workflow.

### User story

As a person reviewing a combined skill evaluation, I want the run outcome and
each skill/case/iteration result to be easy to locate, so I can identify where
to investigate while still being able to inspect the complete captured answers
and evidence in the report. Success means I can find the run status, one
iteration's status and that iteration's own baseline/candidate comparison,
attempts, and evidence without decoding JSON/YAML. Source: user-approved
readable-report and multi-skill/five-iteration direction in BR-004, BR-005,
and QS-001.

### Scenarios

1. **Quick review, current single-skill sample.** A reviewer opens the actual
   saved Python-testing run report. In the summary they identify a passing run
   with one passing case. They follow the case into its baseline and candidate
   results and see the per-case comparison: both sides pass, both scores are
   100%, delta is +0.00 percentage points, and skill value is neutral. They
   can open or read on to the captured answer, judge details, attempts, and
   evidence without leaving the report. The report remains honest that this
   run has one case and one iteration.
2. **Locate a result in a combined run.** A reviewer scans the run summary,
   chooses a skill section, finds a case, then scans its five-entry iteration
   status index. They open the specific iteration and match its status to its
   baseline/candidate results, comparison, attempts, and captured evidence.
   This is a structural example only: no real multi-skill/five-iteration
   run has been supplied for this baseline, so its values remain placeholders.
3. **Read with keyboard or narrow viewport.** A keyboard user follows report
   contents links and opens a native details disclosure, then returns to the
   iteration context. A reader at 320 CSS px or high zoom reads the same
   content in a linear, non-wide layout. Status is expressed in text and not
   only by color or icon.

## Information architecture

**Primary organization:** One run first; within it, group by skill identity,
then case identity, then ascending iteration. This follows the reader's mental
questions (overall result → which skill/case → what happened this time) and
matches the required result attribution. Each iteration is a distinct entry,
not a roll-up. A run-level summary remains a run-level summary; no skill-level
pass-rate, score, ranking, or aggregate verdict is introduced.

**Findability:** Provide a compact contents list of the skill and case headings
for long HTML reports, with in-document anchors to the relevant iteration
detail. Markdown uses the same heading hierarchy and linkable anchors where
supported. The report remains fully readable when links are unavailable or
printed: headings and content order alone communicate the hierarchy. Do not
use a wide cross-skill/cross-iteration comparison table.

### Section hierarchy

```text
Evaluation run — [run id]
  Run overview
  Contents (long reports; links to skill/case sections)
  Skill: [identity]
    Case: [stable case identity / readable source identity]
      Iteration status index (1, 2, 3, 4, 5; each individually labeled)
      Iteration 1 — [status]
        Outcome and comparison
        Baseline result
        Candidate result
        Attempts and checks
        Captured answers and evidence
      Iteration 2 — [status]
        ...same structure, independent values...
      Iteration 3 — [status]
      Iteration 4 — [status]
      Iteration 5 — [status]
  Skill: [next identity]
    ...same case/iteration hierarchy...
  Run details (provenance/configuration and remaining run-level facts)
```

For each iteration's outcome, keep the candidate's absolute classification
distinct from the baseline/candidate comparison decision and skill-value
label. Display the baseline score, candidate score, delta, trap change, and
comparison status together within that skill/case/iteration. If comparison is
invalid or non-evidence, display that actual state and its reason; do not
substitute zero or imply a numeric comparison. The run summary may show the
existing run-level status/counts over planned jobs, but must not restate answer
content or imply that per-skill aggregates exist.

## Presentation by format

### Markdown

- Use a short run heading and summary bullets first; avoid field/value dumps in
  this opening section.
- Use nested headings for run → skill → case → iteration. Keep case headings
  under their run/skill, and each iteration heading beneath its case.
- Use short bullets or definition-style labels for status, comparison, and
  provenance. Prefer linear text and short lists over tables, especially for
  attempts and evidence.
- Place complete captured target/judge answers, checks, and supporting
  evidence under clearly titled iteration details in the same document. Mark
  captured raw process stdout/stderr as raw stream material, separate from
  assistant answers and judge interpretation.
- Retain the source's sanitization/redaction and truncation markers verbatim
  in meaning and make them visible beside the affected capture. Rendering may
  not silently omit or further truncate captured material.

### HTML

- Use the same semantic hierarchy and ordering as Markdown. A contents list
  links to skill/case headings; it is supplementary navigation, not the only
  way to understand the report.
- Use native `<details>`/`<summary>` only for full captured answer/evidence
  material that is secondary to the summary. The summary label names its
  content and associated iteration (for example, “Captured answers and
  evidence — iteration 1”). The browser's native disclosure behavior is the
  entire interaction model; no custom controls or script-dependent behavior
  are needed.
- Keep outcome, comparison and iteration status visible without expanding
  evidence. Each disclosure must preserve all captured content and its
  redaction/truncation metadata; it is not a mechanism for deleting, clipping,
  or moving evidence outside the report.
- Escape input-derived text. Raw stdout/stderr must be visibly identified as
  raw captured stream, not presented as the report's narrative or verdict.

## Examples

### Actual-data example: supplied one-skill, one-iteration run

Source reviewed: `/tmp/opencode/skills-before-631a3e6-python-testing-1-i1.md`
and its HTML counterpart, run `285177f31520435fb797ce2fa54d4ca9` (created
2026-10-16). This is an actual sample, not a fabricated scale run.

```text
Evaluation run 285177f31520435fb797ce2fa54d4ca9
Status: PASS — 1 pass, 0 fail, 0 non-evidence, 0 errors, 0 not run (1 job)

Skill: python-testing
  Case: skill:python-testing:1
  Iteration 1 — PASS (complete)
    Comparison: PASS; baseline 100.00%, candidate 100.00%, delta +0.00 pp;
                neutral. Candidate absolute pass: yes.
    Baseline answer: uses AsyncMock; awaits sync_one(client, "playlist-id");
                     asserts the result is "skipped".
    Candidate answer: same behavior, additionally asserts the awaited call
                      occurred once with "playlist-id".
    Judge: both baseline and candidate judges passed all five expectations;
           neither observed the declared plain-Mock trap.
    Attempts: baseline target, baseline judge, candidate target, and candidate
              judge each have their own recorded attempt.
    Captured answers, judge payloads, attempt metadata, and runtime evidence:
    available in this iteration's full details in the same report.
```

The excerpt condenses answers for readability; a report must retain the full
captured answer text and evidence in its associated details, not just these
summaries. The sample's actual report records no stdout/stderr truncation for
these phases; this example does not imply that future captures cannot carry
redaction or truncation markers. The supplied example has one skill, one case,
and one iteration only.

### Structural scale example: placeholders, not measurements

The following is a wireframe of hierarchy only. Every bracketed status/value
must come from a real verified run; none is asserted as sample data.

```text
Evaluation run [run id]
Status: [verified run status] — [existing run-level counts]

Skill: [skill A]
  Case: [case A]
  Iterations: 1 [status] · 2 [status] · 3 [status] · 4 [status] · 5 [status]
    Iteration 1 — [status from result]
      Comparison: baseline [result/score]; candidate [result/score];
                  delta [result]; trap change [result]; value [result]
      Attempts: [this iteration's attempts]
      Captured answers and evidence: [same-report details]
    Iteration 2 — [status from result]
      ...independent details...
    Iteration 3 — [status from result]
    Iteration 4 — [status from result]
    Iteration 5 — [status from result]

Skill: [skill B]
  Case: [case B]
  Iterations: 1 [status] · 2 [status] · 3 [status] · 4 [status] · 5 [status]
    Iteration 1 — [status from result]
      Comparison: [this skill/case/iteration's own baseline/candidate result]
      Attempts: [this iteration's attempts]
      Captured answers and evidence: [same-report details]
    ...iterations 2–5 remain separately visible with their own result details...
```

No totals or summaries are added under each skill in this example. If the
actual run contains several cases for a skill, each case gets its own index
and five iteration entries. The example's two skills and two cases illustrate
structure only and make no claim about actual run size or result.

## Evidence and status semantics

- Preserve all five statuses independently for every case; absence, error,
  not-run, non-evidence, fail, and pass remain distinguishable according to
  the verified result. Do not use an empty or missing slot to imply success.
- Associate attempts, checks, baseline/candidate answers, judge outcomes,
  comparison facts, and evidence with their originating skill/case/iteration.
- Keep captured assistant answer, judge result, raw stdout/stderr, and
  evidence interpretation visibly distinct. Do not present stdout as an
  answer or as a verdict.
- Retain existing redaction, sanitization, evidence readiness, and
  truncation/loss markers accurately and next to the material they qualify.
  Do not expand capture limits or claim unlimited capture.
- The human-readable report is derived from the same completed verified run.
  Presentation does not repair missing results, change verified status, or
  alter JSON/YAML or evaluation semantics.

## Accessibility constraints

These are design conditions informed by WCAG 2.2 AA; they are not a claim of
conformance for any generated or implemented report.

- **WCAG 2.2 SC 1.3.1, Info and Relationships:** Report nesting is represented
  with semantic heading levels and properly associated list/table headers if
  a table is used. Verify the heading outline and semantic relationships in
  the rendered document.
- **WCAG 2.2 SC 1.3.2, Meaningful Sequence:** DOM/source order follows the
  reading order run → skill → case → iteration → details. Verify that
  sequential reading gives this same order.
- **WCAG 2.2 SC 1.4.1, Use of Color:** Status text always spells out the
  classification; color or symbols are supplementary. Verify status remains
  identifiable in monochrome.
- **WCAG 2.2 SC 1.4.10, Reflow; SC 1.4.4, Resize Text:** The semantic linear
  structure has no required wide table or side-by-side baseline/candidate
  layout. At 320 CSS px and at 200% zoom, content remains available without
  horizontal scrolling or loss of facts. Verify both conditions in a browser.
- **WCAG 2.2 SC 2.1.1, Keyboard; SC 2.4.3, Focus Order; SC 2.4.7, Focus
  Visible:** Contents links and native disclosure summaries, if present, work
  by keyboard in reading order and retain a visible focus indicator. Verify
  Tab/Shift+Tab, activation, and focus visibility.
- **WCAG 2.2 SC 2.4.6, Headings and Labels:** Each heading and disclosure
  summary names its skill/case/iteration and purpose. Verify a reader can
  distinguish same-numbered iterations by their surrounding case context.
- **WCAG 2.2 SC 4.1.2, Name, Role, Value:** Any interactive item is a native
  link or disclosure with an accessible name/state. Avoid custom widgets;
  verify the browser accessibility tree exposes the link/disclosure purpose
  and expanded state.

The Markdown rendering remains linear text; HTML must not reorder content
visually against its semantic reading order. No hover-only information,
color-only status, decorative motion, or custom interaction is required.

## Design decision

**Selected:** Summary-first, nested skill → case → iteration hierarchy, with
all five iterations separately visible and per-iteration details available
in the same report. This best supports both quick status scanning and precise
evidence inspection without creating false cross-skill comparison semantics.

**Alternatives not selected:**

- **One large table across skills and iterations:** rejected because many
  columns become hard to scan in Markdown and force horizontal overflow in
  narrow HTML; associations between detailed evidence and a row become
  fragile.
- **One section per iteration in global run order:** rejected because a
  reviewer must repeatedly reconstruct which skill and case an iteration
  belongs to; it weakens grouping and wayfinding.
- **Summary-only with evidence in separate artifact links:** rejected because
  the accepted direction requires full captured answers/evidence in the same
  report and those links would make the report incomplete when moved or
  printed.
- **Collapsed-all-details report:** rejected because essential status and
  comparison would require repeated expansion; evidence may be secondary,
  but each iteration and its result must remain individually findable.

## Open questions

No user-owned design choice remains open for this bounded baseline. Exact
markup and schema details remain governed by ARS-001. A polished branded
report, new aggregation, or additional interactive analysis is explicitly
outside this design's scope and would require separate authorization.
