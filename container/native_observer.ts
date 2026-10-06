import { randomUUID } from "node:crypto"
import { createConnection } from "node:net"

const OBSERVER_STREAM_ENV = "OPENCODE_EVAL_OBSERVER_STREAM"
const SCHEMA = "opencode-eval-runner/runtime-observer-event/v1"
const FIELD_LIMIT = 256 * 1024
const MAX_DEPTH = 32
const MAX_NODES = 20_000

let sequence = 0
let nativeStarts = 0
let nativeTerminals = 0
let codeStarts = 0
let codeTerminals = 0
let observerFailures = 0
let callbackFailures = 0
let unavailableFields = 0

const CODE_FINALITY_REASON = "stock_codemode_final_boundary_not_exposed"
const CREDENTIALS_ENV = "OPENCODE_EVAL_OBSERVER_CREDENTIALS"
const INVENTORY_ENV = "OPENCODE_EVAL_OBSERVER_CREDENTIALS_COMPLETE"

const rawStreamEndpoint = process.env[OBSERVER_STREAM_ENV] ?? ""
delete process.env[OBSERVER_STREAM_ENV]
const streamMatch = /^127\.0\.0\.1:(\d+)$/.exec(rawStreamEndpoint)
const captureSocket = streamMatch
  ? createConnection({ host: "127.0.0.1", port: Number(streamMatch[1]) })
  : null
if (captureSocket) {
  captureSocket.on("error", () => {
    observerFailures += 1
  })
  captureSocket.unref()
}

type Field =
  | { state: "available"; value: unknown }
  | { state: "redacted" | "omitted"; reason: string }

type Identity = {
  invocationID: string
  tool: string
  sessionID: string
  agent: string
  messageID: string
  callID: string
}

const nativeActive = new Map<string, Identity>()
const activeOuter = new Map<string, string>()
const wrapped = new WeakSet<Function>()

function identityKey(value: { sessionID: string; messageID: string; callID?: string; id?: string }) {
  return [value.sessionID, value.messageID, value.callID ?? value.id ?? ""].join("\u0000")
}

function nativeInvocationID() {
  return "native:" + randomUUID()
}

function sensitiveKey(key: string) {
  const snake = key
    .replace(/([A-Z]+)([A-Z][a-z])/g, "$1_$2")
    .replace(/([a-z0-9])([A-Z])/g, "$1_$2")
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "_")
  return (
    ["key", "apikey", "api_key", "access", "refresh", "token"].includes(snake) ||
    snake.endsWith("_key") ||
    snake.endsWith("_token") ||
    ["secret", "password", "credential", "authorization", "cookie"].some(
      (value) => snake === value || snake.endsWith("_" + value),
    )
  )
}

let inventoryComplete = process.env[INVENTORY_ENV] === "1"
let credentials: string[] = []
try {
  const parsed = JSON.parse(process.env[CREDENTIALS_ENV] ?? "[]")
  if (!Array.isArray(parsed) || parsed.some((value) => typeof value !== "string")) {
    inventoryComplete = false
  } else {
    credentials = [...new Set(parsed.filter(Boolean))]
  }
} catch {
  inventoryComplete = false
}

const variants = new Set<string>(credentials)
let frontier = new Set<string>(credentials)
for (let depth = 0; depth < 3; depth++) {
  const generated = new Set<string>()
  for (const value of frontier) {
    const encoded = JSON.stringify(value).slice(1, -1)
    if (!variants.has(encoded)) generated.add(encoded)
  }
  for (const value of generated) variants.add(value)
  frontier = generated
}
const credentialVariants = [...variants].sort((a, b) => b.length - a.length)

class ProjectionFailure extends Error {
  constructor(
    readonly state: "redacted" | "omitted",
    readonly reason: string,
  ) {
    super(reason)
  }
}

function containsCredential(value: string) {
  return credentialVariants.some((credential) => credential && value.includes(credential))
}

function copySafe(value: unknown, depth: number, seen: Set<object>, budget: { nodes: number }): unknown {
  budget.nodes += 1
  if (depth > MAX_DEPTH || budget.nodes > MAX_NODES) {
    throw new ProjectionFailure("omitted", "unsupported_representation")
  }
  if (value === null || typeof value === "boolean") return value
  if (typeof value === "string") {
    if (containsCredential(value)) throw new ProjectionFailure("redacted", "credential_match")
    return value
  }
  if (typeof value === "number") {
    if (!Number.isFinite(value)) throw new ProjectionFailure("omitted", "unsupported_representation")
    if (credentials.includes(JSON.stringify(value))) {
      throw new ProjectionFailure("redacted", "credential_match")
    }
    return value
  }
  if (!value || typeof value !== "object") {
    throw new ProjectionFailure("omitted", "unsupported_representation")
  }
  if (seen.has(value)) throw new ProjectionFailure("omitted", "unsupported_representation")
  const proto = Object.getPrototypeOf(value)
  if (!Array.isArray(value) && proto !== Object.prototype && proto !== null) {
    throw new ProjectionFailure("omitted", "unsupported_representation")
  }
  seen.add(value)
  try {
    if (Array.isArray(value)) {
      return value.map((item) => copySafe(item, depth + 1, seen, budget))
    }
    const result: Record<string, unknown> = Object.create(null)
    for (const [key, item] of Object.entries(value)) {
      if (sensitiveKey(key) || containsCredential(key)) {
        throw new ProjectionFailure("omitted", "sensitive_key")
      }
      result[key] = copySafe(item, depth + 1, seen, budget)
    }
    return result
  } finally {
    seen.delete(value)
  }
}

