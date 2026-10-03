#!/usr/bin/env python3
"""Apply the pinned runtime patch, then restrict its protected-channel profile."""
from pathlib import Path
import shutil
import sys
from apply import apply


def apply_protected(root: Path):
    # apply() first verifies the upstream revision and every original blob.
    apply(root)
    path = root / "packages/core/src/codemode/tool.ts"
    text = path.read_text()
    replacements = [
        ('              const executed = yield* executeTool(name, tool, input, context,',
         '              const dispatchedContext = process.env.OPENCODE_EVAL_PROTECTED_CHANNEL === "1" && invocation\n'
         '                ? Object.assign({}, context, { evaluationInvocationID: invocation.id, evaluationDispatchOrdinal: index })\n'
         '                : context\n'
         '              const executed = yield* executeTool(name, tool, input, dispatchedContext,'),
        ('extensions: [CodeModeWeb.extension], hooks',
         'extensions: process.env.OPENCODE_EVAL_PROTECTED_CHANNEL === "1" ? [] : [CodeModeWeb.extension], hooks'),
    ]
    for old, new in replacements:
        if text.count(old) != 1:
            raise ValueError("protected runtime patch anchor mismatch")
        text = text.replace(old, new, 1)
    path.write_text(text)
    shutil.copyfile(Path(__file__).with_name("protected-profile.test.ts"),
                    root / "packages/core/test/protected-profile.test.ts")
    print("Applied protected profile: no script network extension; runtime-carried transport identity")


if __name__ == "__main__":
    apply_protected(Path(sys.argv[1]).resolve())
