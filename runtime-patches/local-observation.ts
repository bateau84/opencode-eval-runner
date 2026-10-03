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
type Field =
  | { readonly state: "available"; readonly value: unknown }
  | { readonly state: "omitted"; readonly reason: string }

type NativeState = {
  readonly invocationID: string
  readonly context: Context
  readonly tool: string
  readonly actor: Readonly<{ agent: string; session_id: string; message_id: string }>
  readonly emit: (event: Event) => Effect.Effect<void>
  lost: number
  unavailable: number
}

const nativeStates = new Map<string, NativeState>()

const nextSequence = () => ++sequence
const nativeKey = (sessionID: string, messageID: string, callID: string) =>
  [sessionID, messageID, callID].join("\u0000")

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

const sendNative = (state: NativeState, body: Event) =>
  Effect.suspend(() => {
    const event = Object.freeze({
      schema: "opencode-native-observation/v2",
      sequence: nextSequence(),
      actor: state.actor,
      observer_failures: state.lost,
      ...body,
    })
    return Effect.suspend(() => state.emit(event)).pipe(
      Effect.catchCause(() => Effect.sync(() => { state.lost++ })),
    )
  })

const nativeField = (state: NativeState, value: unknown) => {
  const result = snapshot(value)
  if (result.state !== "available") state.unavailable++
  return result
}

/**
 * Begin observation only after Tool runtime input decoding succeeds.
 *
 * The terminal is deliberately NOT emitted here: the canonical native result
 * crosses ToolOutput.truncate and SessionEvent publication later in the Step
 * writer. finishNative() is called at that final session-owned boundary.
 */
export function makeNative(context: Context, tool: string, emit: (event: Event) => Effect.Effect<void>) {
  const invocationID = crypto.randomUUID()
  const key = nativeKey(context.sessionID, context.messageID, context.id)
  const state: NativeState = {
    invocationID,
    context,
    tool,
    actor: Object.freeze({ agent: context.agent, session_id: context.sessionID, message_id: context.messageID }),
    emit,
    lost: 0,
    unavailable: 0,
  }
  let started = false
  return {
    invocationID,
    start: (input: unknown) =>
      Effect.suspend(() => {
        // Duplicate runtime call identity is a diagnostic capture defect, not
        // permission to perturb the real tool execution. Leave it unsupported.
        if (nativeStates.has(key)) return Effect.void
        started = true
        nativeStates.set(key, state)
        // The same Context object reaches the Code Mode outer tool.
        if (tool === "execute") nativeExecuteParents.set(context as object, invocationID)
        return sendNative(state, {
          kind: "call_start",
          invocation_id: invocationID,
          call_id: context.id,
          tool,
          mode: "native",
          parent: null,
          input: nativeField(state, input),
          boundary: "executable-input",
        })
      }),
    started: () => started,
  }
}

/**
 * Emit the native terminal after the normal Session writer has published the
 * same canonical result/error. Missing starts remain non-events, never invented
 * terminals.
 */
export function finishNative(input: {
  readonly sessionID: string
  readonly messageID: string
  readonly callID: string
  readonly outcome: "returned" | "threw"
  readonly value: unknown
  readonly errorRepresentation?: string
}) {
  const key = nativeKey(input.sessionID, input.messageID, input.callID)
  const state = nativeStates.get(key)
  if (!state) return Effect.void
  nativeStates.delete(key)
  if (state.tool === "execute" && nativeExecuteParents.get(state.context as object) === state.invocationID)
    nativeExecuteParents.delete(state.context as object)
  const terminalField = nativeField(state, input.value)
  const common = {
    kind: "call_end",
    invocation_id: state.invocationID,
    call_id: input.callID,
    boundary: "session-tool-terminal",
    unavailable_fields: state.unavailable,
  }
  return input.outcome === "returned"
    ? sendNative(state, { ...common, outcome: "returned", result: terminalField })
    : sendNative(state, {
        ...common,
        outcome: "threw",
        error: terminalField,
        error_representation: input.errorRepresentation ?? "session-error/v1",
      })
}

export function make(context: Context, emit: (event: Event) => Effect.Effect<void>) {
  const parent = Object.freeze({
    invocation_id: nativeExecuteParents.get(context as object) ?? crypto.randomUUID(),
    session_id: context.sessionID,
    message_id: context.messageID,
    call_id: context.id,
  })
  const actor = Object.freeze({ agent: context.agent, session_id: context.sessionID, message_id: context.messageID })
  const admitted = new Set<string>()
  const dispatched = new Set<string>()
  const ended = new Set<string>()
  let lost = 0
  let unavailable = 0
  const send = (body: Event) =>
    Effect.suspend(() => {
      const event = Object.freeze({
        schema: "opencode-local-observation/v1",
        sequence: nextSequence(),
        parent,
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
  return {
    open: () => send({ kind: "parent_start", boundary: "codemode-engine", mode: "code_mode" }),
    dispatch: (call: CodeMode.ToolInvocation, registration: string, input: unknown) =>
      Effect.suspend(() => {
        dispatched.add(call.id)
        return send({
          kind: "call_start",
          invocation_id: call.id,
          tool: registration,
          catalog_path: call.name,
          input: field(input),
          boundary: "executable-input",
        })
      }),
    hooks: (original: CodeMode.Hooks): CodeMode.Hooks => ({
      ...original,
      "tool.before": (call) =>
        Effect.suspend(() => {
          admitted.add(call.id)
          return original["tool.before"]?.(call) ?? Effect.void
        }),
      "tool.after": (call, result) =>
        Effect.andThen(
          original["tool.after"]?.(call, result) ?? Effect.void,
          Effect.suspend(() => {
            ended.add(call.id)
            const base = {
              kind: "call_end",
              invocation_id: call.id,
              dispatched: dispatched.has(call.id),
              boundary: "codemode-json-return",
            }
            if (result.status === "success")
              return send({ ...base, outcome: "returned", result: field(result.value) })
            if (result.status === "interrupted") return send({ ...base, outcome: "interrupted" })
            return send({
              ...base,
              outcome: "threw",
              error: field(CodeMode.callerError(result.error)),
              error_representation: "codemode-catch-name-message/v1",
            })
          }),
        ),
    }),
    close: () =>
      send({
        kind: "parent_end",
        admitted: admitted.size,
        dispatched: dispatched.size,
        terminals: ended.size,
        missing_terminals: [...admitted].filter((id) => !ended.has(id)).length,
        unsupported_dispatches: [...admitted].filter((id) => !dispatched.has(id)).length,
        unavailable_fields: unavailable,
        scope: "one-codemode-engine-invocation",
        evidence_eligible: false,
      }),
  }
}
