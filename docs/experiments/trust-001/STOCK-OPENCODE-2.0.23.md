# Stock OpenCode 2.0.23 capability assessment

## Decision boundary

OpenCode v2.0.23 is treated as **stock and immutable**. A missing public capability becomes `UNPROVEN` or `UNSUPPORTED`; it is not permission to patch OpenCode.

## Changes since v2.0.18 that help

Stock v2.0.23 adds useful supported plugin/session API surface:

- parent Session creation through `session.create({parentID})`;
- `session.remove`;
- `session.compact`;
- Session metadata forwarding through `session.update`;
- explicit provider request headers carrying Session and parent Session IDs;
- improved parallel permission-rejection handling.

These improve lifecycle fidelity and future compatibility, but pinned Loom `149406d` does not depend on most of these additions in its normal control plane.

## Critical components unchanged

Exact Git blobs are unchanged between v2.0.18 and v2.0.23 for:

- `packages/core/src/plugin/module.ts`;
- `packages/core/src/plugin/hooks.ts`;
- `packages/core/src/tool.ts`;
- `packages/core/src/tool/runtime.ts`;
- `packages/core/src/plugin/supervisor.ts`.

Consequences:

1. configured plugin code is still loaded/evaluated in the OpenCode process;
2. plugin hooks still execute in-process;
3. the plugin supervisor is lifecycle management, not security isolation;
4. `tool.execute.after` still occurs before later core normalization and return.

## Useful stock evidence surfaces

| Requirement | Stock surface | Planning status |
|---|---|---|
| Public live event access | plugin Context `ctx.event.subscribe()` returns OpenCode event stream | SUPPORTED-SOURCE for access; ordering/drain/completeness remain UNPROVEN |
| Session creation / ancestry | durable `session.created` with `parentID`; Session API | SUPPORTED-SOURCE |
| Agent for a step | durable `session.step.started` binds assistant message to agent | SUPPORTED-SOURCE |
| Native tool call ID/input | durable Session tool input/called events | SUPPORTED-SOURCE |
| Native terminal success/failure | durable `session.tool.success` / `session.tool.failed` | SUPPORTED-SOURCE |
| Permission mutation | `permission.hook("evaluate")` | SUPPORTED-SOURCE |
| Tool input mutation/failure | `tool.hook("execute.before")` | SUPPORTED-SOURCE |
| Tool handler result/error mutation | `tool.hook("execute.after")` | SUPPORTED-SOURCE, but not final caller boundary |
| Session context/retry mutation | Session hooks | SUPPORTED-SOURCE |
| Background/foreground child mechanics | stock Subagent/Session APIs/events | SUPPORTED-SOURCE; composition still required |
| Code Mode inner name/input/status | Code Mode metadata + hooks | SUPPORTED-SOURCE |
| Code Mode per-inner final caller value/error | no demonstrated public final boundary | **UNPROVEN** |
| Trusted run-wide ordering | public event delivery + runner sequence could support it | **UNPROVEN until provider-free ordering test** |
| Plugin isolation | none supplied by stock OpenCode | **UNSUPPORTED by OpenCode itself** |

## Code Mode finality

Stock v2.0.23 Code Mode records inner calls as roughly:

`{ tool, status, input }`

and returns them as outer `execute` metadata. Per-inner returned value/error is not retained there.

The inner tool execution path returns a `Tool.Result`, then Code Mode derives the script-visible value from structured `output` or textual content. Public `execute.after` runs before later core processing. Therefore CAP-004 cannot be marked supported merely from the public hook shape.

The experiment may investigate whether a runner-owned proxy tool can establish the tested inner finality without inference or OpenCode modification. Until demonstrated, the row stays `UNPROVEN`.

## Built-in shell authority

Stock OpenCode's built-in shell tool spawns real subprocesses from the OpenCode runtime domain. Unless a Session-specific environment exists, shell invocation begins from `process.env`.

This is load-bearing for TRUST-001:

- bridge/collector secrets MUST NOT be placed in the OpenCode process environment if shell can inherit them;
- shell subprocesses are evaluated workload authority for the threat model;
- evidence storage and collector paths must remain outside their writable/reachable authority;
- the candidate must prevent shell subprocesses from stealing or injecting an established bridge/collector channel, while allowing suppression to result only in incomplete evidence.

## Plugin loading escape

Stock OpenCode derives plugin operations from configuration documents/directories, auto-discovers entries under `plugin/` and `plugins/`, resolves configured package/local targets, watches relevant config/source inputs, and evaluates admitted plugin modules in-process.

The candidate must therefore freeze the **effective plugin-source operation set and every input that can change it**, not merely make one bridge file read-only. The runner must enumerate those config roots/documents, discovery directories, configured targets, symlink/source identities, and watched inputs for the exact profile before activation and keep them outside evaluated write authority for the generation.

Any post-activation change in the effective operation set or admitted source identity is a checkpoint stop/rejection. If this cannot be guaranteed using stock behavior without changing required Loom semantics, TRUST-001 is unsupported for that profile.

## Conclusion

v2.0.23 is a better stock target than v2.0.18, mainly due to improved Session APIs. It does not provide the missing trust boundary and does not solve Code Mode finality. The runner-only plan remains viable for investigation, but Gate 1 must treat these gaps explicitly.
