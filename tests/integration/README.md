# Real-runtime capture boundary probe

This is a diagnostic experiment against the **PR checkout**, not a second Loom
observer or a synthetic signed producer. It runs the unchanged pinned OpenCode
image, its original `container.invoke.invoke_opencode`, and the PR's host-side
`ObserverCapture` importer. It does not run the complete host CLI or Loom's final
assertion consumer. **A passing diagnostic is not handoff acceptance.**

```sh
docker pull ghcr.io/bateau84/opencode-eval-runner@sha256:68ef7322c75aede0e8cc76d0e3531e8b82dd417bbb5e5100264a89eab7fe8627
python3 tests/integration/run_capture_probe.py --output capture-probe-results
```

By default, exit 1 means a diagnostic expectation failed. Exit 4 means the
diagnostics ran as expected but this old image's capture remains BLOCKED.
There is still no success exit for end-to-end capture from this diagnostic.

CI runs the same experiment as an explicit **negative control**:

```sh
python3 tests/integration/run_capture_probe.py --expect-unsupported-baseline --output capture-probe-results
```

In this mode, exit 0 means all 12 required checks passed on the exact pinned old
image, including missing-producer rejection, forged-record rejection and no
eligible capture. Any missing/failed check, unexpected capture eligibility,
wrong image, or changed acceptance claim exits 1. This does not use
`continue-on-error` or ignore arbitrary exit codes.

The summary keeps `handoff_acceptance: "BLOCKED"` and
`independent_code_approval: false`. Its separate `ci_check` identifies the
old-image rejection regression; it is not an evidence-admission field.
`Observer boundary integration` preserves the raw results as before. The
`Protected runtime channel` workflow tests positive capture through the new
isolated profile. Full Loom handoff acceptance and independent review remain
separate requirements. Earlier non-passing runs and artifacts are not rewritten.

## Isolation

Each variant gets a fresh non-root Docker container, disposable HOME/XDG state,
/tmp and workspace tmpfs, no credential/database seeds, and `--network none`.
A deterministic OpenAI-compatible HTTP fixture runs only on that container's
loopback interface; no real provider is contacted. The original immutable image
is pulled and inspected, not rebuilt. The random verifier key lives on the CI
host outside mounted trees, is never given to any producer, and is deleted after
each variant. No signed positive evidence is manufactured.

## Cases

Four variants combine diagnostic hooks on/off with forged-sidecar injection
on/off. All execute one native sentinel call, then a Code Mode script that:

1. Starts two identical calls concurrently and checks their distinct results;
   the fixture deliberately finishes the second call first.
2. Receives a domain-denial JSON string, catches a thrown error, and checks a
   return changed by a deliberately later hook. It discards the original values
   and returns only `script-output-only`.
3. Calls a fixture tool that, in forgery variants, writes a lookalike observer
   envelope with an invalid MAC to the real capture mount. Its return stays the
   same regardless of the injection.

Unsigned logs inside the fixture tools provide a **test oracle**, and separate
read-only hook callbacks record the actual public event fields. Neither log is
submitted to the importer as trustworthy result evidence. The output-changing
hook is a separate deliberate fixture challenge, present with logging both on
and off. Script assertions show what this controlled fixture received; they are
not a permitted production evidence fallback.

## Boundary observations

The first pinned-image execution demonstrated:

- Concurrent identical inner calls share `id: fixture-call-2` with their parent,
  even though results complete in the order `CALL-2`, then `CALL-1`.
- Input object references were distinct and persisted across successful hooks in
  this execution. That is a candidate to investigate, **not an agreed supported
  correlation contract**, and it does not supply missing error terminals.
- The nested throwing tool had an `execute.before` record but no
  `execute.after` terminal, even though the script caught the real exception and
  completed. Missing terminals must stay non-evidence.
- The early after-hook saw `BEFORE-MUTATION`; a later hook changed it to
  `FINAL-RETURN`, which the Code Mode script received. A generic after-hook is
  therefore not inherently the final-return boundary.
- Forged streams were rejected, while the fixture's tool inputs/outcomes and
  script result were unchanged. Without a real producer, ordinary runs were
  explicitly unavailable, never accepted.

The first run's only harness-check failure was version formatting: the actual
binary reports `opencode v2.0.18`, not just `2.0.18`. The check now accepts those
exact two representations and retains the raw version in every artifact. The
original first-run artifacts are not rewritten.

## Producer coordination

Loom's published branch was inspected at
`6e255092388a57f141e609fee954cb7ae5977d4b`. Its existing deterministic provider and
`lifecycle-delay-plugin.ts` supplied the fixture patterns; no usable observer
contract was present in the inspected code. This experiment does not pretend to
run a still-unpublished Worker implementation.

Before changing the exporter contract, the producer owner must demonstrate a
boundary with unique execution correlation, actual error terminals, and final
returns after transformations, plus a channel evaluated code cannot forge.
**Signing is only a proposal.** These probes do not establish protected signer
feasibility; the exporter must adapt to the demonstrated producer boundary.
Independent code review, guarded infrastructure readiness, and full handoff
acceptance remain separate decisions. No merge is authorized by this experiment.
