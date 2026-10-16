# Evaluation format ownership requirements

## Scope and status

This bundle captures the authorized direction that `opencode-eval-runner` own
contracts for both existing Loom evaluation input families and for evaluation
outputs in JSON, YAML, Markdown, and HTML. The user's explicit scope decision
limits the new runner-owned built-in eval interface to OpenCode transport for
target and judge, with model/provider selection configurable through OpenCode;
it excludes GitHub Copilot CLI transport from that built-in contract. The
existing `--profile` API path and its current transport flexibility remain
preserved. This is a requirements baseline, not an architecture or
implementation specification. Concrete schemas/markup, historical
compatibility, migration, and report content remain unsettled as listed below.

## Requirements

- [BR-001 — Accept both input contract families without collapsing semantics](br-001-accept-both-input-contract-families.md)
- [BR-002 — Own output contracts across named formats](br-002-own-output-contracts-across-named-formats.md)
- [BR-003 — Provide one user-facing evaluation interface](br-003-provide-one-user-facing-evaluation-interface.md)

## Scenarios and contracts

No quality scenario is warranted: no measurable quality target or condition
was authorized. Two obligation contracts are included because case authors
and output consumers rely on correctness-sensitive runner-owned format seams.

- [OC-001 — Evaluation case input conformance](oc-001-evaluation-case-input-conformance.md)
- [OC-002 — Evaluation output conformance](oc-002-evaluation-output-conformance.md)
- [Bundle change log](log.md)

## Provenance and reconciliation

Source: [Evaluation format ownership handoff](../../eval-format-ownership-handoff.md),
especially “Intended future direction” and “Unresolved design questions.” The
user-authorized goal for this requirements phase repeats that direction and
requires preserving the two input families' semantic distinction. Amendment
source: the user explicitly answered “yes, opencode only” when asked whether
the new built-in eval supports OpenCode-only or also the separate GitHub
Copilot CLI transport. The user clarified that the desired single image
contains OpenCode and model/provider selection is through OpenCode. This
decision constrains only new built-in evaluation and explicitly preserves
existing `--profile` behavior, including current transport flexibility.

The [current engine architecture](../../eval-engine-architecture.md) and
implementation describe the previous responsibility split. They are
reconciliation evidence, not sources that narrow these requirements.

## Reconciliation amendment

- **Resolved scope / source: user:** New built-in evaluation of either input
  family requires OpenCode for target and judge; provider/model choice remains
  configurable through OpenCode. GitHub Copilot CLI transport is not part of
  this built-in contract. Requests for another transport must be rejected
  before invocation.
- **Preserved compatibility boundary / source: user:** Existing `--profile`
  behavior remains unchanged, including any transport flexibility it currently
  supports. The new built-in transport restriction does not apply to that path.
- **Resolved / aligned:** BR-003 and OC-001 specify OpenCode-only transport for
  built-in target/judge invocations, and ARS-001 §89 aligns with that scope.
  The prior architecture/specification conflict about built-in Copilot
  transport is resolved; it does not change the separate preservation of
  existing `--profile` behavior.

## Reconciliation findings

- **Aligned / superseded prior architecture:** `eval-engine-architecture.md`
  §§2, 3.2, 10, and 15 describe the earlier profile-owned input and
  JSON-artifact responsibility split. The current [ARD-001](../../architecture/eval-format-ownership/design/ard-001-runner-owned-input-and-output-contracts.md)
  assigns the two runner-owned input families and four output representations
  to the runner while retaining the generic engine's common mechanics;
  [ARS-001](../../architecture/eval-format-ownership/specifications/ars-001-runner-eval-contract.md)
  defines the corresponding interface and output contract. The earlier
  responsibility boundaries are therefore not an unresolved conflict with
  this requirements bundle. This does not establish historical compatibility
  beyond the explicit preservation of the existing `--profile` path.
- **Aligned evidence:** The handoff's commit-pinned Loom sources confirm two
  distinct inputs: `EvalSuite`/`EvalCase` with suite version and execution plus
  agent/runtime assertions; and skill-owned cases loaded from arrays or
  `cases`/`evals` objects with skill-oriented expectations and optional
  negative/trap semantics. The sources describe the current Loom formats, not
  future runner schemas or compatibility promises.
