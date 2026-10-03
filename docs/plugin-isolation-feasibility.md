# Bounded feasibility proposal: protect observations without replacing Loom host semantics

## Why this is separate

Normal `eval:live -> runner invoke` semantic observation is feasible, but the
current Loom plugin and the observation callbacks execute in the same OpenCode
process.

Same-process mechanisms such as:

- a hidden file;
- a random file descriptor;
- a localhost socket;
- an environment-held/HMAC key;
- a closure-only signing callback;
- a private JavaScript object;

do not establish a security boundary from arbitrary code with the same process
authority. Signing such records would authenticate the signer, not prove that
evaluated plugin code could not fabricate what reaches it.

The restricted remote-tool profile solves this by changing execution topology,
but that cannot replace the host/session behavior Loom's current evals test.

A stronger solution is therefore broader runtime work and is **not implemented
implicitly in PR #41**.

## Candidate direction

The smallest candidate worth researching is a **process-isolated plugin host with
a narrow capability broker**, while OpenCode core/session/tool execution and the
collector remain in the trusted runtime process.

Conceptually:

```text
runner invoke
  -> trusted OpenCode core/session runtime
       -> protected runtime observation collector
       <-> narrow plugin capability RPC
             -> isolated evaluated Loom plugin process
```

This is a feasibility direction, not accepted architecture.

## Phase 0 result — Loom checkpoint `f8439e4`

The inventory is bounded enough to justify a **separate prototype**, not an
implicit expansion of PR #41.

Static inspection of `plugins/loom/index.ts` at the checkpoint found these
direct OpenCode-context capabilities:

| Capability | Direct uses | Broker class |
| --- | ---: | --- |
| `storage.get` | 167 | typed request/response |
| `storage.set` | 117 | typed request/response |
| `storage.scan` | 10 | typed request/response/stream |
| `location.directory` | 43 | immutable launch data |
| `location.project` | 5 | immutable launch data |
| `session.hook` | 2 | typed callback registration |
| `session.synthetic` | 1 | typed request/response |
| `session.get` | 1 | typed request/response |
| `tool.hook` | 2 | typed callback registration |
| `tool.transform` | 1 | typed registration transform |
| `tool.list` | 1 | typed request/response |
| `agent.transform` | 1 | typed registration transform |
| `agent.list` | 1 | typed request/response |
| `permission.hook` | 1 | typed callback registration |
| `rpc.register` | 1 | plugin-owned RPC registration |

The plugin also directly uses Node filesystem/path/crypto/async-hooks and
`child_process.execFile`. Those do not require execution inside the trusted
OpenCode process: an isolated Loom process can retain a disposable workspace
mount and its own bounded OS process authority while the collector mount,
signing authority, and OpenCode core remain absent from that process.

### Phase 0 classification

- **Pure/brokerable state:** storage get/set/scan, session get/synthetic,
  tool/agent list.
- **Typed lifecycle callbacks:** session/tool/agent/permission hooks and
  transforms. These require ordered request/response callback RPC, but not a
  generic `eval` or arbitrary function execution facility in the trusted
  runtime.
- **Launch facts:** location/project identity can be immutable launch data.
- **Plugin-local authority:** workspace filesystem/process operations and Loom's
  own RPC endpoint can remain in the isolated process.

No direct checkpoint usage requires handing the isolated process arbitrary
memory access, arbitrary module execution, or an unrestricted OpenCode API in
the trusted collector process.

**Phase 0 verdict: GO for a separate bounded prototype.** This is not approval to
build it inside PR #41. The prototype must still falsify the assumption that the
typed callback surface is sufficient for cancellation, grants, child delivery,
OQ continuation, and all current plugin behavior.

## Phase 0 — inventory method

Pin Loom checkpoint `f8439e4` and inventory every OpenCode capability used by the
actual plugin/smoke:

- tool registration and transformations;
- tool before/after hooks;
- permission decisions and grants;
- Session creation, prompt/continuation and lookup;
- child/subagent attachment and completion delivery;
- OQ continuation;
- cancellation/interrupt;
- workflow/gate state and persistence access;
- filesystem/process access;
- events and lifecycle callbacks.

For each capability classify:

1. pure request/response and safely serializable;
2. stateful but brokerable with an explicit identity/capability token;
3. callback/stream requiring lifecycle semantics;
4. same-process assumption that cannot be preserved without redesign.

Stop if required capability surface is effectively an unrestricted OpenCode API.

## Phase 1 — one semantic slice

Only if Phase 0 is bounded, prototype one real Loom-owned runtime case using:

- the unchanged `bun run eval:live -> scripts/run-evals.py -> runner invoke`
  entrypoint;
- actual Loom plugin code in the isolated plugin process;
- actual OpenCode permission enforcement in the trusted runtime;
- one native tool execution and one Code Mode inner execution;
- disposable HOME/XDG/workspace/database state;
- no real provider.

The broker must not accept actor/session/invocation identities from the plugin when
the trusted runtime already owns those identities.

## Phase 2 — discriminating composition tests

Before broadening the API, prove that isolation preserves the behaviors remote
tool substitution currently cannot establish:

- permission denial remains denial;
- grant/elevation scope is unchanged;
- child Session actor/session/message identity is genuine;
- foreground/background subagent completion still follows normal semantics;
- cancellation interrupts the same owned work;
- OQ/continuation delivery is not replaced by successful stubs;
- runtime tool result/error conversion remains identical;
- observation on/off produces the same product outcome;
- plugin attempts to write/submit collector records cannot create eligible
  observations.

Use Loom checkpoint `f8439e4` composition tests as the product-side authority;
runner fixtures are supporting evidence only.

## Go / no-go checkpoint

Proceed to a separate runtime project only if the prototype demonstrates:

- a finite reviewed capability surface;
- no generic arbitrary callback/code execution back into the trusted process;
- genuine runtime-owned identity and permission decisions;
- cancellation/lifecycle parity;
- a collector capability inaccessible to the plugin process;
- acceptable complexity relative to the eval-security goal.

Otherwise keep protected normal-host evidence **unsupported** and retain the
restricted direct-session profile only as supplemental smoke.

## Explicit non-goals

This proposal does not authorize:

- a general remote OpenCode platform;
- replacing `invoke` with `observe`;
- rewriting Loom's case model;
- permissive permission callbacks;
- fabricated Sessions or continuation responses;
- production deployment;
- a default-image change;
- signing as a substitute for collector isolation.
