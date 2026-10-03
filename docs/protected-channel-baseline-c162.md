# Preserved protected-channel baseline (2026-10-03)

This records the prior version-3 connection proof. It is not a claim that these
older images implement the new mandatory supervisor-receipt profile/version 4.
The later collector image must be obtained from its own completed publication run.

- Implementation: `c1629415a814476f7b62f159530e7edd29fde738`.
- Documentation checkpoint: `9153cc30c6d80deac15dbe284408d7bffa17ff38`.
- Protected connection run: https://github.com/bateau84/opencode-eval-runner/actions/runs/37112938698
- Artifact: https://github.com/bateau84/opencode-eval-runner/actions/runs/37112938698/artifacts/11270611290
- Artifact ZIP SHA-256: `1bff745c9db5f9921f93add9eb4613c1262b38f985420b0fef0b91747250b6ed`.
- Result: all 33 restricted-profile integration checks passed. This used the runner's isolated fixture tools, not Loom's full plugin or actual assertion consumer.
- Protected runtime: `ghcr.io/bateau84/opencode-eval-runner@sha256:658f4a53fba33c74f653abb613a6f38f82ec763891bc7f8c09ce1c7b7b19483d`.
- Fixture tools: `ghcr.io/bateau84/opencode-eval-runner@sha256:1e1c58ac92edace961246ce577bb293c2cbcc57fabdb282aa93b6f4c481ffac0`.

The historical run compared actual runtime records with an independently recorded
tool-server test oracle, exercised the public CLI, tested target file/process
access and fake outputs, replay/deletion/reordering, capture I/O failure, input
snapshot integrity and redaction. A deletion with recomputed inline checksum was
rejected by source-sequence/accounting checks. The current receipt extension adds
a separate trusted digest/length comparison so result edits with recomputed inline
checksums are rejected too. This does not expand protection to a malicious host
that controls both paths.

No historical artifact or observation has been rewritten. Independent review,
full Loom composition, native/delegated sessions, production redaction and image/
artifact signing remained open at this checkpoint.

## Loom script routing carried forward

Adapt `scripts/run-evals.py` only for cases explicitly declaring the supported
profile. The `observe` command is a deterministic single-program transport, not
a replacement for normal multi-turn `invoke`. Keep result artifacts on the
trusted host. Pin actual adapter/producer/consumer bytes and preserve
`scripts/test_eval_observer_image.py` and its original fixtures. See the current
[handoff](loom-protected-channel-handoff.md) for version-4 admission and actual
Loom execution-isolation work.


## Contract erratum and current compatibility direction

The tested `c1629415...` implementation used runtime events
`opencode-local-observation/v1`, wire `opencode-protected-observation/v2`, and
projection version **3**. Earlier prose describing that implementation as wire
v1 / projection v2 was stale. This erratum does not rewrite its historical
artifact.

The normal Loom migration target is now explicitly the existing
`bun run eval:live -> scripts/run-evals.py -> opencode-eval-runner invoke` path.
The restricted `observe` profile remains supplemental and must not replace
normal Loom host/session semantics. See
[host-semantics feasibility](loom-host-semantics-feasibility.md).
