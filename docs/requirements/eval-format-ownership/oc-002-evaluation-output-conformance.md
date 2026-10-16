---
type: Obligation Contract
title: Evaluation output conformance
description: Defines shared conformance and result-preservation guarantees between the evaluation runner and output consumers.
tags: [evaluation, output-contracts, obligation-contract]
timestamp: 2026-10-16T00:00:00Z
---

# OC-002 — Evaluation output conformance

**Priority:** Must (authorized scope)

**Source:** User-authorized runner ownership of output contracts in JSON, YAML, Markdown, and HTML through one user-facing interface; approved ARD-001 common-result and integrity boundaries; designer guidance recorded in the approved plan that Markdown/HTML are accessible views of the same result and a polished report is optional; user's subsequent request for human-readable Markdown/HTML results and explicit approval of a readable narrative with captured runtime evidence retained in supporting details, subject to existing capture, sanitization/redaction, and truncation behavior.

**Participants:**
- The evaluation runner, which produces outputs.
- Output consumers, including users and tools that read the selected format.

**Preconditions:**
- A completed evaluation has produced a family-owned result for every planned case-iteration job, and the result is available to the runner for verification and rendering.
- A supported output format is requested through the runner’s user-facing evaluation interface.

An orchestration/preparation error that terminates a job before its family-owned result exists, and a planned job that is not run, do not satisfy this precondition. This contract does not require public-format output for such a run; it does require that they not be represented by fabricated family outcomes or reported as a successfully produced conforming evaluation output.

**Guarantees:**
- The runner produces output conforming to the contract for the requested format.
- A consumer can rely on the selected format's runner-owned contract to interpret the produced output.
- The output represents the result of that evaluation rather than a different or fabricated result.
- For one completed, verified evaluation, each separately requested format represents the same common result facts and applicable family-specific outcomes; selecting a format changes representation only.
- A result's `pass`, `fail`, and `non-evidence` classifications remain distinct in every format. Missing or insufficient evidence is not rendered as a behavioral failure or success, and an observed behavioral failure is not hidden as non-evidence.
- In Markdown and HTML, a consumer can understand the run outcome and applicable case results from readable status text and summaries without decoding raw structured data. Applicable family-specific outcomes remain understandable, including skill baseline/candidate comparison and agent/runtime authored assertion outcomes.
- Captured supporting evidence and attempt detail remain associated with the relevant case and available to consumers in clearly identified details in the same report. Existing sanitization/redaction and truncation metadata remain accurate; rendering adds no omission or truncation for presentation convenience. This does not require unlimited runtime-output capture or bypass existing capture/sanitization behavior.

**Semantic input/output:**
- Input: The verified result of a completed evaluation meeting the preconditions above and a requested supported output format.
- Output: A conforming representation of that evaluation result in the requested format.

**Facts every format must represent:**
- Evaluation/run identity and the identity of each represented case.
- For a skill-owned case, the case identity is the stable identity preserved for that accepted input case under [OC-001](oc-001-evaluation-case-input-conformance.md); all represented outcomes for that case, including ablation sides and comparison when applicable, remain associated with it. This does not prescribe ID spelling or how an identity absent from the source is derived.
- Input-family identity for each case/result, preserving agent/runtime versus skill-owned provenance.
- Per-case classification, including the distinction among pass, fail, and non-evidence; any run-level aggregate must not erase the per-case outcomes.
- Attempt/execution provenance necessary to distinguish the evaluated work from a different run, including retries when they occurred.
- The family-owned outcome needed to understand the verdict: agent/runtime execution mode and applicable authored assertion outcomes for agent/runtime cases; skill expectations and, for ablation, both baseline and candidate outcomes and the skill-owned comparison.

Each format may choose its own organization and syntax, but omitting, contradicting, or flattening one of these applicable facts is nonconforming. This contract does not settle additional report content, redaction, or presentation beyond these facts and the accessibility requirements below.

