---
type: Obligation Contract
title: Evaluation case input conformance
description: Defines shared conformance and semantic-preservation guarantees between case producers and the evaluation runner.
tags: [evaluation, input-contracts, obligation-contract]
timestamp: 2026-10-16T00:00:00Z
---

# OC-001 — Evaluation case input conformance

**Priority:** Must (authorized scope)

**Source:** User-authorized runner ownership of both input contracts and the requirement to preserve the distinction between existing agent/runtime and skill formats; user's explicit decision that the new built-in eval interface is OpenCode-only; user clarification that each accepted skill-owned input case must retain stable identity through normalization and remain associated with its outcomes. Source-feature evidence from the Task 1.1 inventory and the pinned Loom sources it identifies establishes current authored feature semantics, not a general legacy-compatibility promise.

**Participants:**
- Case authors or other input producers.
- The evaluation runner.

**Preconditions:**
- A producer submits an evaluation suite or case through the runner-owned built-in evaluation interface.
- The input purports to conform to one of the runner-owned input families.

**Guarantees:**
- The runner applies the conformance contract for the identified input family, not the other family's contract.
- The runner evaluates accepted input according to that family's semantics; acceptance does not silently convert its meaning to the other family.
- Producers can rely on the runner-owned contract as the authority for what input is conforming.
- The contract covers the source features needed to express currently authored agent/runtime cases and skill-owned cases, as enumerated below. If an accepted input uses an optional source feature, its meaning is retained or the input is rejected as unsupported; it is never silently ignored.
- Every accepted skill-owned input case has a stable identity. That identity is preserved through any normalization and remains associated with that case's evaluation outcomes, including each side and the comparison for ablation when applicable. If the source case has no authored ID, the runner may derive an identity; this contract does not prescribe its spelling or derivation rule.
- When one built-in skill-family run contains cases from multiple inputs, the complete submitted child set is checked before any target or judge invocation begins. Each accepted case occurrence is designated by its composite identity `(skill identity, stable case identity)`, which must be unique across that run. Repeated skill identity in different inputs is permitted when the case identities do not collide; a repeated composite identity is rejected rather than merged, overwritten, omitted, or misattributed. The same rule rejects repeated submission of a case-bearing input when it repeats composite identities. This combined-run guarantee does not prescribe input-selection syntax or identity spelling.
- For built-in evaluation of either family, the target invocation and any judge invocation use OpenCode transport. Model/provider selection is made through OpenCode and remains configurable there; GitHub Copilot CLI is outside this built-in contract. This constraint does not apply to the existing `--profile` API path, whose behavior and transport flexibility remain preserved under BR-003.

**Semantic input/output:**
- Input: An input claiming conformance to the agent/runtime suite family or skill-owned case family, together with the requested built-in target/judge transport configuration.
- Output: Either an accepted case/suite that retains its family identity and semantics for evaluation, or an observable rejection indicating the input was not accepted as conforming.

**Family-specific minimum meaning:**

| Family | The accepted input must retain | Conformance boundary |
| --- | --- | --- |
| Agent/runtime suite | Suite identity, version, and case collection; per-case identity and authored agent, execution mode, requirements, prompt, trap, positive expectations, and `must_not` conditions; and any supplied tools, actions, tool-result assertions, output expectations, fixtures, skill reference, or timeout. | The suite must provide its required identity/version/case structure and each case's required identity and execution/assertion inputs. Optional assertion or fixture features, when present, are meaningful inputs, not annotations the runner may discard. An absent optional feature contributes no assertion or execution setup. |
| Skill-owned cases | Skill identity; each case's stable identity, prompt, and positive expectations; any supplied negative expectations/`must_not` conditions and trap; and, when ablation is requested, distinct baseline and candidate outcomes plus the skill-owned comparison. | The case set must identify the skill and provide the required prompt and expectations. A stable identity must be available for every accepted case, whether authored or derived; it remains tied to the case through normalization and outcome attribution. Negative/trap conditions remain skill-family expectations, not agent/runtime assertions. Ablation is not represented as a single ordinary pass/fail case. |

Input syntax remains family-specific. The currently observed skill sources include a raw case array and `cases`/`evals` object envelopes; this specification requires the runner-owned skill contract to represent the skill cases they contain, but does not promise acceptance of every historical wrapper/alias or normalization quirk. Any family selection must be unambiguous before evaluation; the selected family is retained through the result.

