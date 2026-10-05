import net from "node:net"
import crypto from "node:crypto"

const VERSION = "opencode-eval-runner/trust001-wire/v1"
const generation = process.env.TRUST001_GENERATION ?? ""
const evidencePath = process.env.TRUST001_EVIDENCE_SOCKET ?? ""
const capabilityPath = process.env.TRUST001_CAPABILITY_SOCKET ?? ""
const preflight = process.env.TRUST001_PREFLIGHT === "1"

function requireValue(ok, message) {
  if (!ok) throw new Error(message)
}

requireValue(/^[0-9a-f]{64}$/.test(generation), "invalid TRUST001_GENERATION")
requireValue(evidencePath.startsWith("/"), "invalid TRUST001_EVIDENCE_SOCKET")
requireValue(capabilityPath.startsWith("/"), "invalid TRUST001_CAPABILITY_SOCKET")

function requestID() {
  return crypto.randomBytes(16).toString("hex")
}

function handlerID(value) {
  requireValue(typeof value === "string" && /^[0-9a-f]{32}$/.test(value), "invalid_handler_id")
  return value
}

function frame(value) {
  const raw = Buffer.from(JSON.stringify(value), "utf8")
  requireValue(raw.length > 0 && raw.length <= 256 * 1024, "frame_limit")
  const prefix = Buffer.allocUnsafe(4)
  prefix.writeUInt32BE(raw.length, 0)
  return Buffer.concat([prefix, raw])
}

class Reader {
  constructor(socket) {
    this.socket = socket
    this.buffer = Buffer.alloc(0)
    this.pending = []
  }

  next() {
    if (this.pending.length) return Promise.resolve(this.pending.shift())
    return new Promise((resolve, reject) => {
      const onError = () => cleanup(() => reject(new Error("channel_error")))
      const onClose = () => cleanup(() => reject(new Error("channel_closed")))
      const onData = (chunk) => {
        this.buffer = Buffer.concat([this.buffer, chunk])
        while (this.buffer.length >= 4) {
          const size = this.buffer.readUInt32BE(0)
          if (size < 1 || size > 256 * 1024) {
            cleanup(() => reject(new Error("frame_limit")))
            return
          }
          if (this.buffer.length < 4 + size) return
          const raw = this.buffer.subarray(4, 4 + size)
          this.buffer = this.buffer.subarray(4 + size)
          let value
          try {
            value = JSON.parse(raw.toString("utf8"))
          } catch {
            cleanup(() => reject(new Error("invalid_json")))
            return
          }
          this.pending.push(value)
        }
        if (this.pending.length) cleanup(() => resolve(this.pending.shift()))
      }
      const cleanup = (finish) => {
        this.socket.off("data", onData)
        this.socket.off("error", onError)
        this.socket.off("close", onClose)
        finish()
      }
      this.socket.on("data", onData)
      this.socket.once("error", onError)
      this.socket.once("close", onClose)
    })
  }
}

function connect(path) {
  return new Promise((resolve, reject) => {
    const socket = net.createConnection({ path })
    socket.once("connect", () => resolve(socket))
    socket.once("error", reject)
  })
}

function send(socket, value) {
  socket.write(frame(value))
}

function fixedError(error, fallback) {
  if (error instanceof Error && error.message && error.message.length <= 256) return error.message
  return fallback
}

function plainContext(tool) {
  return {
    sessionID: tool.sessionID,
    agent: tool.agent,
    messageID: tool.messageID,
    id: tool.id,
  }
}

