# Effective-authority manifest

Status: **proposed Wave-1 boundary; not yet experimentally verified**.

## Principle

Different processes/containers do not automatically create TRUST-001. Effective write/control authority is the criterion.

## Proposed filesystem and mount authority

| Resource | Host collector | Stock OpenCode domain | Isolated Loom domain | Requirement |
|---|---|---|---|---|
| evaluated workspace | no direct execution | requested RO/RW | same requested RO/RW where Loom semantics require it | product state only |
| runner/bridge source | host-owned | read-only | none | never workspace-writable |
| stock OpenCode executable/root | no mutation | read-only image | none | immutable stock v2.0.23 |
| Loom source/dependencies | provenance only | **not imported/executed** | read-only | module boundary begins before evaluation |
| OpenCode disposable HOME/XDG | no | private tmpfs/state | none | invocation-local |
| Loom HOME/XDG/state | no | none | private | invocation-local; Loom owns its local runtime state |
| collector/evidence storage | read/write | **not mounted** | **not mounted** | evaluated code cannot modify evidence |
| safety policy/inventory | host-private | delivered only to trusted bridge/collector through reviewed private path | no raw policy | no credential-policy disclosure |
| container-engine socket | host runner only if required | none | none | never exposed |
| evidence-channel bootstrap endpoint | host-created private runtime dir | bridge bootstrap only | **not mounted/reachable** | never under workspace; removed after admitted connection |
| capability-channel bootstrap endpoint | host-created private runtime dir | bridge endpoint only | Loom endpoint only | separate from evidence channel; removed after admitted connection |

## Channel authority and bootstrap

The design requires **two distinct channels with different authority**:

1. **evidence channel** — trusted runner bridge → host collector. This is the only channel allowed to introduce candidate runtime observations into evidence authority.
2. **capability channel** — runner bridge ↔ isolated Loom. This transports product callbacks, requests, mutations, and results only. It is untrusted for evidence authority.

The channels MUST NOT share an accepted descriptor, listener path, authentication material, or message type that the collector could interpret as evidence. Control of the capability channel may break product behavior, but it must not create an eligible evidence record.

The candidate should avoid a reusable credential in `process.env`, because stock shell inherits `process.env` when no Session-specific environment overrides it.

### Evidence-channel bootstrap

1. runner creates a private Unix-domain endpoint outside the workspace;
2. only the stock OpenCode domain receives bootstrap reachability; the isolated Loom domain never receives the collector endpoint;
3. the bridge connects during activation **before inference/tool execution**;
4. host admits only the expected stock OpenCode process hosting the reviewed bridge, using runner-owned process/container identity plus kernel peer identity where available;
5. the listener is closed/unlinked immediately after the expected connection is admitted;
6. the established descriptor is close-on-exec and must not be inherited or duplicated by stock shell subprocesses;
7. reconnect is unsupported in the bounded experiment.

### Capability-channel bootstrap

1. runner creates a separate private endpoint outside the workspace;
2. only the expected bridge side and isolated Loom generation may establish it;
3. the listener is closed/unlinked after the expected peers are admitted;
4. this channel has no collector credential, evidence framing authority, or evidence-write capability;
5. compromise, duplication, or impersonation of this channel makes affected product work failed/unresolved and evidence incomplete; it never upgrades product data into evidence.

Both bootstraps remain **UNPROVEN** until provider-free construction/preflight. They are specified here so Gate 1 reviews concrete authority separation rather than process topology alone.

## Process authority

Required candidate controls:

- read-only container roots;
- non-root execution;
- dropped Linux capabilities;
- no-new-privileges;
- default or stricter seccomp;
- no host PID namespace;
- no Docker/Podman control socket;
- no evidence volume in evaluated domains;
- no bridge secret in process environment;
- core dumps disabled or guaranteed non-persistent/unavailable to evaluated code.

The provider-free preflight must specifically test whether evaluated shell/Loom children can:

- ptrace or use `process_vm_readv/writev` against the trusted OpenCode process;
- use `pidfd_getfd` or `/proc/<pid>/fd` to duplicate bridge descriptors;
- access `/proc/<pid>/mem`;
- discover a still-connectable collector listener;
- signal/kill trusted work.

Killing/suppressing trusted work is not by itself a false-evidence violation: it must become incomplete/non-evidence. Reading/duplicating the trusted channel or creating eligible records is a rejection.

## Plugin-loading authority

Stock OpenCode builds an effective plugin-source operation set from configuration documents, configuration roots, auto-discovered `plugin/` and `plugins/` entries, configured package/local targets, and watched source/config changes. Protecting only the final plugin file is therefore insufficient.

Before activation the candidate MUST build a **plugin-source closure manifest** that:

1. records the exact effective plugin add/remove operation set;
2. enumerates every configuration document/root, discovery directory, configured local source, package declaration, symlink target, and watched input that can change that operation set for the tested profile;
3. admits only runner-owned trusted bridge code for in-process execution;
4. makes every operation-set input runner-owned and read-only/unreachable to evaluated write authority for the generation;
5. preserves required non-plugin project inputs separately;
6. treats any post-activation operation-set change, newly discovered source, or changed admitted source identity as a checkpoint stop/rejection, not a hot reload.

A practical runner-owned approach may use read-only submounts/overlays for the exact source/config closure while leaving the requested workspace mode unchanged elsewhere. Authorization A must name the concrete paths and operation set for its checkpoint.

If stock OpenCode cannot keep this source closure immutable without changing required Loom behavior, the tested profile is **UNSUPPORTED**.

## Network authority

- Collector endpoint is not a general network service.
- Loom broker channel exposes only the reviewed typed capability protocol.
- Evaluated network access cannot provide an alternate route to collector, runner, container engine, or another trusted service.
- Any network mode needed by Loom/provider behavior is reported separately from broker/collector reachability.

## Credentials

- Provider credentials are product inputs, not evidence authority.
- Collector/broker authentication material, if ultimately required, is not carried in argv, process environment, workspace, project config, Loom state, or mounted readable files.
- A product credential can never authenticate evidence.

## Current verdict

Effective-authority separation: **UNPROVEN**.

This is expected before candidate construction. Gate 1 should judge whether the proposed controls are coherent and sufficient to authorize a provider-free prototype—not whether they have already been experimentally proven.
