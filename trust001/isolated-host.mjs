import net from "node:net"
import crypto from "node:crypto"
import { pathToFileURL } from "node:url"

const VERSION = "opencode-eval-runner/trust001-wire/v1"
const generation = process.env.TRUST001_GENERATION ?? ""
const capabilityPath = process.env.TRUST001_CAPABILITY_SOCKET ?? ""
const loomEntrypoint = process.env.TRUST001_LOOM_ENTRYPOINT ?? ""

function requireValue(ok, code) {
  if (!ok) throw new Error(code)
}

requireValue(/^[0-9a-f]{64}$/.test(generation), "invalid_generation")
requireValue(capabilityPath.startsWith("/"), "invalid_capability_socket")
requireValue(loomEntrypoint.startsWith("/"), "invalid_loom_entrypoint")

function requestID() {
  return crypto.randomBytes(16).toString("hex")
}

function handlerID() {
  return crypto.randomBytes(16).toString("hex")
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

function fixedError(error) {
  if (error instanceof Error && error.message) return error.message.slice(0, 256)
  return "remote_handler_failed"
}

function clone(value) {
  if (value === undefined) return undefined
  return JSON.parse(JSON.stringify(value))
}

async function main() {
  const socket = await connect(capabilityPath)
  const reader = new Reader(socket)
  const pendingHost = new Map()
  const callbacks = new Map()
  const activeCallbacks = new Map()
  let closed = false
  let loopFailure = null

  send(socket, {
    version: VERSION,
    kind: "capability.hello",
    generation,
    role: "loom",
  })

  const callHost = (operation, payload) => {
    requireValue(!closed && !loopFailure, "capability_unavailable")
    const id = requestID()
    return new Promise((resolve, reject) => {
      pendingHost.set(id, { resolve, reject })
      send(socket, {
        version: VERSION,
        kind: "capability.host.request",
        generation,
        request_id: id,
        operation,
        payload,
      })
    })
  }

  const remember = (handler) => {
    requireValue(typeof handler === "function", "invalid_handler")
    const id = handlerID()
    callbacks.set(id, handler)
    return id
  }

  const callbackResult = async (message) => {
    const operation = message.operation
    if (operation === "trust001.preflight.ping") {
      return { value: "pong" }
    }

    const id = message.payload?.handler_id
    requireValue(typeof id === "string" && callbacks.has(id), "unknown_handler")
    const handler = callbacks.get(id)
    const controller = new AbortController()
    activeCallbacks.set(message.request_id, controller)
    try {
      if (operation === "tool.execute") {
        const ctx = {
          ...message.payload.context,
          signal: controller.signal,
          progress: async () => undefined,
        }
        return await handler(message.payload.input, ctx)
      }
      if (operation === "rpc.call") {
        return await handler(message.payload.input, {
          signal: controller.signal,
          error: (type, text, data) => ({ type, message: text, data }),
        })
      }
      if ([
        "tool.execute.before",
        "tool.execute.after",
        "permission.evaluate",
        "session.context",
        "session.retry",
      ].includes(operation)) {
        const event = message.payload.event
        await handler(event)
        return { event }
      }
      throw new Error("operation_not_admitted")
    } finally {
      activeCallbacks.delete(message.request_id)
    }
  }

  const loop = (async () => {
    try {
      while (!closed) {
        const message = await reader.next()
        requireValue(message?.version === VERSION, "wrong_version")
        requireValue(message?.generation === generation, "stale_generation")

        if (message.kind === "capability.host.response") {
          const pending = pendingHost.get(message.request_id)
          requireValue(pending, "unknown_or_late_host_response")
          pendingHost.delete(message.request_id)
          if (message.ok === true) pending.resolve(message.payload)
          else pending.reject(new Error(typeof message.error === "string" ? message.error : "host_operation_failed"))
          continue
        }

        if (message.kind === "capability.callback.cancel") {
          const controller = activeCallbacks.get(message.request_id)
          if (controller) controller.abort()
          continue
        }

        requireValue(message.kind === "capability.callback.request", "capability_direction_violation")
        void callbackResult(message).then(
          (payload) => send(socket, {
            version: VERSION,
            kind: "capability.callback.response",
            generation,
            request_id: message.request_id,
            ok: true,
            payload: payload === undefined ? null : payload,
          }),
          (error) => send(socket, {
            version: VERSION,
            kind: "capability.callback.response",
            generation,
            request_id: message.request_id,
            ok: false,
            error: fixedError(error),
          }),
        )
      }
    } catch (error) {
      if (!closed && error instanceof Error && error.message === "channel_closed" && pendingHost.size === 0) {
        closed = true
        return
      }
      if (!closed) {
        loopFailure = fixedError(error)
        for (const pending of pendingHost.values()) pending.reject(new Error("capability_channel_failed"))
        pendingHost.clear()
      }
    }
  })()

  const locationReply = await callHost("location.get", {})
  const location = locationReply?.location
  requireValue(location && typeof location.directory === "string", "invalid_location")

  const storage = {
    async get(key) {
      const reply = await callHost("storage.get", { key })
      return reply?.present ? reply.value : undefined
    },
    async set(key, value) {
      await callHost("storage.set", { key, value })
    },
    async scan(input) {
      return await callHost("storage.scan", input)
    },
  }

  const agent = {
    async list(input) {
      return await callHost("agent.list", { input })
    },
    async transform(transform) {
      const snapshot = await agent.list()
      const agents = clone(snapshot?.data ?? [])
      const operations = []
      const editor = {
        list: () => agents,
        get: (id) => agents.find((item) => item?.id === id),
        default: (id) => operations.push({ kind: "default", id }),
        update: () => { throw new Error("unsupported_agent_transform_update") },
        remove: () => { throw new Error("unsupported_agent_transform_remove") },
      }
      const result = transform(editor)
      requireValue(!result || typeof result.then !== "function", "async_agent_transform_unsupported")
      await callHost("agent.transform.register", { operations })
      return { dispose: async () => undefined }
    },
  }

  const toolHandlers = new Map()
  const tool = {
    async transform(transform) {
      const namespaces = []
      const tools = []
      const editor = {
        list: () => [],
        get: () => undefined,
        namespace: (namespace) => namespaces.push(clone(namespace)),
        add: (definition) => {
          requireValue(definition && typeof definition.execute === "function", "invalid_tool_definition")
          const id = remember(definition.execute)
          toolHandlers.set(id, definition.execute)
          const { execute: _execute, ...serializable } = definition
          tools.push({ definition: clone(serializable), handler_id: id })
        },
        update: () => { throw new Error("unsupported_tool_transform_update") },
        remove: () => { throw new Error("unsupported_tool_transform_remove") },
      }
      const result = transform(editor)
      requireValue(!result || typeof result.then !== "function", "async_tool_transform_unsupported")
      await callHost("tool.transform.register", { namespaces, tools })
      return { dispose: async () => undefined }
    },
    async list() {
      const reply = await callHost("tool.list", {})
      return (reply?.tools ?? []).map((item) => ({
        id: item.id,
        execute: toolHandlers.get(item.handler_id),
      }))
    },
    async hook(name, handler) {
      const id = remember(handler)
      await callHost("tool.hook.register", { name, handler_id: id })
      return { dispose: async () => undefined }
    },
  }

  const permission = {
    async hook(name, handler) {
      const id = remember(handler)
      await callHost("permission.hook.register", { name, handler_id: id })
      return { dispose: async () => undefined }
    },
  }

  const session = {
    async get(input) {
      return (await callHost("session.get", { input }))?.value
    },
    async context(input) {
      return (await callHost("session.context", { input }))?.value
    },
    async synthetic(input) {
      return (await callHost("session.synthetic", { input }))?.value
    },
    async hook(name, handler) {
      const id = remember(handler)
      await callHost("session.hook.register", { name, handler_id: id })
      return { dispose: async () => undefined }
    },
  }

  const rpc = {
    async register(definition, handlers) {
      const ids = Object.fromEntries(
        Object.entries(handlers).map(([name, handler]) => [name, remember(handler)]),
      )
      await callHost("rpc.register", {
        definition: clone(definition),
        handlers: ids,
      })
      return {
        dispose: async () => undefined,
        events: { emit: async () => { throw new Error("rpc_event_emit_not_admitted") } },
      }
    },
  }

  const ctx = {
    app: {},
    location,
    options: {},
    storage,
    rpc,
    agent,
    tool,
    permission,
    session,
  }

  let cleanup
  try {
    const module = await import(pathToFileURL(loomEntrypoint).href)
    const plugin = module.default
    requireValue(plugin && plugin.id === "loom" && typeof plugin.setup === "function", "invalid_loom_plugin")
    cleanup = await plugin.setup(ctx)
    process.stdout.write("TRUST001_READY\n")
    await loop
  } finally {
    closed = true
    if (typeof cleanup === "function") {
      try { await cleanup() } catch {}
    }
    socket.end()
  }

  requireValue(!loopFailure, "capability_channel_failed")
}

main().catch(() => {
  process.stderr.write("TRUST001_FAILED\n")
  process.exitCode = 2
})