export default {
  id: "loom",

  async setup(ctx) {
    const evidence = await connect(evidencePath)
    const capability = await connect(capabilityPath)
    const capabilityReader = new Reader(capability)
    const evidenceReader = new Reader(evidence)

    send(evidence, {
      version: VERSION,
      kind: "evidence.hello",
      generation,
      role: "bridge",
    })
    send(capability, {
      version: VERSION,
      kind: "capability.hello",
      generation,
      role: "bridge",
    })

    let sequence = 0
    let closing = false
    let closed = false
    let capabilityFailure = null
    const eventController = new AbortController()
    const pendingCallbacks = new Map()
    const activeHostRequests = new Set()
    const cancelledHostRequests = new Set()
    const proxyHandlerIDs = new WeakMap()
    const registrations = []

    const observe = (payload) => {
      if (closed) throw new Error("evidence_generation_closed")
      sequence += 1
      send(evidence, {
        version: VERSION,
        kind: "evidence.observation",
        generation,
        sequence,
        payload,
      })
    }

    const callback = (operation, payload, signal) => {
      requireValue(!closed && !closing && !capabilityFailure, "capability_unavailable")
      const id = requestID()
      return new Promise((resolve, reject) => {
        const abort = () => {
          if (!pendingCallbacks.has(id)) return
          pendingCallbacks.delete(id)
          send(capability, {
            version: VERSION,
            kind: "capability.callback.cancel",
            generation,
            request_id: id,
            reason: "interrupted",
          })
          reject(new Error("remote_callback_cancelled"))
        }
        pendingCallbacks.set(id, { resolve, reject, abort, signal })
        signal?.addEventListener("abort", abort, { once: true })
        send(capability, {
          version: VERSION,
          kind: "capability.callback.request",
          generation,
          request_id: id,
          operation,
          payload,
        })
      })
    }

    const respondHost = (message, ok, payload, error) => {
      if (cancelledHostRequests.has(message.request_id)) return
      send(capability, {
        version: VERSION,
        kind: "capability.host.response",
        generation,
        request_id: message.request_id,
        ok,
        ...(ok ? { payload } : { error }),
      })
    }

    const registerAgentTransform = async (payload) => {
      const operations = payload?.operations
      requireValue(Array.isArray(operations) && operations.length <= 16, "invalid_agent_transform")
      for (const op of operations) {
        requireValue(op && op.kind === "default" && typeof op.id === "string", "unsupported_agent_transform")
      }
      const registration = await ctx.agent.transform((editor) => {
        for (const op of operations) editor.default(op.id)
      })
      registrations.push(registration)
      return { registered: true }
    }

    const registerToolTransform = async (payload) => {
      const namespaces = payload?.namespaces ?? []
      const tools = payload?.tools ?? []
      requireValue(Array.isArray(namespaces) && namespaces.length <= 8, "invalid_tool_transform")
      requireValue(Array.isArray(tools) && tools.length <= 128, "invalid_tool_transform")
      const registration = await ctx.tool.transform((editor) => {
        for (const namespace of namespaces) {
          requireValue(
            namespace && typeof namespace.name === "string" && typeof namespace.description === "string",
            "invalid_tool_namespace",
          )
          editor.namespace(namespace)
        }
        for (const item of tools) {
          requireValue(item && typeof item.definition === "object", "invalid_tool_definition")
          const remoteHandler = handlerID(item.handler_id)
          const definition = item.definition
          requireValue(typeof definition.name === "string" && typeof definition.description === "string",
                       "invalid_tool_definition")
          requireValue(definition.input && typeof definition.input === "object", "invalid_tool_definition")
          const execute = async (input, tool) => {
            const result = await callback(
              "tool.execute",
              {
                handler_id: remoteHandler,
                input,
                context: plainContext(tool),
              },
              tool.signal,
            )
            requireValue(result && typeof result === "object", "invalid_remote_tool_result")
            return result
          }
          proxyHandlerIDs.set(execute, remoteHandler)
          editor.add({ ...definition, execute })
        }
      })
      registrations.push(registration)
      return { registered: true }
    }

    const listRemoteTools = async () => {
      const tools = await ctx.tool.list()
      return {
        tools: tools.flatMap((tool) => {
          const remoteHandler = proxyHandlerIDs.get(tool.execute)
          return remoteHandler ? [{ id: tool.id, handler_id: remoteHandler }] : []
        }),
      }
    }

    const registerToolHook = async (payload) => {
      const name = payload?.name
      const remoteHandler = handlerID(payload?.handler_id)
      requireValue(name === "execute.before" || name === "execute.after", "unsupported_tool_hook")
      const registration = await ctx.tool.hook(name, async (event) => {
        await callback(name === "execute.before" ? "tool.execute.before" : "tool.execute.after", {
          handler_id: remoteHandler,
          event,
        })
      })
      registrations.push(registration)
      return { registered: true }
    }

    const registerPermissionHook = async (payload) => {
      requireValue(payload?.name === "evaluate", "unsupported_permission_hook")
      const remoteHandler = handlerID(payload?.handler_id)
      const registration = await ctx.permission.hook("evaluate", async (event) => {
        const result = await callback("permission.evaluate", { handler_id: remoteHandler, event })
        const next = result?.event
        requireValue(next && typeof next === "object", "invalid_permission_callback")
        requireValue(["allow", "deny", "ask"].includes(next.effect), "invalid_permission_effect")
        event.effect = next.effect
        if (next.message === undefined) delete event.message
        else {
          requireValue(typeof next.message === "string", "invalid_permission_message")
          event.message = next.message
        }
      })
      registrations.push(registration)
      return { registered: true }
    }

    const registerSessionHook = async (payload) => {
      const name = payload?.name
      const remoteHandler = handlerID(payload?.handler_id)
      requireValue(name === "context" || name === "retry", "unsupported_session_hook")
      const registration = await ctx.session.hook(name, async (event) => {
        const result = await callback(name === "context" ? "session.context" : "session.retry", {
          handler_id: remoteHandler,
          event,
        })
        const next = result?.event
        requireValue(next && typeof next === "object", "invalid_session_callback")
        if (name === "context") {
          requireValue(Array.isArray(next.system), "invalid_session_context")
          event.system = next.system
        } else {
          const decision = next.decision
          requireValue(
            decision && typeof decision === "object" && typeof decision.retry === "boolean" &&
            (decision.retry === false || typeof decision.delay === "number"),
            "invalid_retry_decision",
          )
          event.decision = decision
        }
      })
      registrations.push(registration)
      return { registered: true }
    }

    const registerRpc = async (payload) => {
      const definition = payload?.definition
      const handlers = payload?.handlers
      requireValue(definition && typeof definition === "object" && typeof definition.id === "string",
                   "invalid_rpc_definition")
      requireValue(handlers && typeof handlers === "object", "invalid_rpc_handlers")
      const remoteHandlers = Object.fromEntries(
        Object.entries(handlers).map(([method, value]) => {
          const remoteHandler = handlerID(value)
          return [method, async (input) => callback("rpc.call", {
            handler_id: remoteHandler,
            method,
            input,
          })]
        }),
      )
      const registration = await ctx.rpc.register(definition, remoteHandlers)
      registrations.push(registration)
      return { registered: true }
    }

    const dispatchHost = async (message) => {
      requireValue(message.generation === generation, "stale_generation")
      const payload = message.payload ?? {}
      switch (message.operation) {
        case "location.get":
          return { location: ctx.location }
        case "storage.get": {
          requireValue(typeof payload.key === "string" && payload.key.length <= 4096, "invalid_storage_key")
          const value = await ctx.storage.get(payload.key)
          return value === undefined ? { present: false } : { present: true, value }
        }
        case "storage.set":
          requireValue(typeof payload.key === "string" && payload.key.length <= 4096, "invalid_storage_key")
          await ctx.storage.set(payload.key, payload.value)
          return { stored: true }
        case "storage.scan": {
          requireValue(typeof payload.prefix === "string" && payload.prefix.length <= 4096, "invalid_storage_prefix")
          const limit = payload.limit === undefined ? undefined : payload.limit
          requireValue(limit === undefined || Number.isInteger(limit) && limit >= 1 && limit <= 1000,
                       "invalid_storage_limit")
          requireValue(payload.after === undefined || typeof payload.after === "string", "invalid_storage_after")
          return await ctx.storage.scan({
            prefix: payload.prefix,
            ...(limit === undefined ? {} : { limit }),
            ...(payload.after === undefined ? {} : { after: payload.after }),
          })
        }
        case "agent.list":
          return await ctx.agent.list(payload.input)
        case "agent.transform.register":
          return await registerAgentTransform(payload)
        case "tool.transform.register":
          return await registerToolTransform(payload)
        case "tool.list":
          return await listRemoteTools()
        case "tool.hook.register":
          return await registerToolHook(payload)
        case "permission.hook.register":
          return await registerPermissionHook(payload)
        case "session.hook.register":
          return await registerSessionHook(payload)
        case "session.get":
          return { value: await ctx.session.get(payload.input) }
        case "session.context":
          return { value: await ctx.session.context(payload.input) }
        case "session.synthetic":
          return { value: await ctx.session.synthetic(payload.input) }
        case "rpc.register":
          return await registerRpc(payload)
        default:
          throw new Error("operation_not_admitted")
      }
    }

    const capabilityLoop = (async () => {
      try {
        while (!closed) {
          const message = await capabilityReader.next()
          requireValue(message?.version === VERSION, "wrong_version")
          requireValue(message?.generation === generation, "stale_generation")
          if (message.kind === "capability.callback.response") {
            const pending = pendingCallbacks.get(message.request_id)
            requireValue(pending, "unknown_or_late_response")
            pendingCallbacks.delete(message.request_id)
            pending.signal?.removeEventListener("abort", pending.abort)
            if (message.ok === true) pending.resolve(message.payload)
            else pending.reject(new Error(fixedError(message.error, "remote_callback_failed")))
            continue
          }
          if (message.kind === "capability.host.cancel") {
            cancelledHostRequests.add(message.request_id)
            continue
          }
          requireValue(message.kind === "capability.host.request", "capability_direction_violation")
          if (closing) {
            capabilityFailure = capabilityFailure ?? "post_close_request"
            respondHost(message, false, undefined, "generation_closing")
            continue
          }
          const id = message.request_id
          requireValue(typeof id === "string" && /^[0-9a-f]{32}$/.test(id), "invalid_request_id")
          requireValue(!activeHostRequests.has(id) && !cancelledHostRequests.has(id), "duplicate_request")
          activeHostRequests.add(id)
          void dispatchHost(message).then(
            (result) => respondHost(message, true, result),
            (error) => respondHost(message, false, undefined, fixedError(error, "host_operation_failed")),
          ).finally(() => activeHostRequests.delete(id))
        }
      } catch (error) {
        if (!closed) {
          capabilityFailure = fixedError(error, "capability_channel_failed")
          for (const pending of pendingCallbacks.values()) {
            pending.reject(new Error("capability_channel_failed"))
          }
          pendingCallbacks.clear()
        }
      }
    })()

    observe({
      type: "bridge.activated",
      implementation: "trust001-bridge",
      plugin: "loom",
      opencode: ctx.app?.version ?? null,
      location: {
        directory: ctx.location?.directory ?? null,
        workspaceID: ctx.location?.workspaceID ?? null,
      },
    })

    const eventTask = (async () => {
      try {
        for await (const event of ctx.event.subscribe({ signal: eventController.signal })) {
          observe({ type: "opencode.event", event })
        }
      } catch {
        if (!eventController.signal.aborted) capabilityFailure = capabilityFailure ?? "event_stream_failed"
      }
    })()

    const closeGeneration = async () => {
      if (closed || closing) return
      closing = true
      eventController.abort()
      await eventTask.catch(() => undefined)
      const eligible =
        !capabilityFailure &&
        pendingCallbacks.size === 0 &&
        activeHostRequests.size === 0
      if (eligible) {
        send(evidence, {
          version: VERSION,
          kind: "evidence.seal",
          generation,
          final_sequence: sequence,
        })
      } else {
        capabilityFailure = capabilityFailure ?? "close_with_outstanding_work"
      }
      closed = true
      capability.end()
      evidence.end()
    }

    const evidenceControlTask = (async () => {
      try {
        const message = await evidenceReader.next()
        requireValue(message?.version === VERSION, "wrong_evidence_control_version")
        requireValue(message?.generation === generation, "stale_evidence_control_generation")
        requireValue(message?.kind === "evidence.close", "unexpected_evidence_control")
        await closeGeneration()
      } catch {
        if (!closed) {
          capabilityFailure = capabilityFailure ?? "evidence_control_failed"
          closed = true
          capability.destroy()
          evidence.destroy()
        }
      }
    })()

    if (preflight) {
      const response = await callback("trust001.preflight.ping", { value: "ping" })
      requireValue(response?.value === "pong", "invalid_preflight_response")
      observe({ type: "capability.preflight", result: "pong" })
    }

    return async () => {
      if (!closed) {
        eventController.abort()
        await eventTask.catch(() => undefined)
        closed = true
        capability.end()
        evidence.end()
      }
      await capabilityLoop.catch(() => undefined)
      await evidenceControlTask.catch(() => undefined)
    }
  },
}
