#!/usr/bin/env python3
"""Apply the downstream patch to exactly OpenCode v2.0.18 sources."""
import hashlib
from pathlib import Path
import shutil
import subprocess
import sys

REVISION = "cd9a14a6b688d4021bee381dfd39d2cef9c0f862"
PINS = {
    "packages/codemode/src/tool-runtime.ts": "9c179bbfe070959704bc6e750e6e2d0045da2b6a",
    "packages/codemode/src/tool.ts": "1b23d20c36839aded39df3eca4d666aa50122b36",
    "packages/codemode/src/codemode.ts": "edae39aeebf996f57baf19115cbc66638548445a",
    "packages/codemode/src/interpreter/errors.ts": "587347645f182c4a1742b3d47748c9dfb5510aff",
    "packages/core/src/codemode/tool.ts": "74742f64997e085aee5e8ee15dba30ee63bf5a6a",
    "packages/core/src/tool.ts": "5e2ca8401aa550b1bd980cd9d7f513a3db9da0bc",
    "packages/core/src/tool/runtime.ts": "f21c67a533ed942c06747f51474908bce099fc33",
    "packages/plugin/src/effect/tool.ts": "04494b2630eda63a169a8905815b438fae8358ba",
}


def apply(root: Path):
    revision = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=root, text=True).strip()
    if revision != REVISION:
        raise ValueError("unsupported runtime revision; refusing fuzzy patch")
    sources = {}
    for path, expected in PINS.items():
        raw = (root / path).read_bytes()
        actual = hashlib.sha1(b"blob " + str(len(raw)).encode() + b"\0" + raw).hexdigest()
        if actual != expected:
            raise ValueError(f"source pin mismatch: {path}")
        sources[path] = raw.decode()

    def edit(path, old, new):
        if sources[path].count(old) != 1:
            raise ValueError(f"patch anchor not unique: {path}: {old[:70]}")
        sources[path] = sources[path].replace(old, new, 1)

    p = "packages/codemode/src/tool-runtime.ts"
    edit(p, 'export type ToolInvocation = { readonly name: string; readonly input: unknown }',
         'export type ToolInvocation = { readonly id: string; readonly name: string; readonly input: unknown }')
    edit(p, '      return yield* hooked(\n        { name, input },',
         '      const call: ToolInvocation = { id: crypto.randomUUID(), name, input }\n      return yield* hooked(\n        call,')
    edit(p, 'Effect.suspend(() => tool.execute(input))', 'Effect.suspend(() => tool.execute(input, call))')
    p = "packages/codemode/src/tool.ts"
    edit(p, 'import type { Tools } from "./tools.js"',
         'import type { Tools } from "./tools.js"\nimport type { ToolInvocation } from "./tool-runtime.js"')
    edit(p, 'readonly execute: (input: unknown) =>', 'readonly execute: (input: unknown, invocation?: ToolInvocation) =>')
    edit(p, 'readonly execute: (input: InputType<I>) =>', 'readonly execute: (input: InputType<I>, invocation?: ToolInvocation) =>')
    edit(p, 'execute: (input) => options.execute(input as InputType<I>),',
         'execute: (input, invocation) => options.execute(input as InputType<I>, invocation),')
    p = "packages/codemode/src/interpreter/errors.ts"
    edit(p, '  const type = thrown instanceof Error && isErrorType(thrown.name) ? thrown.name : "Error"\n  return createErrorValue(builtins[type], normalizeError(thrown).message)',
         '  const error = callerError(thrown)\n  return createErrorValue(builtins[error.name], error.message)')
    edit(p, '/** Error.prototype.toString:',
         'export const callerError = (thrown: unknown): { name: ErrorType; message: string } => ({\n  name: thrown instanceof Error && isErrorType(thrown.name) ? thrown.name : "Error",\n  message: normalizeError(thrown).message,\n})\n\n/** Error.prototype.toString:')
    p = "packages/codemode/src/codemode.ts"
    edit(p, 'import { Effect, Schema } from "effect"',
         'import { Effect, Schema } from "effect"\nexport { callerError } from "./interpreter/errors.js"')

    p = "packages/core/src/tool/runtime.ts"
    edit(p, 'export const execute = (tool: Tool.Info<any, any>, input: unknown, context: Tool.Context) =>',
         'export const execute = (tool: Tool.Info<any, any>, input: unknown, context: Tool.Context, observedInput?: (input: unknown) => Effect.Effect<void>) =>')
    edit(p, '    const decoded = yield* decodeInput(tool, input)',
         '    const decoded = yield* decodeInput(tool, input)\n    if (observedInput) yield* observedInput(decoded)')

    p = "packages/core/src/tool.ts"
    edit(p, 'import { CodeModeTool } from "./codemode/tool.js"',
         'import { CodeModeTool } from "./codemode/tool.js"\nimport { LocalObservation } from "./codemode/local-observation.js"')
    edit(p, '      context: Tool.Context,\n    ) {',
         '      context: Tool.Context,\n      observedInput?: (input: unknown) => Effect.Effect<void>,\n    ) {')
    edit(p, 'execute(tool, input, context).pipe(', 'execute(tool, input, context, observedInput).pipe(')
    edit(p, '    ) {\n      const execution = yield* execute(tool, input, context, observedInput).pipe(',
         '    ) {\n      const nativeObservation =\n        observedInput === undefined && process.env.OPENCODE_EVAL_HOST_OBSERVATIONS === "1"\n          ? LocalObservation.makeNative(context, name, (event) =>\n              hooks.trigger("tool", "execute.native-observed", event).pipe(Effect.asVoid),\n            )\n          : undefined\n      const execution = yield* execute(tool, input, context, observedInput ?? nativeObservation?.start).pipe(')
    edit(p, '        yield* hooks.trigger("tool", "execute.after", afterEvent)\n        return yield* afterEvent.error',
         '        yield* hooks.trigger("tool", "execute.after", afterEvent)\n        if (nativeObservation) {\n          yield* nativeObservation.threw({ message: afterEvent.error.message, metadata: afterEvent.error.metadata ?? null })\n          nativeObservation.close()\n        }\n        return yield* afterEvent.error')
    edit(p, '      const afterContent = yield* normalizeImages(normalizeContent(afterEvent.result.content, afterEvent.result.output))\n      return {\n        ...(afterEvent.result.output === undefined ? {} : { output: afterEvent.result.output }),\n        content: afterContent,\n        ...(afterEvent.result.metadata === undefined ? {} : { metadata: afterEvent.result.metadata }),\n      }',
         '      const afterContent = yield* normalizeImages(normalizeContent(afterEvent.result.content, afterEvent.result.output))\n      const result = {\n        ...(afterEvent.result.output === undefined ? {} : { output: afterEvent.result.output }),\n        content: afterContent,\n        ...(afterEvent.result.metadata === undefined ? {} : { metadata: afterEvent.result.metadata }),\n      }\n      if (nativeObservation) {\n        yield* nativeObservation.returned(result)\n        nativeObservation.close()\n      }\n      return result')
    edit(p, 'CodeModeTool.create(codeModeInventory, (name, tool, input, context) =>\n                beforeExecute(name, input, context).pipe(\n                  Effect.flatMap((event) => executeTool(tool, name, event.input, context)),\n                ),\n              )',
         'CodeModeTool.create(codeModeInventory, (name, tool, input, context, observedInput) =>\n                beforeExecute(name, input, context).pipe(\n                  Effect.flatMap((event) => executeTool(tool, name, event.input, context, observedInput)),\n                ),\n                process.env.OPENCODE_EVAL_OBSERVATIONS === "1"\n                  ? (event) => hooks.trigger("tool", "execute.observed", event).pipe(Effect.asVoid)\n                  : undefined,\n              )')
    p = "packages/plugin/src/effect/tool.ts"
    edit(p, 'export interface ToolHooks {',
         'export interface ToolHooks {\n  /** Downstream eval-only observations; not an authenticated evidence channel. */\n  readonly "execute.observed": Readonly<Record<string, unknown>>\n  /** Native/tool-service observations for normal invoke feasibility; also unauthenticated. */\n  readonly "execute.native-observed": Readonly<Record<string, unknown>>')
    edit(p, 'export interface ToolFailures extends Record<keyof ToolHooks, unknown> {',
         'export interface ToolFailures extends Record<keyof ToolHooks, unknown> {\n  readonly "execute.observed": never\n  readonly "execute.native-observed": never')

    p = "packages/core/src/codemode/tool.ts"
    edit(p, 'import { CodeModeWeb } from "./web.js"',
         'import { CodeModeWeb } from "./web.js"\nimport { LocalObservation } from "./local-observation.js"')
    edit(p, '  executeTool: (name: string, tool: Info, input: unknown, context: Context) => Effect.Effect<Result, Error>,\n)',
         '  executeTool: (name: string, tool: Info, input: unknown, context: Context, observedInput?: (input: unknown) => Effect.Effect<void>) => Effect.Effect<Result, Error>,\n  observe?: (event: Readonly<Record<string, unknown>>) => Effect.Effect<void>,\n)')
    edit(p, '        const callIndex = yield* Ref.make(0)',
         '        const observation = observe ? LocalObservation.make(context, observe) : undefined\n        if (observation) yield* observation.open()\n        const callIndex = yield* Ref.make(0)')
    edit(p, '          (name, tool, input) =>\n            Effect.gen(function* () {',
         '          (name, tool, input, invocation) =>\n            Effect.gen(function* () {')
    edit(p, '              const executed = yield* executeTool(name, tool, input, context)',
         '              const executed = yield* executeTool(name, tool, input, context,\n                observation && invocation ? (decoded) => observation.dispatch(invocation, name, decoded) : undefined)')
    edit(p, '          progressHooks(record),\n        ).execute(code)',
         '          observation ? observation.hooks(progressHooks(record)) : progressHooks(record),\n        ).execute(code).pipe(Effect.onExit(() => observation ? observation.close() : Effect.void))')
    edit(p, '  executeTool: (name: string, tool: Info, input: unknown) => Effect.Effect<unknown, unknown>,',
         '  executeTool: (name: string, tool: Info, input: unknown, invocation?: CodeMode.ToolInvocation) => Effect.Effect<unknown, unknown>,')
    edit(p, '      execute: (input) => executeTool(name, registration, input),',
         '      execute: (input, invocation) => executeTool(name, registration, input, invocation),')

    # Complete all checks in memory before touching the checkout.
    for path, text in sources.items():
        (root / path).write_text(text)
    here = Path(__file__).resolve().parent
    shutil.copyfile(here / "local-observation.ts", root / "packages/core/src/codemode/local-observation.ts")
    target = root / "packages/core/test/local-observation.test.ts"
    target.parent.mkdir(exist_ok=True)
    shutil.copyfile(here / "local-observation.test.ts", target)
    print(f"Applied local eval observation patch to {REVISION}; no upstream write")


if __name__ == "__main__":
    apply(Path(sys.argv[1]).resolve())
