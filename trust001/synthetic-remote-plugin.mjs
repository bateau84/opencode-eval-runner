export default {
  id: "loom",
  async setup(ctx) {
    if (!ctx.location || typeof ctx.location.directory !== "string") {
      throw new Error("missing location")
    }

    await ctx.storage.set("trust001/synthetic", { ready: true })
    const stored = await ctx.storage.get("trust001/synthetic")
    if (!stored || stored.ready !== true) throw new Error("storage round trip failed")
    const page = await ctx.storage.scan({ prefix: "trust001/", limit: 10 })
    if (!Array.isArray(page.entries) || !page.entries.some((entry) => entry.key === "trust001/synthetic")) {
      throw new Error("storage scan failed")
    }
    process.stdout.write("TRUST001_SYNTHETIC_STAGE:storage\n")

    await ctx.rpc.register({
      id: "trust001.synthetic",
      methods: {
        ping: {
          input: {
            type: "object",
            properties: { value: { type: "string" } },
            required: ["value"],
            additionalProperties: false,
          },
          output: {
            type: "object",
            properties: { value: { type: "string" } },
            required: ["value"],
            additionalProperties: false,
          },
        },
      },
      events: {},
    }, {
      ping: async (input) => ({ value: input.value }),
    })
    process.stdout.write("TRUST001_SYNTHETIC_STAGE:rpc\n")

    await ctx.agent.transform((editor) => {
      if (editor.get("general")) editor.default("general")
    })
    process.stdout.write("TRUST001_SYNTHETIC_STAGE:agent\n")

    let expectedRoster
    await ctx.tool.transform((editor) => {
      editor.namespace({ name: "loom", description: "TRUST-001 synthetic namespace" })
      const execute = async () => ({ content: "synthetic-roster" })
      expectedRoster = execute
      editor.add({
        name: "roster",
        description: "Synthetic roster tool",
        input: {
          type: "object",
          properties: {},
          additionalProperties: false,
        },
        options: { namespace: "loom", codemode: false },
        execute,
      })
    })
    process.stdout.write("TRUST001_SYNTHETIC_STAGE:tool-transform\n")

    const registrations = await ctx.tool.list()
    const roster = registrations.filter((entry) => entry.id === "loom_roster")
    if (roster.length !== 1 || roster[0].execute !== expectedRoster) {
      throw new Error("tool identity failed")
    }
    process.stdout.write("TRUST001_SYNTHETIC_STAGE:tool-list\n")

    await ctx.permission.hook("evaluate", async (event) => {
      if (event.action === "trust001.synthetic.deny") {
        event.effect = "deny"
        event.message = "synthetic-deny"
      }
    })
    await ctx.session.hook("context", async (event) => {
      event.system.push({ type: "text", text: "trust001-synthetic-context" })
    })
    await ctx.session.hook("retry", async (event) => {
      if (event.attempt >= 2) event.decision = { retry: false }
    })
    await ctx.tool.hook("execute.before", async () => undefined)
    await ctx.tool.hook("execute.after", async () => undefined)
    process.stdout.write("TRUST001_SYNTHETIC_STAGE:hooks\n")
  },
}
