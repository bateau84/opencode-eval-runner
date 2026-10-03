import { test, expect } from "bun:test"
import { Effect, Schema } from "effect"
import { CodeMode, Tool } from "@opencode/codemode"
import { CodeModeTool } from "../src/codemode/tool.js"
import { LocalObservation } from "../src/codemode/local-observation.js"

const context = {
  sessionID: "actual-session", messageID: "actual-message", id: "shared-parent", agent: "actual-agent",
  progress: () => Effect.void,
} as any
const registration = (name: string) => ({
  name, description: "local observer fixture", input: Schema.Struct({ tag: Schema.optionalKey(Schema.String) }),
  options: { namespace: "fixture", codemode: true }, execute: () => Effect.succeed({ content: "unused" }),
})

test("real core and interpreter: identical overlap, final conversion, caught errors, discarded returns", async () => {
  const events: any[] = []
  const inventory = { tools: new Map(["echo", "denied", "throws", "mutate"].map((name) => [`fixture_${name}`, registration(name)])) }
  let ordinal = 0
  let release!: () => void
  const first = new Promise<void>((resolve) => { release = resolve })
  const execute = (name: string, _tool: unknown, input: unknown, actual: unknown, observed?: (value: unknown) => Effect.Effect<void>) => Effect.gen(function* () {
    expect(actual).toBe(context)
    const dispatched = { ...(input as object), actual: true }
    if (observed) yield* observed(dispatched)
    if (name === "fixture_echo") {
      const n = ++ordinal
      if (n === 1) yield* Effect.promise(() => first)
      if (n === 2) setTimeout(release, 10)
      return { content: `CALL-${n}` }
    }
    if (name === "fixture_throws") return yield* Effect.die(new Error("THROWN-FINAL"))
    if (name === "fixture_denied") return { content: '{"ok":false}' }
    return { content: "FINAL-RETURN" }
  })
  const tool = CodeModeTool.create(inventory as any, execute as any, (event) => Effect.sync(() => { events.push(event) }))
  const result = await Effect.runPromise(tool.execute({ code: `
    const pair = await Promise.all([tools.fixture.echo({tag:"same"}),tools.fixture.echo({tag:"same"})]);
    if (pair[0] !== "CALL-1" || pair[1] !== "CALL-2") throw Error("pair");
    const denied = await tools.fixture.denied({});
    if (denied !== '{"ok":false}') throw Error("denial");
    try { await tools.fixture.throws({}); } catch (error) {
      if (error.name !== "Error" || error.message !== "THROWN-FINAL") throw Error("error view");
    }
    if (await tools.fixture.mutate({}) !== "FINAL-RETURN") throw Error("final");
    return "DISCARDED";
  ` }, context))
  expect(result.output.output).toBe("DISCARDED")
  const starts = events.filter((e) => e.kind === "call_start")
  const ends = events.filter((e) => e.kind === "call_end")
  expect(starts).toHaveLength(5)
  expect(ends).toHaveLength(5)
  expect(new Set(starts.map((e) => e.invocation_id)).size).toBe(5)
  expect(starts[0].input.value).toEqual({ tag: "same", actual: true })
  expect(starts[1].input.value).toEqual(starts[0].input.value)
  expect(ends[0].invocation_id).toBe(starts[1].invocation_id)
  expect(ends[1].invocation_id).toBe(starts[0].invocation_id)
  expect(ends[0].result.value).toBe("CALL-2")
  expect(ends[1].result.value).toBe("CALL-1")
  expect(starts[1].sequence).toBeLessThan(ends[0].sequence)
  expect(ends[2].result.value).toBe('{"ok":false}')
  expect(ends[3].outcome).toBe("threw")
  expect(ends[3].error.value).toEqual({ name: "Error", message: "THROWN-FINAL" })
  expect(ends[4].result.value).toBe("FINAL-RETURN")
  expect(starts[0].actor).toEqual({ agent: "actual-agent", session_id: "actual-session", message_id: "actual-message" })
  expect(starts[0].parent.call_id).toBe("shared-parent")
  expect(events.at(-1)).toMatchObject({ kind: "parent_end", missing_terminals: 0, unsupported_dispatches: 0, evidence_eligible: false })
})

