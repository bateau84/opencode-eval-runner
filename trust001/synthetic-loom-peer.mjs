import net from "node:net"

const VERSION = "opencode-eval-runner/trust001-wire/v1"
const generation = process.env.TRUST001_GENERATION ?? ""
const socketPath = process.env.TRUST001_CAPABILITY_SOCKET ?? ""

if (!/^[0-9a-f]{64}$/.test(generation)) throw new Error("invalid generation")
if (!socketPath.startsWith("/")) throw new Error("invalid socket path")

function frame(value) {
  const raw = Buffer.from(JSON.stringify(value), "utf8")
  if (raw.length < 1 || raw.length > 256 * 1024) throw new Error("frame_limit")
  const prefix = Buffer.allocUnsafe(4)
  prefix.writeUInt32BE(raw.length, 0)
  return Buffer.concat([prefix, raw])
}

function send(socket, value) {
  socket.write(frame(value))
}

let buffer = Buffer.alloc(0)
const socket = net.createConnection({ path: socketPath })

socket.on("connect", () => {
  send(socket, {
    version: VERSION,
    kind: "capability.hello",
    generation,
    role: "loom",
  })
})

socket.on("data", (chunk) => {
  buffer = Buffer.concat([buffer, chunk])
  while (buffer.length >= 4) {
    const size = buffer.readUInt32BE(0)
    if (size < 1 || size > 256 * 1024) throw new Error("frame_limit")
    if (buffer.length < 4 + size) return
    const message = JSON.parse(buffer.subarray(4, 4 + size).toString("utf8"))
    buffer = buffer.subarray(4 + size)

    if (
      message.version !== VERSION ||
      message.generation !== generation ||
      message.kind !== "capability.callback.request" ||
      message.operation !== "trust001.preflight.ping" ||
      !/^[0-9a-f]{32}$/.test(message.request_id)
    ) {
      throw new Error("unexpected capability request")
    }

    send(socket, {
      version: VERSION,
      kind: "capability.callback.response",
      generation,
      request_id: message.request_id,
      ok: true,
      payload: { value: "pong" },
    })
  }
})

socket.on("error", (error) => {
  process.stderr.write("synthetic peer failed: " + error.message + "\n")
  process.exitCode = 2
})