function project(value: unknown): Field {
  if (!inventoryComplete) {
    unavailableFields += 1
    return { state: "omitted", reason: "credential_inventory_unavailable" }
  }
  try {
    const safe = copySafe(value, 0, new Set<object>(), { nodes: 0 })
    if (Buffer.byteLength(JSON.stringify(safe), "utf8") > FIELD_LIMIT) {
      unavailableFields += 1
      return { state: "omitted", reason: "size_limit" }
    }
    return { state: "available", value: safe }
  } catch (error) {
    unavailableFields += 1
    if (error instanceof ProjectionFailure) {
      return { state: error.state, reason: error.reason }
    }
    return { state: "omitted", reason: "unsupported_representation" }
  }
}

function write(record: Record<string, unknown>) {
  const event = {
    schema: SCHEMA,
    sequence: sequence++,
    observer_failures: observerFailures,
    callback_failures: callbackFailures,
    ...record,
  }
  if (!captureSocket || captureSocket.destroyed) {
    observerFailures += 1
    return
  }
  try {
    captureSocket.write(JSON.stringify(event) + "\n")
    if (record.kind === "capture_end") captureSocket.end()
  } catch {
    observerFailures += 1
  }
}

async function parentSession(ctx: any, sessionID: string): Promise<Field> {
  try {
    const session = await ctx.session.get({ sessionID })
    const parentID = session?.parentID
    return {
      state: "available",
      value: typeof parentID === "string" && parentID ? parentID : null,
    }
  } catch {
    callbackFailures += 1
    unavailableFields += 1
    return { state: "omitted", reason: "session_parent_unavailable" }
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
    callbackFailures += 1
    return
  }

  const key = identityKey({
    sessionID: data.sessionID,
    messageID: data.assistantMessageID,
    callID: data.id,
  })
  const current = nativeActive.get(key)
  if (!current) return
  nativeActive.delete(key)
  nativeTerminals += 1

  const common = {
    kind: "native_terminal",
    invocation_id: current.invocationID,
    tool: project(current.tool),
    session_id: project(current.sessionID),
    agent: project(current.agent),
    message_id: project(current.messageID),
    call_id: project(current.callID),
    boundary: event.type,
  }
  if (event.type === "session.tool.success") {
    write({
      ...common,
      outcome: "success",
      result: project({
        content: data.content,
        ...(data.metadata === undefined ? {} : { metadata: data.metadata }),
        ...(data.executed === undefined ? {} : { executed: data.executed }),
        ...(data.resultState === undefined ? {} : { result_state: data.resultState }),
      }),
    })
    return
  }
  write({ ...common, outcome: "error", error: project(data.error) })
}

