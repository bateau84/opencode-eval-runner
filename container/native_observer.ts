import { appendFileSync, mkdirSync, writeFileSync } from "node:fs"
import { dirname } from "node:path"

const PATH = "/tmp/runtime/native-tool-observer.jsonl"
const SCHEMA = "opencode-eval-runner/native-tool-observer-event/v1"
const MAX_FIELD_BYTES = 256 * 1024

let sequence = 0
let starts = 0
let terminals = 0
let observerFailures = 0
let unavailableFields = 0

type Identity = {
  tool: string
  sessionID: string
  agent: string
  messageID: string
  callID: string
}

const active = new Map<string, Identity>()

function key(sessionID: string, messageID: string, callID: string) {
  return [sessionID, messageID, callID].join("\u0000")
}

function snapshot(value: unknown): { state: "available"; value: unknown } | { state: "omitted"; reason: string } {
  const seen = new Set<object>()
  let nodes = 0
  const copy = (item: unknown, depth: number): unknown => {
    if (++nodes > 10000 || depth > 32) throw new Error("snapshot_limit")
    if (item === null || typeof item === "string" || typeof item === "boolean") return item
    if (typeof item === "number" && Number.isFinite(item)) return item
    if (!item || typeof item !== "object") throw new Error("non_json_value")
    if (seen.has(item)) throw new Error("cyclic_value")
    const proto = Object.getPrototypeOf(item)
    if (!Array.isArray(item) && proto !== Object.prototype && proto !== null) throw new Error("non_plain_value")
    seen.add(item)
    const descriptors = Object.getOwnPropertyDescriptors(item)
    const result: Record<string, unknown> | unknown[] = Array.isArray(item) ? [] : Object.create(null)
    for (const property of Reflect.ownKeys(descriptors)) {
      if (Array.isArray(item) && property === "length") continue
      if (typeof property !== "string") throw new Error("symbol_key")
      const descriptor = descriptors[property]
      if (!descriptor.enumerable || !("value" in descriptor)) throw new Error("non_data_property")
      Object.defineProperty(result, property, { enumerable: true, value: copy(descriptor.value, depth + 1) })
    }
    if (Array.isArray(item) && Object.keys(result).length !== item.length) throw new Error("sparse_array")
    seen.delete(item)
    return result
  }

  try {
    const copied = copy(value, 0)
    if (Buffer.byteLength(JSON.stringify(copied), "utf8") > MAX_FIELD_BYTES) {
      return { state: "omitted", reason: "field_limit" }
    }
    return { state: "available", value: copied }
  } catch {
    return { state: "omitted", reason: "unsupported_snapshot" }
  }
}

function field(value: unknown) {
  const result = snapshot(value)
  if (result.state !== "available") unavailableFields++
  return result
}

function write(record: Record<string, unknown>) {
  const event = { schema: SCHEMA, sequence: sequence++, observer_failures: observerFailures, ...record }
  try {
    appendFileSync(PATH, JSON.stringify(event) + "\n", { encoding: "utf8" })
  } catch {
    observerFailures++
  }
}

function terminal(event: any) {
  if (event?.type !== "session.tool.success" && event?.type !== "session.tool.failed") return
  const data = event.data
  if (
    !data ||
    typeof data.sessionID !== "string" ||
    typeof data.assistantMessageID !== "string" ||
    typeof data.id !== "string"
  ) {
    observerFailures++
    return
  }

  const current = active.get(key(data.sessionID, data.assistantMessageID, data.id))
  if (!current) return
  active.delete(key(data.sessionID, data.assistantMessageID, data.id))
  terminals++

  const common = {
    kind: "call_terminal",
    tool: current.tool,
    session_id: data.sessionID,
    agent: current.agent,
    message_id: data.assistantMessageID,
    call_id: data.id,
    boundary: event.type,
  }
  if (event.type === "session.tool.success") {
    write({
      ...common,
      outcome: "success",
      result: field({
        content: data.content,
        ...(data.metadata === undefined ? {} : { metadata: data.metadata }),
        executed: data.executed,
        ...(data.resultState === undefined ? {} : { result_state: data.resultState }),
      }),
    })
    return
  }
  write({ ...common, outcome: "failure", error: field(data.error) })
}

export default {
  id: "eval-native-observer",
  async setup(ctx: any) {
    try {
      mkdirSync(dirname(PATH), { recursive: true })
      writeFileSync(PATH, "", { encoding: "utf8" })
    } catch {
      observerFailures++
    }

    write({
      kind: "capture_start",
      version: 1,
      source: "stock-opencode-2.0.23-plugin",
      input_boundary: "decoded-tool-execute",
      terminal_boundary: "session.tool.success+session.tool.failed",
      correlation: "session-message-call-id",
      ordering: "observer-monotonic-sequence",
    })

    const controller = new AbortController()
    const eventTask = (async () => {
      try {
        for await (const event of ctx.event.subscribe({ signal: controller.signal })) terminal(event)
      } catch {
        if (!controller.signal.aborted) observerFailures++
      }
    })()

    await ctx.tool.transform((editor: any) => {
      for (const item of editor.list()) {
        if (item.options?.codemode !== false) continue
        editor.update(item.id, (tool: any) => {
          const execute = tool.execute
          tool.execute = async (input: unknown, context: any) => {
            const identity: Identity = {
              tool: item.id,
              sessionID: context.sessionID,
              agent: context.agent,
              messageID: context.messageID,
              callID: context.id,
            }
            const identityKey = key(identity.sessionID, identity.messageID, identity.callID)
            starts++
            if (active.has(identityKey)) observerFailures++
            active.set(identityKey, identity)
            write({
              kind: "call_start",
              tool: identity.tool,
              session_id: identity.sessionID,
              agent: identity.agent,
              message_id: identity.messageID,
              call_id: identity.callID,
              input: field(input),
              boundary: "decoded-tool-execute",
            })
            return await execute(input, context)
          }
        })
      }
    })

    return async () => {
      // Session terminal events are published before the step can finish. Give
      // the already-running local subscriber one turn to consume queued events,
      // then close it without letting observer failure affect product behavior.
      await new Promise<void>((resolve) => setTimeout(resolve, 0))
      controller.abort()
      await eventTask
      write({
        kind: "capture_end",
        calls_started: starts,
        calls_terminal: terminals,
        outstanding_calls: active.size,
        observer_failures: observerFailures,
        unavailable_fields: unavailableFields,
      })
    }
  },
}
