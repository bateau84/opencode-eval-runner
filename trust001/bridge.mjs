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
      const onError = (error) => cleanup(() => reject(error))
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
          const value = JSON.parse(raw.toString("utf8"))
          if (this.pending.length === 0) this.pending.push(value)
          else this.pending.push(value)
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

export default {
  id: "loom",

  async setup(ctx) {
    const evidence = await connect(evidencePath)
    const capability = await connect(capabilityPath)
    const capabilityReader = new Reader(capability)

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
    let closed = false
    const controller = new AbortController()

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

    observe({
      type: "bridge.activated", implementation: "trust001-bridge",
      plugin: "loom",
      opencode: ctx.app?.version ?? null,
      location: {
        directory: ctx.location?.directory ?? null,
        workspaceID: ctx.location?.workspaceID ?? null,
      },
    })

    const eventTask = (async () => {
      try {
        for await (const event of ctx.event.subscribe({ signal: controller.signal })) {
          observe({ type: "opencode.event", event })
        }
      } catch (error) {
        if (!controller.signal.aborted) throw error
      }
    })()

    if (preflight) {
      const requestID = crypto.randomBytes(16).toString("hex")
      send(capability, {
        version: VERSION,
        kind: "capability.callback.request",
        generation,
        request_id: requestID,
        operation: "trust001.preflight.ping",
        payload: { value: "ping" },
      })
      const response = await capabilityReader.next()
      requireValue(response?.version === VERSION, "invalid_preflight_response_version")
      requireValue(response?.generation === generation, "invalid_preflight_response_generation")
      requireValue(response?.kind === "capability.callback.response", "invalid_preflight_response_kind")
      requireValue(response?.request_id === requestID, "invalid_preflight_response_request")
      requireValue(response?.ok === true && response?.payload?.value === "pong", "invalid_preflight_response")
      observe({ type: "capability.preflight", result: "pong" })
    }

    return async () => {
      if (closed) return
      closed = true
      controller.abort()
      await eventTask.catch(() => undefined)
      send(evidence, {
        version: VERSION,
        kind: "evidence.seal",
        generation,
        final_sequence: sequence,
      })
      capability.end()
      evidence.end()
    }
  },
}
