---
type: Requirement
title: Provide one user-facing evaluation interface
description: Defines the single public runner interface for inputs, evaluation, and supported output selection.
tags: [evaluation, interface, requirements]
timestamp: 2026-10-16T00:00:00Z
---

# BR-003 — Provide one user-facing evaluation interface

**Priority:** Must (authorized scope)

**Source:** User-authorized statement that all needed to run a case and evaluation should be behind one user-facing interface; user's explicit scope decision that the new built-in eval interface is OpenCode-only; [evaluation format ownership handoff](../../eval-format-ownership-handoff.md), “Intended future direction.”

**Statement:** The runner shall provide one user-facing evaluation interface through which a user can supply the case and evaluation inputs required by the runner-owned contracts, initiate evaluation, and obtain output in a supported format.

**Acceptance criteria:**
- Both input families can be used through the same public runner interface; the user does not need a separate family-specific runner to submit or evaluate them.
- Evaluation initiation and output-format choice are available through that same interface; a separate output-only product surface is not required to obtain the named formats.
- The interface enables the complete case-to-evaluation-to-output path using the inputs and choices required by the runner-owned contracts; a partial surface that requires a separate runner interface to perform one of those steps fails this requirement.
- For runner-owned built-in input-family evaluations, target and judge invocations use the OpenCode transport. Model/provider selection remains configurable through OpenCode; the new built-in contract does not include GitHub Copilot CLI transport.
- A built-in invocation requesting an unsupported transport is rejected before any target or judge invocation begins.
- The pre-existing `--profile` interface remains available with its existing behavior, including its existing transport flexibility. The built-in OpenCode-only constraint does not narrow or replace the profile API path.
- The requirement does not prescribe whether the interface is CLI, GUI, API, or a particular command/argument grammar; those are architectural/design decisions.

**Verification path:** Exercise each input family through the same built-in interface using OpenCode for target and judge, select models/providers through OpenCode, initiate an evaluation, and obtain each supported output format through it. Request an unsupported transport and observe rejection before any invocation. Exercise the existing `--profile` path with its currently supported transport choices and observe no behavior narrowing attributable to the built-in restriction. Falsify if a built-in family requires a non-OpenCode transport, an unsupported transport reaches invocation, OpenCode model/provider selection is unavailable, or the new restriction changes existing profile behavior.

## Derived from
- User-authorized goal for this work.
- [Evaluation format ownership handoff](../../eval-format-ownership-handoff.md).