- **Task 1.2 contract detail:** [OC-001](oc-001-evaluation-case-input-conformance.md)
  enumerates the source features that accepted runner-owned contracts must
  preserve, including stable identity for each accepted skill-owned case across
  normalization and attribution of its outcomes. The identity may be authored
  or derived; legacy spelling, generation rules, selector aliases, inference,
  and wrapper quirks are not compatibility promises. [OC-002](oc-002-evaluation-output-conformance.md)
  specifies common and family-owned facts every output must retain, including
  tri-state classification and paired-ablation outcomes, as well as selection,
  failure, accessible Markdown/HTML behavior, and preservation of the
  OC-001 skill-case identity alongside its outcomes. These details do not define
  schemas, wire fields, CLI grammar, or compatibility with external consumers.
- **Downstream-only / not adopted:** Current code has versioned JSON
  persistence and current docs mention report/error helpers. Neither establishes
  user-authorized YAML/Markdown/HTML contents, polished-report requirements, or
  their compatibility guarantees.
- **Aligned / output eligibility:** OC-002 excludes runs with a pre-result
  terminal error or not-run planned job from successful conforming output.
  ARS-001 §§303, 407, and 428 make the same distinction: such a job has no
  fabricated family result or classification, and execute/render cannot claim
  successful conforming output. No architecture/specification reconciliation
  remains open on this eligibility boundary; completed, verified eligible runs
  retain the output guarantees in OC-002.
- **OKF discovery:** `okf-mcp` indexes this populated bundle, including BR-001,
  BR-002, BR-003, OC-001, OC-002, this index, and the bundle log. The index is
  maintained alongside those documents; the earlier claim that the repository
  had no discoverable OKF documents is stale.

## Open decisions

| Decision | Owner | Blocks |
| --- | --- | --- |
| Must historical variants beyond the existing source formats remain accepted unchanged, including legacy inference/wrapper/ID spelling/generated-ID/selector-alias behavior? | User | Blocks historical-compatibility promises only; source feature coverage and stable identity preservation do not depend on it. |
| Does the user accept or authorize the historical image-transfer/egress behavior identified during remediation? | User | Blocks closure or acceptance of that historical egress question only; it does not change the input/output requirements in this bundle. |
| Backward compatibility, migration path, and timing for current profile inputs and runner outputs | User | Blocks migration/compatibility promises and any removal/change to those current surfaces; does not block new ownership paths while preserving current v1 integrity/meaning. |
| Exact serialization/schema/version/markup and any additional output content beyond the common facts in OC-002 | Architect for structural realization; user for material user-facing content beyond the stated baseline | Blocks detailed format specification beyond the semantic boundaries in OC-002, not production of all four formats. |
| Whether formats are selectable or emitted together | Resolved as selectable alternatives by BR-002/OC-002; simultaneous output is not required | Not blocking. |
| Built-in target/judge transport and model/provider selection | Resolved by the user's explicit decision and captured in BR-003/OC-001: OpenCode transport only; selection remains configurable through OpenCode. Existing `--profile` transport behavior is preserved. ARS-001 §89 is aligned with this scope. | Requirement and architecture alignment are resolved; no further reconciliation is pending for this decision. |
| What HTML represents beyond an accessible view of the same facts or enables interactively | User for report/product meaning; architect realizes accepted meaning | Blocks specific HTML/report content or interaction claims only; any introduced interaction must be keyboard operable. |
| Is a polished report required; if so, for whom, what must it communicate, and is it distinct from HTML? | User | Yes, report scope only. |
| Whether there is a canonical representation and the technical relationship between inputs and outputs | Architect, unless the user has a product preference | Blocks architecture, not these requirements. |

These questions do not block the ownership, input acceptance, output production,
or shared-interface requirements above. They must be resolved before claiming
historical compatibility, a specific report, migration behavior, or serialization
and presentation details beyond the semantic boundaries in the OCs.
