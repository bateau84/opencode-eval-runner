# Scope and completeness contract

Status: **Wave-1 planning**.

Coverage is relative to the case-required observation scope. Loom defines what must be observed; the runner resolves membership and completeness from trusted runtime facts.

## Bounded experiment scope descriptor

For the initial experiment, use a deliberately strong but finite scope:

```text
generation = one admitted bridge/Loom generation for this runner invocation
root = actual target Session for this runner invocation
include = root +
          all actual descendant Sessions created from root during the case +
          all required tool/proxy invocations in those Sessions
interval = target turn start until trusted closure predicate
```

A future contract may support narrower explicit selectors, but the experiment does not need an unlimited global monitor.

## Root admission

The host launch record must bind the experiment to the actual target invocation.

The collector must not select "first Session seen" or infer root identity from model prose.

The candidate must define how the normal runner invocation admits its target root Session ID before Gate 2. Acceptable proof must come from stock runtime/runner identity, not Loom claims.

Until provider-free candidate construction demonstrates this binding, root admission is **UNPROVEN**.

## Session membership

Trusted stock Session events provide:

- `session.created.sessionID`;
- `session.created.parentID`;
- Session step/message identities.

A Session joins scope only when trusted ancestry reaches the admitted root under the declared inclusion rule.

Loom-returned child IDs may be used as product data/corroboration but cannot create authoritative membership.

## Tool membership

Native Tool identity is reconstructed from trusted stock Session events:

- assistant message / Session;
- input start/name;
- called input;
- call ID;
- terminal success/failure.

For runner proxy Loom tools, the bridge additionally owns the remote proxy request/child correlation.

A plugin cannot add or remove an authoritative tool member by emitting collector-shaped payloads.

## Background descendants

A root/foreground turn ending does not close scope while a required admitted background descendant remains unresolved.

For the bounded experiment, every descendant Session admitted by the inclusion rule must reach an accounted terminal/idle state or an explicit non-success classification.

## Trusted member states

Each required member is represented as one of:

- started;
- terminal-success;
- terminal-error;
- interrupted;
- timed-out;
- unresolved;
- unsupported.

No unknown state is silently counted as zero/missing-free.

## Trusted closure seal

Completeness is a two-phase property: **quiescence, then trusted seal**. Observing that all currently known members look terminal is not enough because a late admitted callback, descendant, or live event could otherwise arrive after the collector declares success.

For the bounded experiment:

1. a reviewed runner/OpenCode boundary closes admission for new case-required work for the generation;
2. every already-admitted Session/tool/proxy/capability member settles or receives an explicit non-success classification;
3. the trusted bridge assigns a monotonic collector sequence to every accepted observation for that generation;
4. after all accepted observations are emitted, the bridge sends `seal(generation, finalSequence)`;
5. the collector accepts completeness only if it has a contiguous sequence through `finalSequence`, all required members satisfy the closure predicate, and no accepted post-seal work/event exists.

A late required request/event after seal is a protocol/completeness failure. It is never silently ignored.

A disposable OpenCode process exit may be used as part of the trusted close boundary only after provider-free proof that the relevant stock-event and bridge queues are drained before the seal. Process exit by itself is not completeness.

## Closure predicate

The bounded experiment scope can close as complete only when all are true:

1. root identity is admitted;
2. no required Session membership is ambiguous;
3. trusted generation admission is closed for new case-required work;
4. root reaches the required lifecycle boundary;
5. every in-scope descendant required by the scope has reached its required lifecycle boundary;
6. every in-scope required tool/proxy invocation has one trusted terminal;
7. there are no unresolved outstanding capability requests;
8. evidence channel did not lose an unaccounted interval;
9. collector has the trusted generation seal and a contiguous sequence through its `finalSequence`;
10. no required request/event was accepted after that seal;
11. no required operation is classified unsupported;
12. no evidence-safety loss required by the case prevents the deterministic assertion.

If any condition is false, completeness is false/unknown as appropriate.

## Forbidden absence

A forbidden-absence assertion is eligible only after the trusted generation seal and only if every in-scope path on which the forbidden behavior could occur is completely covered.

Examples:

- If forbidden behavior may occur in a background child, root-only coverage is insufficient.
- If Code Mode inner capture is unsupported for the selected operation, absence inside Code Mode is not proved.
- A missing terminal cannot be interpreted as "did not happen."

## Concurrency

Calls are not correlated by FIFO or completion order.

The experiment must cover:

- identical calls, same parent, reverse completion;
- identical calls, different parents, overlapping execution.

For remote Loom proxy tools, bridge-owned proxy request IDs may provide unique child correlation while retaining the stock outer call as parent.

For stock inner tools that cannot be uniquely correlated through public APIs, report ambiguity/unsupported rather than guess.

## Scope authority

Evaluated Loom/plugin/product data cannot authoritatively provide:

- member list;
- parentage;
- sequence;
- terminal state;
- close signal;
- missing count;
- completeness.

These come only from the trusted collector/bridge and stock runtime surfaces admitted by this contract.

## Experiment limitation

A successful bounded scope proves only the selected scope rule. It does not establish unlimited descendant coverage or every future Loom case scope.