**Observed legacy behavior, not an additional compatibility promise:** the diagnostic legacy skill loader infers skill identity from source fields or directory context, normalizes negative conditions and traps, generates normalized IDs/selectors, and rejects duplicate normalized IDs. The agent/runtime source has its own suite/version/name/cases validation. These observations inform contract coverage; they do not promise directory-based discovery, legacy ID spellings, a particular generated-ID rule, selector aliases, or backward compatibility. The stable-identity guarantee above does not require those legacy details.

**Failure semantics:**
- Missing, malformed, or nonconforming input is not evaluated as if it were valid. The exact diagnostic format and whether valid siblings can proceed are unspecified.
- For a combined skill-family run, any duplicate composite case identity in the submitted child set rejects the run before any target or judge invocation begins. No subset of that colliding child set may proceed as though validation had succeeded.
- Ambiguous family identity must not cause silent reinterpretation; the runner rejects it or otherwise makes the selected interpretation explicit before evaluation.
- A family validation/normalization failure is an input rejection, not a behavioral pass, behavioral fail, or non-evidence verdict for an executed case. No invocation may begin for an input rejected as a whole before evaluation.
- Unsupported supplied features must be reported as rejection rather than accepted with that feature silently dropped. Whether valid siblings proceed when another case is invalid remains unspecified.
- A built-in request that selects a non-OpenCode transport for its target or any judge is rejected before any target or judge invocation begins; it is not silently routed to OpenCode or to another transport. The current `--profile` interface is not subject to this built-in rejection rule.

**Invariant:**
- Input-family identity and meaning are preserved from submission through evaluation; acceptance under one family is not evidence of conformance under the other.
- For each accepted skill-owned case, one stable identity continues to designate that case through normalization and is the identity to which its evaluation outcomes are attributed; identity may be authored or derived. Distinct accepted cases must not become indistinguishable in outcome attribution. No particular ID spelling, derivation algorithm, or selector syntax is required.
- Across a combined skill-family run, no two accepted child occurrences share the same `(skill identity, stable case identity)` composite identity. A duplicate is a pre-invocation rejection, not permission to collapse occurrences into one outcome. Different input documents may declare the same skill identity when their cases have distinct stable identities.
- Shared orchestration may share mechanics but does not impose a shared assertion language: agent/runtime execution and runtime/action/tool-result assertion meanings remain distinct from skill prompt/expectation and ablation-comparison meanings.
- No GitHub Copilot CLI target or judge invocation is part of built-in evaluation of either input family; the OpenCode-only restriction does not alter existing profile-mode behavior.

**Verification semantics:**
Submit source-representative inputs through the built-in interface: an agent/runtime case exercising execution mode and supplied runtime/assertion features; skill-owned cases with and without authored IDs, exercising positive and negative/trap expectations; and a paired skill ablation. Observe OpenCode transport for every target and judge, configurable model/provider selection through OpenCode, and no invocation if a non-OpenCode built-in transport is requested. Observe that each accepted skill case retains one stable identity through normalization and that its ordinary or ablation outcomes remain attributable to that same case; observe accepted fields affecting the corresponding family evaluation/result, optional supplied features not being dropped, and family identity remaining explicit. In a combined skill run, submit different inputs with the same skill identity and disjoint case identities and observe all cases accepted and distinct; then submit colliding `(skill identity, stable case identity)` values, including by repeating a case-bearing input, and observe rejection before any target or judge invocation with no child silently merged or executed. Submit malformed required structure, unsupported supplied feature, and ambiguous family cases; observe rejection before invocation and no behavioral verdict for rejected input. Separately exercise the existing `--profile` route and confirm this contract does not narrow its current transport flexibility. Changed or lost skill-case identity, outcome misattribution, cross-family reinterpretation, silent feature loss, execution of rejected input, non-OpenCode built-in invocation, or altered profile behavior attributable to the built-in restriction falsifies this contract. Do not treat a test of legacy directory inference, generated ID spelling, or selector syntax as evidence of a compatibility promise.

## Derived from
- [BR-001 — Accept both input contract families without collapsing semantics](br-001-accept-both-input-contract-families.md).
- [BR-003 — Provide one user-facing evaluation interface](br-003-provide-one-user-facing-evaluation-interface.md).
