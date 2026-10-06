import { appendFileSync, writeFileSync } from "node:fs"
import { randomUUID } from "node:crypto"

// Provider-free stock-runtime probe only. This file intentionally writes
// diagnostics to /tmp; those records are never authoritative runtime evidence.
const RECORDS = "/tmp/code-mode-observer-records.jsonl"
const LOADED = "/tmp/code-mode-observer-loaded"
const FABRICATED_ID = "fabricated-from-script"

let sequence = 0
let observerLosses = 0
let toolOrdinal = 0
let echoOrdinal = 0
let releaseFirst!: () => void
const secondMayReleaseFirst = new Promise<void>((resolve) => {
  releaseFirst = resolve
})

const activeParents = new Map<string, any>()
const wrapped = new WeakSet<Function>()

function key(value: any) {
  return [value.sessionID, value.messageID, value.id].join("\u0000")
}

function snapshot(value: unknown): unknown {
  if (value instanceof Error) return { name: value.name, message: value.message }
  try {
    return JSON.parse(
      JSON.stringify(value, (_key, item) => {
        if (item instanceof Error) return { name: item.name, message: item.message }
        if (typeof item === "bigint") return String(item)
        if (typeof item === "function") return "<function>"
        return item
      }),
    )
  } catch {
    return { state: "omitted", reason: "not_json_serializable" }
  }
}

function emit(record: Record<string, unknown>) {
  const event = {
    schema: "opencode-eval-runner/code-mode-observer-experiment/v1",
    sequence: ++sequence,
    observer_losses_before: observerLosses,
    ...record,
  }
  try {
    appendFileSync(RECORDS, JSON.stringify(event) + "\n")
  } catch {
    // Observation must not alter product execution.
    observerLosses += 1
  }
}

function resultView(event: any) {
  if (event?.status === "completed") return { status: event.status, result: snapshot(event.result) }
  if (event?.status === "error") return { status: event.status, error: snapshot(event.error) }
  return { status: String(event?.status ?? "unknown") }
}

export default {
  id: "code-mode-observer-probe",
  async setup(ctx: any) {
    // Deterministic Code Mode fixtures.
    await ctx.tool.transform((editor: any) => {
      editor.namespace({ name: "codemodeprobe", description: "Stock Code Mode observer probe tools." })
      const add = (name: string, run: (input: any) => Promise<string>) =>
        editor.add({
          name,
          description: `Code Mode observer probe ${name}`,
          input: {
            type: "object",
            properties: { tag: { type: "string" } },
            additionalProperties: false,
          },
          options: { namespace: "codemodeprobe", codemode: true },
          execute: async (input: unknown) => {
            toolOrdinal += 1
            return { content: await run(input) }
          },
        })

      add("success", async () => "SUCCESS-FINAL")
      add("echo", async () => {
        const n = ++echoOrdinal
        if (n === 1) await secondMayReleaseFirst
        if (n === 2) {
          await new Promise((resolve) => setTimeout(resolve, 25))
          releaseFirst()
        }
        return `ECHO-${n}`
      })
      add("throws", async () => {
        throw new Error("THROW-RAW")
      })
      add("mutate", async () => "BEFORE-MUTATION")
    })

    // Smallest stock-supported correlation path: wrap the actual registered
    // Code Mode leaf handler. Core has already decoded input before this
    // function runs. The same Tool.Context carries the real outer execute
    // call identity, while this wrapper supplies a unique per-inner UUID.
    await ctx.tool.transform((editor: any) => {
      for (const item of editor.list()) {
        if (item.options?.namespace !== "codemodeprobe" || item.options?.codemode === false) continue
        if (wrapped.has(item.execute)) continue
        editor.update(item.id, (tool: any) => {
          const original = tool.execute
          const observed = async (input: unknown, context: any) => {
            const parent = activeParents.get(key(context))
            const invocationID = randomUUID()
            emit({
              kind: "inner_start",
              invocation_id: invocationID,
              tool: item.id,
              catalog_path: `codemodeprobe.${item.name}`,
              parent: parent ?? {
                state: "unsupported",
                reason: "outer_execute_not_observed",
                call_id: context.id,
                session_id: context.sessionID,
                message_id: context.messageID,
              },
              actor: {
                agent: context.agent,
                session_id: context.sessionID,
                message_id: context.messageID,
              },
              input: snapshot(input),
              boundary: "decoded-tool-handler-input",
            })
            try {
              const result = await original(input, context)
              emit({
                kind: "inner_handler_terminal",
                invocation_id: invocationID,
                tool: item.id,
                outcome: "returned",
                handler_result: snapshot(result),
                boundary: "tool-handler-return",
                caller_terminal: {
                  status: "unsupported",
                  reason: "stock_codemode_final_boundary_not_exposed",
                },
              })
              return result
            } catch (error) {
              emit({
                kind: "inner_handler_terminal",
                invocation_id: invocationID,
                tool: item.id,
                outcome: "threw",
                handler_error: snapshot(error),
                boundary: "tool-handler-throw",
                caller_terminal: {
                  status: "unsupported",
                  reason: "stock_codemode_final_boundary_not_exposed",
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

    await ctx.tool.hook("execute.before", (event: any) => {
      if (event.tool !== "execute") return
      const parent = {
        tool: "execute",
        call_id: event.id,
        session_id: event.sessionID,
        message_id: event.messageID,
        agent: event.agent,
      }
      activeParents.set(key(event), parent)
      emit({ kind: "parent_start", parent })
    })

    // A later normal tool hook is allowed to mutate the result after the
    // transformed leaf handler has returned. This is the counterexample that
    // proves the wrapper terminal is not Code Mode's final caller boundary.
    await ctx.tool.hook("execute.after", (event: any) => {
      if (event.tool === "codemodeprobe_mutate" && event.status === "completed") {
        event.result = { ...event.result, content: "AFTER-MUTATION" }
      }
    })

    // This hook sees core's post-handler result/error, but all inner calls reuse
    // the outer execute CallID. It therefore cannot correlate identical
    // concurrent calls without an unsupported side channel.
    await ctx.tool.hook("execute.after", (event: any) => {
      if (String(event.tool).startsWith("codemodeprobe_")) {
        emit({
          kind: "inner_after_hook",
          tool: event.tool,
          shared_call_id: event.id,
          session_id: event.sessionID,
          message_id: event.messageID,
          ...resultView(event),
          boundary: "core-tool-execute-after",
          invocation_id: {
            status: "unsupported",
            reason: "inner_calls_share_outer_call_id",
          },
        })
        return
      }
      if (event.tool !== "execute") return
      const parent = activeParents.get(key(event))
      emit({
        kind: "parent_end",
        parent: parent ?? {
          state: "unsupported",
          reason: "outer_execute_start_missing",
          call_id: event.id,
        },
        observer_losses: observerLosses,
      })
      activeParents.delete(key(event))
    })

    writeFileSync(LOADED, JSON.stringify({ fabricated_id: FABRICATED_ID, tool_ordinal: toolOrdinal }))
  },
}
