# Cosign provenance for approved normal-invoke images and results

## Security goal

Cosign authenticates **approved bytes and signer identity**. It does not make an
observation truthful when evaluated code shares the collector's authority.

The trusted signing path is deliberately separate from pull-request CI:

```text
reviewed PR commit
  -> manual default-branch workflow_dispatch
  -> unprivileged rebuild from that exact commit
  -> immutable image publication
  -> unprivileged provider-free verification
  -> protected release-signing environment approval
  -> Cosign image + finalized-result signatures
```

PR pushes and green PR workflows cannot automatically request a signature.

## Why PR artifacts are not signed directly

A PR controls its source files, Containerfile, test scripts, and workflow inputs.
A default-branch signer that automatically consumes successful PR artifacts would
authenticate attacker-controlled bytes after only self-produced checks.

The signer therefore does **not** use `workflow_run` and does not consume
`runtime-publication-*` or `local-runtime-*` PR artifacts.

Instead, an authorized operator manually dispatches the trusted default-branch
workflow with:

- the reviewed 40-hex source commit;
- the PR number that currently has that exact head.

The trusted workflow verifies the PR head, checks out the selected commit in an
unprivileged build job, rebuilds the runtime from pinned OpenCode source, and
reruns the provider-free runtime, eval-live compatibility, and delegated-session
probes.

## Privilege separation

The workflow has four jobs.

### build

- runs only when the workflow definition itself is invoked from `refs/heads/main`;
- has read-only repository permission;
- validates the selected commit is the current head of the supplied PR;
- rebuilds OpenCode from pinned upstream source plus the reviewed downstream
  patch;
- runs the source tests;
- saves image bytes as an artifact;
- has no package-write or OIDC authority.

### publish

- receives only the image archive;
- has package-write permission but no OIDC token;
- does not check out or execute source code;
- publishes a commit/run-scoped image and returns its immutable digest.

### verify

- has read-only permission;
- checks out the exact selected commit;
- pulls the immutable digest;
- verifies revision/runtime labels;
- runs the real normal-invoke runtime probe, eval-live compatibility probe, and
  delegated-session probe;
- uploads the finalized diagnostic evidence;
- has no package-write or OIDC authority.

### sign

- depends on successful build, publish, and verify;
- uses the GitHub environment **`release-signing`**;
- repository configuration must protect that environment with required
  reviewers;
- has OIDC and package-write permission;
- checks out no source and executes no selected-commit scripts;
- validates only fixed result shapes from the verified artifacts;
- signs the exact immutable image and a separately finalized result JSON.

Thus a PR push cannot obtain signing authority merely by making its own tests
green. The final approval occurs after rebuild and verification.

## Signed result binding

`eval-result.json` version 2 contains:

- reviewed source commit;
- PR number;
- trusted signing workflow run ID;
- exact immutable image digest;
- SHA-256 digests of the finalized compatibility, delegated-session, and runtime
  probe summaries;
- their pass states;
- explicit `protected_capture_accepted: false`;
- explicit `in_process_plugin_protection: "unsupported"`.

The signature therefore authenticates the diagnostic result without upgrading it
into a protected-capture claim.

## Expected signer identity

When invoked from the protected default-branch workflow, the expected identity is:

```text
https://github.com/bateau84/opencode-eval-runner/.github/workflows/sign-normal-invoke-evidence.yml@refs/heads/main
```

Issuer:

```text
https://token.actions.githubusercontent.com
```

The workflow verifies both the image signature and blob bundle immediately after
creation.

## Required repository configuration

Before this signing path is treated as release authority:

1. merge/install the workflow on the default branch;
2. create the `release-signing` GitHub environment;
3. configure required reviewers for that environment;
4. limit who may deploy to it according to repository policy.

Without those environment protections, the YAML alone is not a human approval
gate.

## Current PR limitation

PR #41 is intentionally unmerged. The trusted workflow therefore cannot yet be
invoked from the default branch, and no valid release-signing environment run can
be produced from this PR alone.

That limitation is intentional: producing a keyless signature from a PR-controlled
copy of the workflow would defeat the security boundary this design is meant to
provide.


## Final signer admission

Before the protected `release-signing` job creates either signature, it validates
the downloaded summaries against the immutable image selected for that run:

- eval-live compatibility: kind `eval-live-invoke-compatibility`, version 2,
  matching `image`, passed, and diagnostic/non-evidence status;
- delegated-session proof: kind `delegated-session-normal-invoke`, version 1,
  matching `image`, and passed;
- runtime seam: kind `normal-invoke-runtime-seam-probe`, version 2, matching
  `image`, matching reviewed source revision, seam passed, handoff still
  `BLOCKED`, and independent-code-approval still false.

The signing job authenticates to GHCR with its package-scoped `GITHUB_TOKEN`
before `cosign sign`. GitHub OIDC provides the keyless certificate identity; it
does not replace registry authentication for publishing the OCI signature.