export default {
  id: "eval-runtime-observer",
  async setup(ctx: any) {
    write({
      kind: "capture_start",
      version: 1,
      source: "stock-opencode-2.0.23-plugin",
      native_input_boundary: "decoded-tool-execute+outer-execute-before",
      native_terminal_boundary: "session.tool.success+session.tool.failed",
      code_input_boundary: "decoded-code-tool-handler",
      code_terminal_boundary: "tool-handler-return+tool-handler-throw",
      code_finality: "unsupported",
      code_finality_reason: CODE_FINALITY_REASON,
      correlation: "identity-not-input-or-fifo",
      ordering: "observer-monotonic-sequence",
    })

    const controller = new AbortController()
    const eventTask = (async () => {
      try {
        for await (const event of ctx.event.subscribe({ signal: controller.signal })) {
          terminal(event)
        }
      } catch {
        if (!controller.signal.aborted) callbackFailures += 1
      }
    })()

    await ctx.tool.transform((editor: any) => {
      for (const item of editor.list()) {
        if (wrapped.has(item.execute)) continue

        if (item.options?.codemode === false) {
          editor.update(item.id, (tool: any) => {
            const execute = tool.execute
            const observed = async (input: unknown, context: any) => {
              const identity: Identity = {
                invocationID: nativeInvocationID(),
                tool: item.id,
                sessionID: context.sessionID,
                agent: context.agent,
                messageID: context.messageID,
                callID: context.id,
              }
              const key = identityKey(identity)
              nativeStarts += 1
              if (nativeActive.has(key)) observerFailures += 1
              nativeActive.set(key, identity)
              if (item.id === "execute") activeOuter.set(key, identity.invocationID)

              write({
                kind: "native_start",
                invocation_id: identity.invocationID,
                tool: project(identity.tool),
                session_id: project(identity.sessionID),
                agent: project(identity.agent),
                message_id: project(identity.messageID),
                call_id: project(identity.callID),
                parent_session_id: await parentSession(ctx, identity.sessionID),
                input: project(input),
                boundary: "decoded-tool-execute",
              })
              try {
                return await execute(input, context)
              } finally {
                if (item.id === "execute") activeOuter.delete(key)
              }
            }
            wrapped.add(observed)
            tool.execute = observed
          })
          continue
        }

        editor.update(item.id, (tool: any) => {
          const execute = tool.execute
          const observed = async (input: unknown, context: any) => {
            const key = identityKey({
              sessionID: context.sessionID,
              messageID: context.messageID,
              callID: context.id,
            })
            const parentInvocationID = activeOuter.get(key)
            if (!parentInvocationID) return await execute(input, context)

            const invocationID = "code:" + randomUUID()
            codeStarts += 1
            write({
              kind: "code_start",
              invocation_id: invocationID,
              tool: project(item.id),
              session_id: project(context.sessionID),
              agent: project(context.agent),
              message_id: project(context.messageID),
              call_id: project(context.id),
              parent_invocation_id: parentInvocationID,
              input: project(input),
              boundary: "decoded-code-tool-handler",
            })
            try {
              const result = await execute(input, context)
              codeTerminals += 1
              write({
                kind: "code_terminal",
                invocation_id: invocationID,
                tool: project(item.id),
                session_id: project(context.sessionID),
                agent: project(context.agent),
                message_id: project(context.messageID),
                call_id: project(context.id),
                outcome: "success",
                boundary: "tool-handler-return",
                finality: {
                  state: "unsupported",
                  reason: CODE_FINALITY_REASON,
                },
              })
              return result
            } catch (error) {
              codeTerminals += 1
              write({
                kind: "code_terminal",
                invocation_id: invocationID,
                tool: project(item.id),
                session_id: project(context.sessionID),
                agent: project(context.agent),
                message_id: project(context.messageID),
                call_id: project(context.id),
                outcome: "error",
                boundary: "tool-handler-throw",
                finality: {
                  state: "unsupported",
                  reason: CODE_FINALITY_REASON,
                },
              })
              throw error
            }
          }
          wrapped.add(observed)
          tool.execute = observed
        })
      }
    })

    // The synthetic Code Mode execute tool is created inside Tool.snapshot,
    // after registration transforms have run. Observe that real model-facing
    // invocation at the stock execute.before runtime hook so it cannot vanish
    // from the native boundary. This is an exact observed effective input, but
    // unlike transformed registered tools it is before CodeMode.Input decode.
    await ctx.tool.hook("execute.before", async (event: any) => {
      if (event?.tool !== "execute") return
      if (
        typeof event.sessionID !== "string" ||
        typeof event.agent !== "string" ||
        typeof event.messageID !== "string" ||
        typeof event.id !== "string"
      ) {
        callbackFailures += 1
        return
      }

      const identity: Identity = {
        invocationID: nativeInvocationID(),
        tool: "execute",
        sessionID: event.sessionID,
        agent: event.agent,
        messageID: event.messageID,
        callID: event.id,
      }
      const key = identityKey(identity)
      const existing = nativeActive.get(key)
      if (existing) {
        activeOuter.set(key, existing.invocationID)
        return
      }

      nativeStarts += 1
      nativeActive.set(key, identity)
      activeOuter.set(key, identity.invocationID)
      write({
        kind: "native_start",
        invocation_id: identity.invocationID,
        tool: project(identity.tool),
        session_id: project(identity.sessionID),
        agent: project(identity.agent),
        message_id: project(identity.messageID),
        call_id: project(identity.callID),
        parent_session_id: await parentSession(ctx, identity.sessionID),
        input: project(event.input),
        boundary: "tool-execute-before",
      })
    })
    await ctx.tool.hook("execute.after", (event: any) => {
      if (event?.tool !== "execute") return
      if (
        typeof event.sessionID === "string" &&
        typeof event.messageID === "string" &&
        typeof event.id === "string"
      ) {
        const key = identityKey({
          sessionID: event.sessionID,
          messageID: event.messageID,
          callID: event.id,
        })
        activeOuter.delete(key)
      }
    })

    return async () => {
      await new Promise<void>((resolve) => setTimeout(resolve, 0))
      controller.abort()
      await eventTask
      write({
        kind: "capture_end",
        native_starts: nativeStarts,
        native_terminals: nativeTerminals,
        code_starts: codeStarts,
        code_terminals: codeTerminals,
        observer_failures: observerFailures,
        callback_failures: callbackFailures,
        unavailable_fields: unavailableFields,
      })
    }
  },
}
