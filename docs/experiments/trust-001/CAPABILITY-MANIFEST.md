# Bounded capability manifest

Status: **Wave-1 planning**.

The capability surface is derived from pinned Loom `149406dfa0a01f94491d17054e50a1bc84bb97be`, not from the full stock OpenCode PluginHost.

## Key reduction

Loom setup initially receives OpenCode plugin storage as `legacyStorage`, then creates its own `execution-state.sqlite` and proxies `ctx.storage` to that Loom-local transactional store.

Most steady-state Loom state therefore stays local to Loom. However pinned Loom retains `legacyStorage`: fresh-session cancellation admission can still perform a legacy `get`, and resumed pre-epoch sessions can invoke lazy migration that reads/scans legacy state and may write migration-refusal records.

Therefore stock plugin storage is **not setup-only**. The bounded broker must keep Loom-plugin-namespace `get/set/scan` available for the generation, with structural/size bounds and no evidence authority. These values remain product state.

## Required capabilities

| Capability | Direction | Why pinned Loom needs it | Trusted identity owner | Authority / notes | Planning status |
|---|---|---|---|---|---|
| immutable `location` facts | core → Loom | runtime/project identity, workspace paths | core/runner | value only; Loom cannot redefine trusted Location | SUPPORTED-DESIGN |
| legacy storage `get/set/scan` | Loom → core | activation import + lazy runtime compatibility/migration | core Loom-plugin storage namespace | generation-lifetime bounded product access; fresh-session compatibility can `get`, resumed legacy migration can `get/set/scan`; never evidence authority | SUPPORTED-DESIGN |
| `rpc.register` | Loom → core registration; calls core → Loom | sidebar RPC | core owns effective registration | async proxy handler | SUPPORTED-DESIGN |
| `agent.transform` | Loom registration → core | set General as default when present | core owns active registry | synchronous stock transform is a fidelity challenge; bounded experiment may support initial generation only | **UNPROVEN** |
| `agent.list` | Loom → core | roster tool | core | normal request/response | SUPPORTED-DESIGN |
| `tool.transform` | Loom registration → core | register Loom namespace/tools | core owns effective registration | remote setup returns declarative registrations + opaque handler IDs | SUPPORTED-DESIGN |
| `tool.list` | Loom → core | attestation checks effective roster registration | core | remote view must preserve Loom-owned handler identity through token mapping | **UNPROVEN** |
| `permission.hook("evaluate")` | core → Loom → core | Loom authorization/grants/budgets | core owns event Session/agent/action; Loom owns product decision | mutable effect/message only; at-most-once callback | SUPPORTED-DESIGN |
| `session.hook("context")` | core → Loom → core | guidance + observed user message + upgrade notice | core | mutable system context | SUPPORTED-DESIGN |
| `session.hook("retry")` | core → Loom → core | Loom retry limit | core | mutable retry decision | SUPPORTED-DESIGN |
| `session.get` | Loom → core | legacy session/project checks, background parent validation | core | returned Session data remains product data | SUPPORTED-DESIGN |
| `session.context` | Loom → core | exact subagent background request discovery | core | request/response | SUPPORTED-DESIGN |
| `session.synthetic` | Loom → core | background/OQ/coordinator delivery | core owns Session identity/admission | Loom supplies product message/metadata | SUPPORTED-DESIGN |
| `tool.hook("execute.before")` | core → Loom → core | cancellation fences, locks, question/budget admission, evidence bookkeeping | core owns call context | mutable input / may fail | SUPPORTED-DESIGN |
| `tool.hook("execute.after")` | core → Loom → core | question decisions, mutation/evidence bookkeeping | core owns call context | mutable result/error; stock finality occurs later | SUPPORTED-DESIGN |
| remote Loom tool execute handler | core → Loom → core | all Loom native/Code Mode tools | bridge allocates proxy request; stock core owns outer context | Loom returns legitimate product result/error only | SUPPORTED-DESIGN |
| trusted event subscription (runner bridge only) | core → host collector | Session ancestry, native called/terminal records, scope accounting | stock core + host collector | not exposed to Loom as evidence authority | SUPPORTED-SOURCE |

## Source-derived host-use closure

Static inspection of pinned Loom `149406dfa0a01f94491d17054e50a1bc84bb97be` found direct host use limited to:

- immutable `location` facts;
- storage `get/set/scan`;
- `rpc.register`;
- `agent.transform` and `agent.list`;
- `tool.transform`, `tool.list`, and tool hooks;
- permission hook;
- Session `get`, `context`, `synthetic`, and Session hooks.

The runner bridge's trusted `event.subscribe()` use is an observation surface, not a Loom-requested capability and is not exposed to isolated Loom.

Any newly discovered pinned-Loom host call or later Loom revision adds capability surface and creates a new candidate checkpoint with affected authority review.

## Not required by pinned Loom selected surface

The experiment MUST NOT implement the full PluginHost for completeness. Current pinned Loom does not directly require, among others:

- provider/model transforms;
- MCP transforms;
- VCS API;
- websearch;
- worktree;
- skill transforms;
- shell hooks;
- Session create/remove/compact/move;
- general generation APIs.

If later source inspection or an authorized scenario demonstrates a need, adding one is a **new candidate checkpoint** and requires affected authority review.

## Transform fidelity

### Tool transform

Pinned Loom's tool transform primarily adds a namespace and tool definitions. The isolated setup can execute Loom's callback against a remote-side recording editor and send:

- declarative namespace;
- declarative tool metadata/schema;
- opaque execute-handler ID.

The bridge installs local proxy handlers; Loom code itself never crosses into trusted core.

### Agent transform

Pinned Loom performs:

```text
if general exists -> make general default
```

Stock transform callbacks are synchronous and replayable. A remote async callback cannot simply replace that mechanism.

For the bounded experiment, acceptable planning options are:

1. prove a generic declarative recording/replay representation for this exact transform; or
2. mark dynamic agent-transform reload outside the tested surface and prove initial activation parity.

Embedding a Loom-specific `default("general")` rule directly in trusted bridge code is **not acceptable**.

## Tool identity and remote function identity

Stock `tool.list` returns function-bearing registrations in-process. Serialized RPC cannot preserve JavaScript function identity directly.

The broker must retain an opaque registration mapping so the isolated Loom view can recognize its own registered handler identity without trusting a caller-supplied provenance claim.

This is needed by Loom's attestation tool and remains **UNPROVEN** until the provider-free callback/registration preflight.

## Code Mode

For a remote Loom tool invoked inside Code Mode, the trusted bridge can allocate a fresh proxy-child invocation identity when its proxy execute handler is actually entered, while retaining stock outer `Tool.Context.id` as the parent association.

This can improve correlation without changing OpenCode.

However stock public APIs still do not independently expose the final per-inner script-visible value/error after every Code Mode conversion. CAP-004 remains **UNPROVEN** pending the bounded experiment.

## Rejection rule

No capability may accept:

- executable callback/module payload for execution in the trusted domain;
- caller-selected trusted invocation/session/parent identity;
- caller-selected sequence/scope/completeness/eligibility;
- generic arbitrary OpenCode method dispatch.

A large typed surface is acceptable; authority escalation is not.
