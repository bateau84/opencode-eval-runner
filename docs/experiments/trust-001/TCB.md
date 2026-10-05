# Provisional trusted computing boundary

Status: **Wave-1 planning artifact. Gate 1 NOT RUN.**

This TCB is the candidate boundary to review. It is not a claim that the boundary is already effective.

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

The stock OpenCode domain is therefore a **mixed-authority OS domain**. Gate 1 must review whether the proposed channel and mount controls prevent its untrusted subprocesses from escalating into evidence authority.

## Evidence authority

Only the trusted side may establish:

- effective admitted registration identity;
- trusted collector sequence;
- authoritative runtime Session/message/call facts obtained from stock OpenCode;
- runner-owned proxy invocation identity when stock OpenCode lacks a unique inner identity;
- scope membership and closure;
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

## Open questions before Gate 1 PASS

1. Can the runner establish a bridge/collector channel that shell subprocesses cannot inherit, duplicate, or impersonate?
2. Can project/plugin discovery be bounded so evaluated workspace mutations cannot cause new untrusted code to load in-process?
3. Can the runner prove the required Code Mode final-inner-result boundary using stock APIs/proxy wrapping?
4. Does the tested callback surface preserve stock ordering and cancellation semantics?
5. Can every first evidence sink be protected before persistence/clipping?

These are review conditions, not permission to alter OpenCode.
