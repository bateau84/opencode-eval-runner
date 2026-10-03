# Cosign provenance for normal-invoke eval images and results

## Security goal

Cosign authenticates **approved bytes and signer identity**. It does not make an
observation truthful when evaluated code shares the collector's authority.

The signing design therefore follows protected collection rather than replacing
it:

```text
unprivileged PR build/test
  -> immutable image + finalized diagnostic evidence
  -> trusted default-branch workflow_run signer
       -> Cosign image signature
       -> Cosign signed finalized result JSON
```

## Why signing is not in the PR build job

A pull-request workflow definition is PR-controlled. Giving that workflow OIDC
or a long-lived signing key would allow a modified PR workflow to request
signatures for attacker-chosen material.

`.github/workflows/sign-normal-invoke-evidence.yml` is instead triggered by
`workflow_run`. GitHub loads that signer definition from the repository's
**default branch**.

The signer:

1. receives no repository checkout;
2. executes no PR-provided script or image;
3. verifies the triggering workflow's exact Git blob SHA against
   `EXPECTED_BUILD_WORKFLOW_BLOB`;
4. downloads only publication/verification artifacts from the completed run;
5. independently pulls the immutable image digest and verifies its
   `org.opencontainers.image.revision` and runtime-version labels;
6. requires the eval-live, delegated-session, and runtime diagnostic summaries
   to have their expected successful/non-evidence state;
7. signs the image digest with GitHub OIDC;
8. creates and signs a separate finalized result JSON.

Changing the build workflow therefore requires an explicit reviewed update to
the trusted signer's allowed workflow blob.

## Signed result binding

`eval-result.json` contains:

- source commit;
- triggering workflow run ID and attempt;
- exact immutable image digest;
- reviewed build-workflow blob SHA;
- SHA-256 digests of the finalized compatibility, delegated-session, and runtime
  probe summaries;
- their pass states;
- explicit `protected_capture_accepted: false`;
- explicit `in_process_plugin_protection: "unsupported"`.

The signature cannot silently upgrade diagnostic evidence into protected
evidence.

## Expected signer identity

The verifier derives the expected identity from the trusted signer workflow:

```text
https://github.com/bateau84/opencode-eval-runner/.github/workflows/sign-normal-invoke-evidence.yml@refs/heads/main
```

Issuer:

```text
https://token.actions.githubusercontent.com
```

The workflow also verifies both signatures immediately after creation.

## Current PR limitation

PR #41 is intentionally **not merged**. A `workflow_run` signer added by this PR
does not become a trusted default-branch workflow until that workflow file is
installed on the default branch.

Therefore the current experimental PR image can be published and tested, but it
must remain **unsigned by the trusted signer**. Producing a signature from a
PR-controlled copy of the signer would defeat the purpose of this design.

This is an activation dependency created by the no-merge constraint, not an
implementation gap to paper over with a weaker signing path.
