# Evaluation format ownership handoff

## Purpose and status

This handoff records the user's intended direction for future evaluation input
and output contract ownership. It is a record of intent for later design work,
not an implementation or design specification, and it does not claim that the
future formats or ownership model already exist.

## Current responsibility split

The current runner exposes a generic `eval` command whose project-supplied
`EvalProfile` discovers and normalizes cases, constructs fixtures and
invocations, declares evidence needs, performs project-specific checks, and
defines judge meaning. The runner owns generic orchestration, including
selection, scheduling, attempts/retries, evidence readiness, classification,
artifacts, summaries, and exit status. The current profile API is an
initialized Python object loaded through `module:attribute`; it is not a
file-based input contract. See [`eval-usage.md`](eval-usage.md) and
[`runner/eval_api.py`](../runner/eval_api.py).

The artifact layer currently validates, persists, and verifies versioned JSON
run, case, and paired-evaluation envelopes. It does not interpret project
metadata or project-specific checks. See
[`runner/eval_artifacts.py`](../runner/eval_artifacts.py), which defines
`eval-run/v1`, `eval-artifact/v1`, and `eval-paired-artifact/v1`.

The existing architecture document describes a deliberate split in which
projects/profiles own case discovery and compatibility/normalization, while
the generic engine owns durable artifacts and summaries. It also explicitly
excludes an input-JSON invocation API. See
[`eval-engine-architecture.md`](eval-engine-architecture.md). This reflects
the current documented architecture, not the direction captured below.

## Existing Loom input formats

Loom currently has two distinct evaluation inputs. They have different
provenance and semantics; their similarities should not be taken as evidence
that they are interchangeable.

1. **Agent/runtime evaluation suites** are defined in Loom's TypeScript
   `EvalSuite` / `EvalCase` contract and loaded/validated by
   [`scripts/eval-lib.ts`](https://github.com/bateau84/loom/blob/f0e1a78ce2e2171d9b9a755e5d1f323e02994bab/scripts/eval-lib.ts).
   These are agent-oriented cases with an execution mode and potentially
   runtime/action/tool-result assertions, output expectations, or fixture
   content. The suite version and the kinds of assertion represent behavior
   and observation semantics specific to this suite.
2. **Skill-owned evaluation cases** are read from skill evaluation JSON files
   and loaded and normalized by
   [`scripts/run-evals-legacy.py`](https://github.com/bateau84/loom/blob/f0e1a78ce2e2171d9b9a755e5d1f323e02994bab/scripts/run-evals-legacy.py).
   The loader accepts a JSON array or an object containing cases/evals, and
   normalizes skill-owned prompts, expectations, optional negative
   expectations/must-not conditions, and trap information into its own
   runtime skill-ablation path. These inputs express skill-oriented behavioral
   expectations and their baseline/candidate comparison context, not the
   agent-suite assertion model.

These links point to Loom commit
[`f0e1a78ce2e2171d9b9a755e5d1f323e02994bab`](https://github.com/bateau84/loom/commit/f0e1a78ce2e2171d9b9a755e5d1f323e02994bab),
on branch `functionality-anchor-requirements-coherance` (from the verified
`origin` remote, `ssh://git@github.com/bateau84/loom.git`). The input formats
are summarized only to establish the current situation; this document does not
define either format or prescribe a conversion between them.

## Intended future direction

The user's intended direction is for **`opencode-eval-runner` to own both
existing input contracts**—the agent/runtime evaluation suites and the
skill-evaluation cases—and to own **evaluation output contracts in multiple
formats**, including JSON, YAML, Markdown, and HTML. The user also expressed
interest in possibly delivering a polished report.

This is future product direction for design, not authorization to implement
schemas, change current runtime behavior, or decide how inputs and outputs
should be represented. The intent is ownership of both input families and
output formats; it does not imply that their distinct behavioral semantics
should be collapsed into one meaning.

## Unresolved design questions

The following remain open and must be decided in later design work:

- What exact fields, semantics, versions, compatibility guarantees, and
  migration expectations apply to each input contract?
- How should the distinct agent/runtime-suite and skill-evaluation semantics
  be represented while both are owned by the runner?
- Should there be a canonical internal representation with format-specific
  renderers, or another relationship between the input and output contracts?
- What are the exact output contents and compatibility expectations for JSON,
  YAML, and Markdown, and what should HTML render or enable?
- What does the proposed report need to communicate, for whom, and is it a
  rendered output format or a separate deliverable?
- Which current Loom/runner responsibilities move, when, and how are existing
  inputs and outputs migrated or kept compatible during that ownership change?

No answers to these questions are implied here.

## Follow-up

The current runner architecture documentation describes the old split:
project profiles own discovery and normalization, and runner artifacts are
generic durable JSON. Later design work must reconcile that architecture and
its related documentation with the user's intended runner ownership of both
input families and multi-format outputs. This handoff does not revise those
documents or settle the new architecture.