**Format boundaries:**
- **JSON:** machine-readable representation conforming to its runner-owned output contract. Existing integrity-checked `eval-run/v1`, `eval-artifact/v1`, and paired-artifact v1 meanings/integrity are not reinterpreted or weakened. The existence of those persisted envelopes does not itself establish that they are the public JSON output contract or that their historical shape is externally compatible.
- **YAML:** machine-readable representation conforming to its runner-owned output contract and preserving the same applicable facts as JSON.
- **Markdown:** readable summary of the same result, with meaningful headings and document order; status and other distinctions are stated in text and are not conveyed by color or visual styling alone. Captured runtime evidence remains available as clearly identified supporting detail, with existing sanitization/redaction and truncation metadata preserved.
- **HTML:** readable summary of the same result, with meaningful semantic structure and reading order; status and other distinctions are stated in text and are not conveyed by color or visual styling alone. Captured runtime evidence remains available as clearly identified supporting detail, with existing sanitization/redaction and truncation metadata preserved. Any interactive content, if present, has a keyboard-operable path. A polished report or any particular interaction model is not required by this baseline.

JSON and YAML syntax/schema/version details and exact Markdown/HTML markup are realization details for the architect, not additional semantic promises in this contract. The required user-visible fact coverage above is binding independently of those choices.

**Failure semantics:**
- If the runner cannot produce a conforming output, it does not report successful production of that output. Exact error representation and partial-output cleanup are unspecified.
- An unsupported/ambiguous format request or an invalid/unverified source result does not yield a successful output. Output production failure is not an evaluation behavioral verdict and does not change the source result.
- A run containing a planned job with no family-owned result because of a pre-result terminal error or not-run disposition is outside the successful-render precondition; the runner does not claim a conforming output for that run. No family result or behavioral classification may be fabricated to make it renderable.
- The formats are selectable alternatives; this contract does not require simultaneous production. For same-result parity, the same completed, verified evaluation must be the source for each separately requested representation; separate evaluations do not establish parity.

**Invariant:**
- Format selection changes representation, not which evaluation result is represented.
- Rendering preserves all applicable common and family-specific facts, verdicts, and distinctions, including non-evidence versus behavioral failure and both sides plus comparison for skill ablation.
- Markdown/HTML must not rely on color or visual treatment alone to communicate result distinctions. If HTML interactions are added, they remain keyboard operable.
- Readable summaries do not replace or alter the underlying result; captured runtime stdout/evidence and required attempt details remain available as supporting details, with existing sanitization/redaction and truncation state accurately represented. Rendering adds no presentation-only omission or truncation; no unlimited-capture promise is made.

**Verification semantics:**
Complete and verify one evaluation from each input family, including skill-owned input cases with authored and derived identities and one skill ablation; from the same completed verified result, request JSON, YAML, Markdown, and HTML separately through the public interface. Compare each representation to that result for run/case identity, family, classification (including non-evidence), attempts, applicable agent/runtime assertion outcomes, and skill baseline/candidate outcomes/comparison. Confirm the stable identity of each skill-owned case matches OC-001 and remains associated with its outcomes in every format. For Markdown and HTML, verify that readers can understand run and case outcomes and applicable family-specific results without decoding raw serialized data, and that all captured runtime evidence and required attempt detail remain available and correctly associated in supporting details, with existing sanitization/redaction and truncation metadata preserved. Rendering must not add presentation-only omission or truncation; this does not require unlimited evidence capture. Validate the requested syntax/format; inspect generated Markdown/HTML for meaningful structure and reading order, non-color status cues, and keyboard operation of any HTML interaction. Also request an unsupported format and attempt output from an invalid/unverified result; neither may be reported as successful output. Any absent or changed applicable fact, identity discontinuity or outcome misattribution, false success, format-dependent verdict, unreadable summary, missing captured evidence, inaccurate evidence metadata, inaccessible status distinction, or inaccessible interaction falsifies this contract. This verifies output semantics, not historical compatibility with any particular v1 consumer.

## Derived from
- [BR-002 — Own output contracts across named formats](br-002-own-output-contracts-across-named-formats.md).
- [BR-004 — Present readable Markdown and HTML results](br-004-present-readable-markdown-and-html-results.md).
- [BR-003 — Provide one user-facing evaluation interface](br-003-provide-one-user-facing-evaluation-interface.md).
