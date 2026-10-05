# Provisional trusted computing boundary

Status: **Wave-1 planning artifact. Gate 1 PASS; runtime properties remain unproven.**

This TCB is the candidate boundary accepted for Gate-1 design readiness. It is not a claim that the boundary is already effective.

## Trusted components

For the bounded experiment, the proposed trusted domain is:

1. host `opencode-eval-runner` launcher;
2. host collector, scope accountant, evidence-safety projector, and final evidence writer;
3. host kernel and selected OCI engine only to the extent required to enforce the declared container/process boundary;
4. **stock OpenCode v2.0.23** core runtime;
5. a runner-owned bridge plugin loaded by stock OpenCode through its supported plugin API;
6. runner-owned bridge protocol framing/correlation code.

OpenCode itself is immutable. No patched binary or source fork belongs to the TCB.

## Untrusted/evaluated authority

Treat as untrusted for evidence authority:

- the complete Loom plugin module at `149406d`;
- Loom dependencies;
- Loom tool handlers, hooks, transforms, workflow/authorization/OQ logic;
- the Loom plugin's direct filesystem, Git, dashboard, and subprocess activity;
- processes spawned by Loom;
- model-produced data;
- arbitrary tool/product return values;
- **commands spawned by stock OpenCode's built-in shell tool**;
- the writable evaluated workspace;
- any external plugin not explicitly admitted as trusted or isolated equivalently.

The last two items are load-bearing. Isolating Loom alone does not establish TRUST-001 if an evaluated shell command or another plugin can control the bridge/core/collector.

## Proposed topology

```text
host opencode-eval-runner
  ├─ trusted collector / scope accounting / safety / writer
  │
  ├─ stock OpenCode v2.0.23 OCI domain
  │    ├─ OpenCode core
  │    ├─ runner-owned trusted bridge plugin
  │    └─ untrusted built-in tool subprocesses (e.g. shell)
  │
  └─ isolated Loom OCI domain
       ├─ Loom module + dependencies
       ├─ Loom callbacks/tool handlers
       ├─ Loom local runtime state
       └─ Loom-spawned children
```

The stock OpenCode domain is therefore a **mixed-authority OS domain**. The Gate 1 review requires later proof that the proposed channel and mount controls prevent its untrusted subprocesses from escalating into evidence authority.

Two channels have different TCB meaning:

- **evidence channel:** trusted bridge → host collector only; this is the sole candidate observation ingress with evidence authority;
- **capability channel:** trusted bridge ↔ isolated Loom; payloads are untrusted product data and have no direct evidence-write authority, while trusted transport admission/correlation must bind them to the admitted Loom generation.

They must not share accepted descriptors, listener paths, authentication material, or collector-readable evidence framing.

## Evidence authority

Only the trusted side may establish:

- effective admitted registration identity;
- trusted collector sequence;
- authoritative runtime Session/message/call facts obtained from stock OpenCode;
- runner-owned proxy invocation identity when stock OpenCode lacks a unique inner identity;
- scope membership, generation admission close, trusted seal, and final collector sequence/drain;
- evidence completeness/eligibility;
- final evidence persistence.

The isolated Loom side may legitimately supply:

- tool output;
- thrown errors;
- permission decisions;
- hook mutations;
- workflow/OQ state;
- other product data.

Those values are not provenance merely because they contain provenance-shaped fields.

## TCB exclusions

The following are explicitly not trusted evidence authorities:

- Loom's own evidence records;
- product prose;
- model claims;
- workspace files;
- stock OpenCode Session storage when read after the fact as a substitute for a reviewed live capture boundary;
- raw stdout/stderr;
- OCI logs;
- the historical PR #41 patched observer;
- signatures/HMACs created by evaluated code.

## Open questions carried beyond Gate 1

1. Can the runner establish the evidence channel so shell subprocesses cannot inherit, duplicate, or impersonate it, while keeping the capability channel non-authoritative?
2. Can the exact plugin-source closure manifest be kept immutable to evaluated authority for the tested stock profile?
3. Can the runner prove generation admission close, queue drain, contiguous final sequence, and trusted seal under concurrency?
4. Can the runner prove the required Code Mode final-inner-result boundary using stock APIs/proxy wrapping?
5. Does the tested callback surface preserve stock ordering, cancellation, and remote side-effect semantics?
6. Can every candidate-controlled first sink be protected before persistence/clipping/logging/export?

These are provider-free/source-review obligations for later gates, not permission to alter OpenCode and not reasons to claim the properties are already proven.
