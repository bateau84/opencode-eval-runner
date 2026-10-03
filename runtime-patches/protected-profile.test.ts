import { test, expect } from "bun:test"
import { Effect, Schema } from "effect"
import { CodeModeTool } from "../src/codemode/tool.js"

const context = {
  sessionID: "actual-session", messageID: "actual-message", id: "parent", agent: "actual-agent",
  progress: () => Effect.void,
} as any

test("protected profile has no script fetch and preserves dispatched invocation IDs with capture on/off", async () => {
  const saved = process.env.OPENCODE_EVAL_PROTECTED_CHANNEL
  process.env.OPENCODE_EVAL_PROTECTED_CHANNEL = "1"
  try {
    for (const observing of [false, true]) {
      const executions: any[] = [], events: any[] = []
      const tool = { name: "one", description: "fixture", input: Schema.Struct({}),
        options: { namespace: "isolated", codemode: true }, execute: () => Effect.succeed({ content: "unused" }) }
      const execute = (_name: string, _tool: unknown, input: unknown, actual: any, record?: (input: unknown) => Effect.Effect<void>) =>
        Effect.gen(function* () {
          if (record) yield* record(input)
          executions.push(actual)
          return { content: "UNCHANGED" }
        })
      const runtime = CodeModeTool.create({ tools: new Map([["isolated_one", tool]]) } as any, execute as any,
        observing ? event => Effect.sync(() => { events.push(event) }) : undefined)
      const result = await Effect.runPromise(runtime.execute({ code: `
        if (typeof fetch !== "undefined") throw Error("script network available");
        const values = await Promise.all([tools.isolated.one({}), tools.isolated.one({})]);
        return values;
      ` }, context))
      expect(result.output.error).toBeUndefined()
      expect(JSON.parse(result.output.output)).toEqual(["UNCHANGED", "UNCHANGED"])
      expect(executions).toHaveLength(2)
      expect(new Set(executions.map(c => c.evaluationInvocationID)).size).toBe(2)
      expect(executions.map(c => c.evaluationDispatchOrdinal)).toEqual([0, 1])
      for (const actual of executions) expect(actual).toMatchObject(context)
      expect(context).not.toHaveProperty("evaluationInvocationID")
      if (observing) {
        const starts = events.filter(e => e.kind === "call_start")
        expect(starts.map(e => e.invocation_id)).toEqual(executions.map(c => c.evaluationInvocationID))
        expect(events.filter(e => e.kind === "call_end").map(e => e.invocation_id).sort())
          .toEqual(executions.map(c => c.evaluationInvocationID).sort())
      }
    }
  } finally {
    if (saved === undefined) delete process.env.OPENCODE_EVAL_PROTECTED_CHANNEL
    else process.env.OPENCODE_EVAL_PROTECTED_CHANNEL = saved
  }
})
