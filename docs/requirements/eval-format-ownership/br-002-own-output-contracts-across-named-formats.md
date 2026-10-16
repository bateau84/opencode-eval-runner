---
type: Requirement
title: Own output contracts across named formats
description: Defines the runner's obligation to produce outputs conforming to its JSON, YAML, Markdown, and HTML contracts.
tags: [evaluation, output-contracts, requirements]
timestamp: 2026-10-16T00:00:00Z
---

# BR-002 — Own output contracts across named formats

**Priority:** Must (authorized scope)

**Source:** User-authorized goal; [evaluation format ownership handoff](../../eval-format-ownership-handoff.md), “Intended future direction.”

**Statement:** The runner shall produce evaluation outputs conforming to its owned JSON, YAML, Markdown, and HTML contracts.

**Acceptance criteria:**
- The runner can produce a conforming evaluation output in each of the four named formats; a contract definition without output production does not satisfy this requirement.
- Each format's contract defines a conformance boundary, and a successfully produced output conforms to the selected format's contract and represents the result of the evaluation that produced it.
- **Specification choice:** Formats are available as output alternatives; this requirement does not require one run to emit every format, designate a canonical representation, or define whether HTML is a report or another view.
- A polished report is not required by this baseline: it was expressed as a possibility, not an accepted deliverable.

**Verification path:** Run an evaluation with each named output format requested in turn. For each, verify that output is produced, conforms to its contract, and corresponds to that evaluation's result. Falsify if any format is only documented but not producible, its output violates its contract, or it represents a different result.

## Derived from
- User-authorized goal for this work.
- [Evaluation format ownership handoff](../../eval-format-ownership-handoff.md).
