export * as LocalObservation from "./local-observation.js"

import { CodeMode } from "@opencode/codemode"
import type { Context } from "@opencode/schema/tool"
import { Effect } from "effect"

// Runtime observation seam only. Nothing here authenticates a collector.
// Sequence is process-wide so native and Code Mode records can be merged
// without inferring ordering from timestamps or array position.
let sequence = 0
const nativeExecuteParents = new WeakMap<object, string>()

type Event = Readonly<Record<string, unknown>>
type Field = { readonly state: "available"; readonly value: unknown } | { readonly state: "omitted"; readonly reason: string }

const nextSequence = () => ++sequence

export function snapshot(value: unknown): Field {
  const seen = new Set<object>()
  let nodes = 0
  const copy = (value: unknown, depth: number): unknown => {
    if (++nodes > 10000 || depth > 32) throw new Error("snapshot_limit")
    if (value === null || typeof value === "boolean" || typeof value === "string") return value
    if (typeof value === "number" && Number.isFinite(value)) return value
    if (!value || typeof value !== "object") throw new Error("non_json_value")
    if (seen.has(value)) throw new Error("cyclic_value")
    if (!Array.isArray(value) && Object.getPrototypeOf(value) !== Object.prototype && Object.getPrototypeOf(value) !== null)
      throw new Error("non_plain_value")
    seen.add(value)
    const descriptors = Object.getOwnPropertyDescriptors(value)
    const result: Record<string, unknown> | unknown[] = Array.isArray(value) ? [] : Object.create(null)
    for (const key of Reflect.ownKeys(descriptors)) {
      if (Array.isArray(value) && key === "length") continue
      if (typeof key !== "string") throw new Error("symbol_key")
      const property = descriptors[key]
      if (!property.enumerable || !("value" in property)) throw new Error("non_data_property")
      Object.defineProperty(result, key, { enumerable: true, value: copy(property.value, depth + 1) })
    }
    if (Array.isArray(value) && Object.keys(result).length !== value.length) throw new Error("sparse_array")
    seen.delete(value)
    return Object.freeze(result)
  }
  try {
    return Object.freeze({ state: "available", value: copy(value, 0) })
  } catch {
    return Object.freeze({ state: "omitted", reason: "unsupported_snapshot" })
  }
}

export function makeNative(context: Context, tool: string, emit: (event: Event) => Effect.Effect<void>) {
  const invocationID = crypto.randomUUID()
  const actor = Object.freeze({ agent: context.agent, session_id: context.sessionID, message_id: context.messageID })
  let lost = 0
  let unavailable = 0
  let started = false
  const send = (body: Event) => Effect.suspend(() => {
    const event = Object.freeze({
      schema: "opencode-native-observation/v1",
      sequence: nextSequence(),
      actor,
      observer_failures: lost,
      ...body,
    })
    return Effect.suspend(() => emit(event)).pipe(
      Effect.catchCause(() => Effect.sync(() => { lost++ })),
    )
  })
  const field = (value: unknown) => {
    const result = snapshot(value)
    if (result.state !== "available") unavailable++
    return result
  }
  // The same Tool.Context object is passed into the internal Code Mode tool.
  // Keep the native execute invocation only as an internal parent binding; do
  // not add observation metadata to the public tool input or plugin context.
  if (tool === "execute") nativeExecuteParents.set(context as object, invocationID)
  return {
    invocationID,
    start: (input: unknown) => Effect.suspend(() => {
      started = true
      return send({
        kind: "call_start",
        invocation_id: invocationID,
        call_id: context.id,
        tool,
        mode: "native",
        parent: null,
        input: field(input),
        boundary: "executable-input",
      })
    }),
    returned: (result: unknown) => started ? send({
      kind: "call_end",
      invocation_id: invocationID,
      call_id: context.id,
      outcome: "returned",
      result: field(result),
      boundary: "native-tool-return",
      unavailable_fields: unavailable,
    }) : Effect.void,
    threw: (error: unknown) => started ? send({
      kind: "call_end",
      invocation_id: invocationID,
      call_id: context.id,
      outcome: "threw",
      error: field(error),
      error_representation: "tool-error-message-metadata/v1",
      boundary: "native-tool-error",
      unavailable_fields: unavailable,
    }) : Effect.void,
    close: () => {
      if (tool === "execute" && nativeExecuteParents.get(context as object) === invocationID)
        nativeExecuteParents.delete(context as object)
      return started
    },
  }
}

export function make(context: Context, emit: (event: Event) => Effect.Effect<void>) {
  const parent = Object.freeze({
    invocation_id: nativeExecuteParents.get(context as object) ?? crypto.randomUUID(),
    session_id: context.sessionID, message_id: context.messageID, call_id: context.id,
  })
  const actor = Object.freeze({ agent: context.agent, session_id: context.sessionID, message_id: context.messageID })
  const admitted = new Set<string>()
  const dispatched = new Set<string>()
  const ended = new Set<string>()
  let lost = 0
  let unavailable = 0
  const send = (body: Event) => Effect.suspend(() => {
    // Allocate order before the observer can await I/O. Every published object
    // owns its data; no observer gets the live tool arguments or returned object.
    const event = Object.freeze({
      schema: "opencode-local-observation/v1", sequence: nextSequence(),
      parent, actor, observer_failures: lost, ...body,
    })
    return Effect.suspend(() => emit(event)).pipe(
      Effect.catchCause(() => Effect.sync(() => { lost++ })),
    )
  })
  const field = (value: unknown) => {
    const result = snapshot(value)
    if (result.state !== "available") unavailable++
    return result
  }
  return {
    open: () => send({ kind: "parent_start", boundary: "codemode-engine", mode: "code_mode" }),
    dispatch: (call: CodeMode.ToolInvocation, registration: string, input: unknown) => Effect.suspend(() => {
      dispatched.add(call.id)
      return send({ kind: "call_start", invocation_id: call.id, tool: registration,
        catalog_path: call.name, input: field(input), boundary: "executable-input" })
    }),
    hooks: (original: CodeMode.Hooks): CodeMode.Hooks => ({
      ...original,
      "tool.before": (call) => Effect.suspend(() => {
        admitted.add(call.id)
        return original["tool.before"]?.(call) ?? Effect.void
      }),
      "tool.after": (call, result) => Effect.andThen(
        original["tool.after"]?.(call, result) ?? Effect.void,
        Effect.suspend(() => {
          ended.add(call.id)
          const base = { kind: "call_end", invocation_id: call.id,
            dispatched: dispatched.has(call.id), boundary: "codemode-json-return" }
          if (result.status === "success") return send({ ...base, outcome: "returned", result: field(result.value) })
          if (result.status === "interrupted") return send({ ...base, outcome: "interrupted" })
          return send({ ...base, outcome: "threw", error: field(CodeMode.callerError(result.error)),
            error_representation: "codemode-catch-name-message/v1" })
        }),
      ),
    }),
    close: () => send({ kind: "parent_end", admitted: admitted.size, dispatched: dispatched.size,
      terminals: ended.size, missing_terminals: [...admitted].filter((id) => !ended.has(id)).length,
      unsupported_dispatches: [...admitted].filter((id) => !dispatched.has(id)).length,
      unavailable_fields: unavailable, scope: "one-codemode-engine-invocation",
      evidence_eligible: false }),
  }
}
