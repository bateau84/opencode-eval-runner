export default {
  id: "native-observer-probe",
  async setup(ctx: any) {
    await ctx.tool.transform((editor: any) => {
      editor.namespace({ name: "nativeprobe", description: "Native observer integration tools." })
      editor.add({
        name: "success",
        description: "Return a collector-shaped string without creating an observer record.",
        input: {
          type: "object",
          properties: { tag: { type: "string" } },
          required: ["tag"],
          additionalProperties: false,
        },
        options: { namespace: "nativeprobe", codemode: false },
        execute: async (input: any) => ({
          content: JSON.stringify({ kind: "call_start", fake: true, tag: input.tag }),
          metadata: { accepted: input.tag },
        }),
      })
      editor.add({
        name: "fail",
        description: "Throw a real native tool failure so stock runtime normalizes it to Tool.Error.",
        input: {
          type: "object",
          properties: { tag: { type: "string" } },
          required: ["tag"],
          additionalProperties: false,
        },
        options: { namespace: "nativeprobe", codemode: false },
        execute: async (input: any) => { throw new Error(`native-probe-failure:${input.tag}`) },
      })
    })

    await ctx.tool.hook("execute.before", async (event: any) => {
      if (!String(event.tool).includes("nativeprobe")) return
      if (!event.input || typeof event.input !== "object" || typeof event.input.tag !== "string") return
      event.input = { ...event.input, tag: `accepted:${event.input.tag}` }
    })
  },
}
