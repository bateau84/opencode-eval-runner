# Callback and request lifecycle

Status: **Wave-1 planning**.

The remote boundary must preserve stock OpenCode callback semantics without making the transport an alternate product or evidence authority.

## Request state machine

Every core → Loom callback/tool request uses a trusted request identity and one lifecycle:

```text
allocated
   ↓
outstanding
   ├─→ responded
   ├─→ failed
   ├─→ cancelled
   └─→ transport-lost
```

Rules:

- exactly one response may be accepted for one outstanding request;
- response identity is allocated by the trusted bridge;
- unsolicited, unknown, duplicate, replayed, stale-generation, and post-cancellation responses are rejected;
- a response from an older plugin generation is never rebound to a newer generation;
- channel loss does not trigger product replay;
- reconnect is outside the bounded experiment; a lost channel makes affected work unresolved/incomplete.

## Plugin generation

Activation binds:

- admitted Loom source revision/snapshot;
- bridge generation;
- isolated Loom process/container identity;
- capability manifest version;
- request sequence namespace.

All registrations and outstanding requests belong to that generation.

A restart creates a new generation and cannot inherit outstanding request authority.

## Generation sealing and collector drain

Request at-most-once rules do not by themselves prove completeness. The generation therefore needs a trusted two-phase close:

1. stop admitting new case-required work at the reviewed runner/OpenCode boundary;
2. let all already-admitted callback/tool requests and stock events settle or receive an explicit non-success classification;
3. bridge assigns a monotonic collector sequence to every accepted evidence observation for the generation;
4. only after its accepted observation queue is drained, bridge sends a trusted `seal(generation, finalSequence)`;
5. collector may call the generation complete only after it has a contiguous sequence through `finalSequence` and no post-seal accepted observation/request exists.

A late request/event after the seal is a protocol/completeness failure, not something silently ignored. A disposable OpenCode process exit may support the close boundary only after provider-free proof that relevant event and bridge queues are drained before the seal.

## Registration lifecycle

### Tool transform

The isolated Loom process executes Loom's transform callback against a remote-side recording editor.

It returns declarative:

- namespace definitions;
- tool schemas/metadata;
- opaque handler IDs.

The trusted bridge installs proxy tool handlers through stock `tool.transform`.

No Loom function/object crosses the boundary for execution in core.

### Agent transform

Stock transforms are synchronous and replayable. Pinned Loom conditionally selects General as default.

The bounded experiment must either:

- use a reviewed generic declarative recording/replay form for the exact transform; or
- limit the claim to initial activation and mark dynamic agent-registry reload `UNPROVEN`.

Trusted bridge code may not contain a Loom-specific hard-coded defaulting rule.

## Hook semantics

Stock `PluginHooks.trigger` invokes registered callbacks sequentially for one event. The bridge must preserve that observable behavior.

For one Loom callback:

1. core creates/owns the real event identity;
2. bridge allocates callback request ID;
3. event's allowed product fields are serialized;
4. isolated Loom callback executes;
5. returned mutation is structurally validated;
6. bridge applies only fields mutable in the stock API;
7. stock core continues normally.

### Mutable fields by family

- `tool.execute.before`: Loom may mutate `tool` / `input` according to stock semantics and may fail the call.
- `tool.execute.after`: Loom may mutate the completed `result` or error object as allowed by stock semantics; callback itself cannot fail the hook channel.
- `permission.evaluate`: Loom may mutate `effect` / `message`.
- `session.context`: Loom may mutate context/system/tool presentation according to stock API.
- `session.retry`: Loom may mutate retry decision.

Bridge validation is structural and host-semantic only. It does not invent Loom authorization, retry, OQ, budget, cancellation, or workflow behavior.

## Remote Loom tool execution

When a stock Tool proxy is invoked:

1. stock core supplies real `Tool.Context` with Session/agent/message and outer call ID;
2. bridge allocates a fresh remote-handler request ID;
3. bridge may also allocate a runner-owned **proxy child invocation ID** for trustworthy correlation where stock Code Mode reuses the outer call ID;
4. isolated Loom handler receives normal Loom input/context;
5. Loom returns/throws legitimate product data;
6. bridge maps the result into the registered stock Tool schema;
7. stock OpenCode continues through its normal hooks/normalization/session settlement.

The proxy child ID is evidence correlation owned by the bridge. It is not injected into Loom tool input and does not replace stock Session/Tool identity.

## Native finality

Trusted evidence should prefer the stock live Session event surface for canonical native terminal settlement:

- `session.tool.called`;
- `session.tool.success`;
- `session.tool.failed`.

The stock Session runner publishes the terminal only after normal tool execution and ToolOutput truncation. The candidate must consume the **live event stream**, not replay Session storage later as a substitute.

## Code Mode finality

Stock v2.0.23 does not expose a demonstrated public event containing each inner call's final script-visible value/error.

For remote Loom proxy tools, the bridge sees:

- exact proxy invocation entry;
- exact input;
- product result/error returned by isolated Loom;
- stock outer context/parent.

But stock Code Mode may still transform that Tool result into the JavaScript caller value after the proxy returns.

Therefore:

**CAP-004 inner finality remains UNPROVEN.**

The experiment may prove a runner-owned proxy/wrapping construction sufficient for the selected surface. If it cannot, the result is `UNSUPPORTED` for that stock profile; no OpenCode patch is allowed.

## Cancellation

Cancellation ownership remains stock OpenCode/Loom product semantics.

The bridge owns only request-channel authority:

- once trusted request authority is cancelled, a late response cannot mutate trusted OpenCode/bridge state or create eligible evidence;
- rejecting that response does **not** prove that isolated Loom made no earlier side effect in its SQLite, workspace, subprocesses, or other product state;
- where stock semantics expose interruption/cancellation, the bridge must propagate it and prove the selected callback/tool behavior;
- cancelling transport request authority is not represented as Loom workflow cancellation;
- a runner timeout is not represented as Loom cancellation;
- a Loom cancellation decision remains produced by Loom code;
- if the timing or effect of a post-cancel remote side effect cannot be shown equivalent to stock behavior, the product result is unresolved and evidence completeness is false for that case.

No cancellation path may retry product work implicitly.

## Channel loss

### Capability channel loss before product terminal

- request becomes `transport-lost`;
- generation stops admitting new capability work and the isolated generation is fenced/terminated according to the reviewed runner path;
- product outcome is unresolved or follows the reviewed stock transport failure path;
- remote side effects completed before the fence are product state and may be indeterminate;
- evidence remains incomplete;
- no automatic retry.

### Evidence channel loss

- collector sequence can no longer be proven contiguous/sealed;
- product completion cannot be rewritten or replayed to repair evidence;
- evidence remains incomplete;
- no reconnect/replay under the bounded experiment.

### After product completion but before evidence seal

- completed product result must remain completed;
- collector/capability loss cannot replace it;
- evidence may remain incomplete;
- no replay/retry.

## Required provider-free fidelity checks before Authorization B

- transform registration order;
- hook ordering;
- `execute.before` mutation and failure;
- handler return and throw;
- `execute.after` result/error mutation;
- native final Session event;
- permission mutation;
- context/retry mutation;
- duplicate/replayed/stale/late response rejection;
- cancellation + late response, including remote side-effect timing;
- capability/evidence channel loss before/after product completion;
- generation seal/drain, contiguous final sequence, and post-seal late request/event rejection;
- same-parent and different-parent overlapping requests.

Missing proof is `UNPROVEN`, not PASS or behavioral FAIL.
