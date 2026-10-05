# Architect recommendation — stock OpenCode TRUST-001 candidate

Status: **Gate 1 PASS; recommended experiment candidate, not selected architecture**.

## Recommendation

Following independent Gate-1 review, the owner may consider a separate Authorization A to investigate:

> A runner-owned trusted bridge plugin loaded by **stock OpenCode v2.0.23**, proxying the bounded Loom plugin API to an isolated Loom execution domain, while host-side runner code owns evidence collection, safety, scope accounting, and persistence.

No OpenCode modification is permitted.

## Why this candidate

It preserves the existing normal runner entrypoint and stock OpenCode Tool/Session semantics while moving evaluated Loom module execution out of the trusted OpenCode process.

It reuses a natural supported extension point—the stock plugin API—without requiring a new workflow engine, state API, permission engine, or OpenCode fork.

## Important revision from the earlier candidate

The candidate is **not** simply "put Loom in another process."

The trust design must separately address:

- stock shell subprocesses executing under the OpenCode runtime's OS authority;
- project/config plugin-loading escape paths;
- broker/collector channel authority;
- synchronous transform fidelity;
- Code Mode inner finality.

Process topology alone is not evidence of TRUST-001.

## Proposed boundary

### Trusted

- host runner launcher/verifier;
- host collector/scope/safety/writer;
- stock OpenCode v2.0.23 core;
- runner bridge plugin;
- reviewed protocol/correlation implementation;
- kernel/OCI enforcement assumptions.

### Untrusted for evidence authority

- Loom module/dependencies;
- Loom callbacks/handlers/policy logic;
- Loom children;
- model/product data;
- built-in shell subprocesses;
- writable workspace;
- arbitrary external plugins.

## No OpenCode patch fallback

If stock OpenCode's supported APIs cannot establish a Loom contract requirement, the only valid outcomes are:

- supported by runner-owned wrapping;
- `UNPROVEN`;
- `UNSUPPORTED`.

"Patch OpenCode" is not an allowed resolution.

## Why v2.0.23

Compared with v2.0.18 it exposes more Session lifecycle API, including parent Session creation, removal, compaction, and metadata updates.

However the plugin loader, plugin hooks, Tool execution path, Tool runtime, and plugin supervisor relevant to TRUST-001 remain unchanged. v2.0.23 does not itself isolate plugins.

## Candidate strengths

- pinned Loom needs only a bounded subset of PluginHost;
- Loom moves most normal state to its own SQLite after setup, reducing broker state surface, while bounded stock plugin-storage `get/set/scan` remains available for pinned Loom's lazy legacy-compatibility path;
- stock live Session events provide strong native ancestry/called/terminal facts;
- runner proxy Loom tools can allocate trustworthy child correlation without changing tool inputs;
- Loom semantics remain executed by Loom.

## Candidate risks

1. **Code Mode inner finality** — stock public metadata does not expose each inner final script-visible result/error.
2. **Mixed OS trust** — shell subprocesses share the OpenCode runtime domain.
3. **Plugin loading** — evaluated paths must not cause new in-process plugin imports.
4. **Synchronous transforms** — stock transform callbacks are synchronous/replayable.
5. **Callback/cancellation fidelity** — RPC separation must preserve shared mutable event behavior and late-response rules.
6. **First-sink confidentiality** — new broker/collector paths must not persist secrets before projection.
7. **Scope sealing** — apparent quiescence is not complete evidence until trusted admission is closed and the collector has drained a generation-scoped final sequence.

## Recommendation status

**Gate 1: PASS.** The corrected planning package is coherent and bounded enough for the owner to consider a separate Authorization A for construction and explicitly named provider-free preflights.

This review does not grant Authorization A, prove feasibility, or authorize semantic/adversarial/model-backed execution.
