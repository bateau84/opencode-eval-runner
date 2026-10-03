# Local OpenCode observation patch

This is a downstream patch maintained **in this runner repository**, not an
upstream OpenCode PR and not another Code Mode interpreter. The normal release
image and host installation remain unchanged.

The experimental **normal-invoke** image builds the existing OpenCode CLI from
`cd9a14a6b688d4021bee381dfd39d2cef9c0f862` (v2.0.18). `apply.py` verifies every
changed upstream blob before applying exact substitutions.

## Compatibility boundary

The patch exists underneath Loom's current path:

```text
bun run eval:live ...
  -> scripts/run-evals.py
  -> opencode-eval-runner invoke
  -> patched OpenCode
```

No alternate Loom case runner is introduced. The restricted `observe` command and
remote-tool profile are a separate supplemental experiment and are not applied to
this image.

The image enables:

```text
OPENCODE_EVAL_OBSERVATIONS=1
OPENCODE_EVAL_HOST_OBSERVATIONS=1
```

Those flags only expose diagnostic hook events. They do not change tool inputs,
permissions, session selection, provider flow or normal result handling.

## Runtime seams

### Native/direct tool boundary

A plugin may subscribe to:

```ts
ctx.tool.hook("execute.native-observed", callback)
```

The central Tool service emits `opencode-native-observation/v2` starts and final
returns/errors for normal native calls, including the outer `execute` call.

The start is emitted after input decoding, using the real Tool.Context:
session, agent, assistant message and runtime call ID. The terminal is emitted
after existing `execute.after` hooks and final content normalization.

### Code Mode inner boundary

The existing downstream seam remains:

```ts
ctx.tool.hook("execute.observed", callback)
```

It emits `opencode-local-observation/v1` records for actual Code Mode inner calls.
The runtime-generated inner invocation ID survives to the final interpreter
terminal. Returned values are captured after Code Mode conversion; caught throws
use the explicit `codemode-catch-name-message/v1` view.

Native and inner events share one monotonic runtime sequence. With host-semantics
observation enabled, the inner parent invocation ID is the actual native outer
`execute` observation ID; it is not reconstructed from input equality or FIFO.

The observation metadata is kept outside tool input. Existing product call IDs
and Tool.Context values are not replaced.

## Evidence boundary

These events are **diagnostic, not protected evidence**.

The normal Loom plugin is loaded inside the same OpenCode process as the runtime
seam. Code in that process shares the authority needed to reach same-process
files, sockets, descriptors and any signing/collector capability exposed there.
A hidden filename, HMAC key, random FD or localhost listener does not establish a
supported isolation boundary against arbitrary in-process plugin code.

Therefore the normal-invoke image proves semantic feasibility, not target-unforgeable
collection. Do not turn these events into PASS evidence merely because their
schema validates.

The restricted direct-session profile proves a different property by moving
evaluated tools out of collector authority. It intentionally changes the host
execution shape and cannot replace normal Loom eval semantics.

## Build and verification

The `Normal-invoke runtime observation seam` workflow:

1. applies only `apply.py` — **not** the restricted `apply-protected.py`;
2. runs source tests against the real core/interpreter;
3. builds `OpenCode 2.0.18-eval.4`;
4. publishes a commit/run-scoped immutable image in a separate credentialed job;
5. probes the runtime with a deterministic local provider;
6. runs `run_eval_live_compat_probe.py` through the public
   `opencode-eval-runner invoke` CLI.

The compatibility probe verifies that the existing runner result behavior remains
usable while native and Code Mode observations are emitted underneath it. It uses
disposable HOME/XDG/workspace state and no real-provider credentials.

The runtime probe additionally covers overlapping identical inner calls, reverse
completion, actual actor/input bindings, parent linkage, final modified returns,
caught throws and observer callback failure.

## Remaining feasibility boundary

The central runtime seam is suitable for Loom to test its existing host behavior
without moving its tool implementations behind a new service.

What is **not** solved by this patch is a protected collector for an arbitrary
in-process Loom plugin. Achieving that requires a real plugin isolation/capability
boundary while retaining the APIs and lifecycle semantics Loom depends on. That is
a broader runtime project and must not be implemented implicitly in PR #41.

See [Loom host-semantics feasibility](../docs/loom-host-semantics-feasibility.md).


## Loom-facing contract

The exact event fields, enablement, ordering, value/error semantics, redaction
boundary, completeness limits and unsupported coverage are defined in
[docs/loom-normal-invoke-observation.md](../docs/loom-normal-invoke-observation.md).

A bounded proposal for stronger plugin isolation, without replacing `invoke`, is
documented in
[docs/plugin-isolation-feasibility.md](../docs/plugin-isolation-feasibility.md).