test("native outer observation binds the actual Code Mode parent without changing context", async () => {
  const nativeEvents: any[] = []
  const innerEvents: any[] = []
  const native = LocalObservation.makeNative(context, "execute", (event) => Effect.sync(() => nativeEvents.push(event)))
  await Effect.runPromise(native.start({ code: "return await tools.fixture.echo({})" }))

  const inventory = { tools: new Map([["fixture_echo", registration("echo")]]) }
  const execute = (_name: unknown, _tool: unknown, input: unknown, actual: unknown, observed?: (value: unknown) => Effect.Effect<void>) =>
    Effect.gen(function* () {
      expect(actual).toBe(context)
      if (observed) yield* observed(input)
      return { content: "INNER-FINAL" }
    })
  const tool = CodeModeTool.create(inventory as any, execute as any, (event) => Effect.sync(() => innerEvents.push(event)))
  const result = await Effect.runPromise(tool.execute({ code: "return await tools.fixture.echo({});" }, context))
  await Effect.runPromise(native.returned(result))
  native.close()

  const nativeStart = nativeEvents.find((event) => event.kind === "call_start")
  const nativeEnd = nativeEvents.find((event) => event.kind === "call_end")
  const innerStart = innerEvents.find((event) => event.kind === "call_start")
  expect(nativeStart).toMatchObject({
    schema: "opencode-native-observation/v1",
    invocation_id: native.invocationID,
    call_id: "shared-parent",
    tool: "execute",
    mode: "native",
    parent: null,
    actor: { agent: "actual-agent", session_id: "actual-session", message_id: "actual-message" },
  })
  expect(nativeEnd.invocation_id).toBe(native.invocationID)
  expect(innerStart.parent.invocation_id).toBe(native.invocationID)
  expect(innerStart.parent.call_id).toBe("shared-parent")
  expect(nativeStart.sequence).toBeLessThan(innerStart.sequence)
  expect(context).not.toHaveProperty("evaluationInvocationID")
})

test("native observation keeps delegated actor identity as supplied by the real tool context", async () => {
  const child = {
    sessionID: "child-session", messageID: "child-message", id: "child-call", agent: "reviewer",
    progress: () => Effect.void,
  } as any
  const events: any[] = []
  const observation = LocalObservation.makeNative(child, "read", (event) => Effect.sync(() => events.push(event)))
  await Effect.runPromise(observation.start({ file: "README.md" }))
  await Effect.runPromise(observation.returned({ output: "ok", content: [] }))
  observation.close()
  expect(events[0].actor).toEqual({ agent: "reviewer", session_id: "child-session", message_id: "child-message" })
  expect(events[0]).toMatchObject({ call_id: "child-call", mode: "native", parent: null })
  expect(events[1].invocation_id).toBe(events[0].invocation_id)
})

test("native decode failures do not fabricate terminal-only observations", async () => {
  const events: any[] = []
  const observation = LocalObservation.makeNative(context, "read", (event) => Effect.sync(() => events.push(event)))
  await Effect.runPromise(observation.threw({ message: "decode failed" }))
  observation.close()
  expect(events).toEqual([])
})

test("runtime-carried invocation IDs reach actual executable and terminal", async () => {
  const executing: string[] = [], after: string[] = []
  const tools = { one: Tool.make({ description: "one", input: Schema.Struct({}), output: Schema.Null,
    execute: (_input, call) => Effect.sync(() => { executing.push(call!.id); return null }) }) }
  await Effect.runPromise(CodeMode.execute({ tools, code: "await tools.one({}); await tools.one({}); return null;",
    hooks: { "tool.after": (call) => Effect.sync(() => { after.push(call.id) }) } }))
  expect(executing).toEqual(after)
  expect(new Set(executing).size).toBe(2)
})

test("observer failure does not replace actual return", async () => {
  const inventory = { tools: new Map([["fixture_echo", registration("echo")]]) }
  const execute = (_name: unknown, _tool: unknown, input: unknown, _context: unknown, observe?: (input: unknown) => Effect.Effect<void>) =>
    Effect.andThen(observe?.(input) ?? Effect.void, Effect.succeed({ content: "UNCHANGED" }))
  for (const observe of [undefined, () => Effect.die("observer I/O failure")]) {
    const tool = CodeModeTool.create(inventory as any, execute as any, observe)
    const result = await Effect.runPromise(tool.execute({ code: 'return await tools.fixture.echo({});' }, context))
    expect(result.output.output).toBe("UNCHANGED")
  }

  const native = LocalObservation.makeNative(context, "read", () => Effect.die("native-observer-failure"))
  await Effect.runPromise(native.start({ path: "x" }))
  await Effect.runPromise(native.returned({ output: "UNCHANGED", content: [] }))
  native.close()
})

test("snapshots are owned, immutable, and do not call getters/toJSON", () => {
  const source = { nested: { value: "original" } }
  const copied: any = LocalObservation.snapshot(source)
  source.nested.value = "changed"
  expect(copied.value.nested.value).toBe("original")
  expect(Object.isFrozen(copied.value.nested)).toBe(true)
  let called = false
  expect(LocalObservation.snapshot({ get token() { called = true; return "secret" } }).state).toBe("omitted")
  expect(LocalObservation.snapshot({ toJSON() { called = true; return "secret" } }).state).toBe("omitted")
  expect(called).toBe(false)
  expect(LocalObservation.snapshot(undefined).state).toBe("omitted")
  expect(LocalObservation.snapshot({ value: Infinity }).state).toBe("omitted")
  const cycle: any = {}; cycle.self = cycle
  expect(LocalObservation.snapshot(cycle).state).toBe("omitted")
})
