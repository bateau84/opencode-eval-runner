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
| broker socket directory | host-created private runtime dir | bridge endpoint only | Loom endpoint only | never under workspace |

## Channel bootstrap

The candidate should avoid a reusable credential in `process.env`, because stock shell inherits `process.env` when no Session-specific environment overrides it.

Planning candidate:

1. runner creates private host-side Unix-domain endpoints outside the workspace;
2. bridge and isolated Loom establish their required long-lived channel(s) during activation **before inference/tool execution**;
3. host accepts only the expected bootstrap peer/container/process for the trusted bridge;
4. listener path is removed/closed after the expected connection is established;
5. established bridge descriptors must be close-on-exec and not inherited by stock shell subprocesses;
6. reconnect is unsupported in the bounded experiment; channel loss yields incomplete/unresolved evidence and never retries product work.

This mechanism remains **UNPROVEN** until provider-free construction/preflight. It is specified here so Gate 1 reviews an actual authority proposal rather than the phrase "separate process."

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

Stock OpenCode discovers configured/local plugins in-process. The experiment profile MUST therefore:

1. preflight every project/global/config-root plugin source;
2. admit only runner-owned trusted bridge code in-process;
3. reject package/file plugin declarations not explicitly trusted;
4. prevent runtime creation/replacement of auto-discovered plugin sources in evaluated-writable paths;
5. preserve required non-plugin project inputs separately.

A practical runner-owned approach may use read-only submounts/overlays for project config/plugin-discovery paths while leaving the requested workspace mode unchanged elsewhere. Exact mounts are a Gate-1/Authorization-A item.

If the stock CLI cannot prevent an evaluated-writable path from becoming an in-process plugin source without changing required Loom behavior, the tested profile is **UNSUPPORTED**.

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
