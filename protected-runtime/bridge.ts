import { appendFileSync, readFileSync, writeFileSync } from "node:fs"

// Trusted transport adapter for the existing execute.observed runtime seam.
// No observation is reconstructed here. Never load target plugins in this process.
const request = JSON.parse(readFileSync("/input/request.json", "utf8"))
const policy = JSON.parse(readFileSync("/input/policy.json", "utf8"))
const path = "/capture/events.jsonl"
const token = /^[A-Za-z0-9_.:/@-]{1,256}$/
const sensitive = /password|passwd|secret|token|authorization|credential|api[-_]?key|private[-_]?key/i
const literals: string[] = [...new Set<string>((policy.secrets ?? []).flatMap((s: string) =>
  [s, Buffer.from(s).toString("base64"), Buffer.from(s).toString("hex"), encodeURIComponent(s)]))]
  .filter(Boolean).sort((a, b) => b.length - a.length)
function canonical(v: any): string {
  if (Array.isArray(v)) return "[" + v.map(canonical).join(",") + "]"
  if (v !== null && typeof v === "object") return "{" + Object.keys(v).sort().map(k => JSON.stringify(k) + ":" + canonical(v[k])).join(",") + "}"
  return JSON.stringify(v)
}
const allowed = new Set((policy.allowed_values ?? []).map(canonical))
function safeField(field: any): any {
  if (field?.state !== "available") return { state: "omitted", reason: "unsupported_snapshot" }
  let changed = false
  const scrub = (value: any): any => {
    if (typeof value === "string") {
      let out = value
      for (const secret of literals) out = out.split(secret).join("[REDACTED]")
      changed ||= out !== value
      return out
    }
    if (Array.isArray(value)) return value.map(scrub)
    if (value !== null && typeof value === "object") {
      const out = Object.create(null)
      for (const [key, item] of Object.entries(value)) {
        const safeKey = scrub(key)
        if (Object.hasOwn(out, safeKey)) throw new Error("key_collision")
        if (sensitive.test(key)) { out[safeKey] = "[REDACTED]"; changed = true }
        else out[safeKey] = scrub(item)
      }
      return out
    }
    return value
  }
  try {
    const value = scrub(field.value)
    // Exact host-approved values, not a claim that regexes discover unknown secrets.
    if (!allowed.has(canonical(value))) return { state: "omitted", reason: "policy_omission" }
    if (Buffer.byteLength(JSON.stringify(value), "utf8") > 16384) return { state: "truncated", reason: "field_limit" }
    return { state: changed ? "redacted" : "available", redaction: "safe", value }
  } catch { return { state: "omitted", reason: "policy_omission" } }
}
let seq = 0
let bytes = 0
let broken = false
function write(body: any) {
  if (broken) return
  try {
    const line = JSON.stringify(body) + "\n"
    bytes += Buffer.byteLength(line)
    if (bytes > 8 * 1024 * 1024 - 4096 || seq > 10000) throw new Error("capture_limit")
    appendFileSync(path, line, { mode: 0o600 })
  } catch {
    broken = true
    try { writeFileSync("/capture/fault", "capture_io_or_limit") } catch {}
  }
}
function observed(event: any) {
  if (!request.observe) return
  // All metadata comes from the runtime. Reject unexpected fields rather than
  // copying unreviewed free text through the redaction boundary.
  const names = new Set(["schema", "sequence", "parent", "actor", "observer_failures", "kind", "boundary", "mode",
    "invocation_id", "tool", "catalog_path", "input", "result", "error", "error_representation", "outcome", "dispatched",
    "admitted", "terminals", "missing_terminals", "unsupported_dispatches", "unavailable_fields", "scope", "evidence_eligible"])
  const safe: any = {}
  try {
    for (const [key, value] of Object.entries(event)) {
      if (!names.has(key)) throw new Error("unknown_field")
      if (["input", "result", "error"].includes(key)) safe[key] = safeField(value)
      else if (key === "actor" || key === "parent") {
        if (!value || typeof value !== "object") throw new Error("identity")
        for (const item of Object.values(value)) {
          if (typeof item !== "string" || !token.test(item) || literals.some(s => item.includes(s))) throw new Error("identity")
        }
        safe[key] = value
      } else {
        if (typeof value === "string" && (!token.test(value) || literals.some(s => value.includes(s)))) throw new Error("metadata")
        if (!["string", "number", "boolean"].includes(typeof value)) throw new Error("metadata")
        safe[key] = value
      }
    }
    write({ kind: "observation", run_id: request.run_id, seq: ++seq, observation: safe })
  } catch {
    broken = true
    try { writeFileSync("/capture/fault", "capture_metadata_unsupported") } catch {}
  }
}

export default {
  id: "protectedbridge",
  async setup(ctx: any) {
    if (request.observe) write({ kind: "capture_start", schema: "opencode-protected-observation/v1",
      profile: "codemode-inner/direct-session/v1", run_id: request.run_id, seq: 0, policy_id: request.policy_id })
    await ctx.tool.hook("execute.observed", observed)
    await ctx.tool.hook("execute.before", (event: any) => {
      if (event.tool !== "execute" && !request.tools.some((t: any) => event.tool === "isolated_" + t.name))
        throw new Error("tool_not_in_protected_profile")
    })
    await ctx.tool.transform((editor: any) => {
      // Fixed restricted profile, identical with capture ON and OFF. No local
      // shell, dynamic plugin, delegated-session or other executable surface.
      for (const tool of editor.list()) editor.remove(tool.id)
      editor.namespace({ name: "isolated", description: "Tools executed in a separate untrusted container." })
      for (const definition of request.tools) editor.add({
        name: definition.name, description: definition.description ?? definition.name,
        input: definition.input, output: {}, options: { namespace: "isolated", codemode: true },
        execute: async (input: unknown, tool: any) => {
          const response = await fetch(request.tool_url + "/call", {
            method: "POST", headers: { "content-type": "application/json" },
            body: JSON.stringify({ name: definition.name, input }), signal: AbortSignal.timeout(10000),
          })
          if (!response.ok) throw new Error("isolated_tool_transport_failed")
          const text = await response.text()
          if (Buffer.byteLength(text) > 1024 * 1024) throw new Error("isolated_tool_response_limit")
          const value = JSON.parse(text)
          if (value.outcome === "threw" && typeof value.error === "string") throw new Error(value.error)
          if (value.outcome !== "returned" || !Object.hasOwn(value, "result")) throw new Error("isolated_tool_invalid_response")
          return { output: value.result, content: "" }
        },
      })
    })
  },
}
