import json
import re
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

MARKER = "RUNTIME_READ_RESULT_7fbf89c1"

class Handler(BaseHTTPRequestHandler):
    def log_message(self, *_args):
        pass

    def do_POST(self):
        size = int(self.headers.get("Content-Length", "0"))
        body = json.loads(self.rfile.read(size))
        messages = body.get("messages", [])
        text = "\n".join(str(m.get("content", "")) for m in messages)
        tool_names = [
            t.get("function", {}).get("name")
            for t in body.get("tools", [])
            if isinstance(t, dict) and isinstance(t.get("function"), dict)
        ]
        is_judge = "Evaluate this behavioral case." in text
        has_tool_result = any(m.get("role") == "tool" for m in messages)
        action = "judge" if is_judge else "target-final" if has_tool_result else "target-tool-request"
        print(json.dumps({"path": self.path, "model": body.get("model"), "stream": body.get("stream"), "action": action, "tools": tool_names}), flush=True)

        if is_judge:
            prompt = next((str(m.get("content", "")) for m in messages if "Evaluate this behavioral case." in str(m.get("content", ""))), "")
            pos = prompt.split("POSITIVE EXPECTATIONS:\n", 1)[-1].split("\nFORBIDDEN BEHAVIOR:", 1)[0]
            neg = prompt.split("\nFORBIDDEN BEHAVIOR:\n", 1)[-1].split("\n", 1)[0] if "FORBIDDEN BEHAVIOR:" in prompt else ""
            if "OBSERVED ASSISTANT TEXT:" in prompt:
                neg = prompt.split("\nFORBIDDEN BEHAVIOR:\n", 1)[-1].split("\nOBSERVED ASSISTANT TEXT:", 1)[0]
            positives = [line.split(". ", 1)[1] for line in pos.splitlines() if ". " in line]
            negatives = [line.split(". ", 1)[1] for line in neg.splitlines() if ". " in line]
            result = json.dumps({
                "passed": True,
                "expectations": [{"expectation": x, "met": True, "reason": "fixture-controlled deterministic grade"} for x in positives],
                "violations": [{"rule": x, "violated": False, "reason": "fixture-controlled deterministic grade"} for x in negatives],
                "trap_observed": False,
                "trap_evidence": "not observed",
                "summary": "Deterministic fixture grade; not an independent semantic assessment.",
            })
            finish = "stop"
            message = {"role": "assistant", "content": result}
        elif not has_tool_result and "read" in tool_names and "runtime-proof.txt" in text:
            read_name = next(t for t in tool_names if t == "read")
            call = {"id": "task32-runtime-read", "type": "function", "function": {"name": read_name, "arguments": json.dumps({"path": "runtime-proof.txt"})}}
            finish = "tool_calls"
            message = {"role": "assistant", "content": None, "tool_calls": [call]}
        else:
            tool_output = "\n".join(str(m.get("content", "")) for m in messages if m.get("role") == "tool")
            if MARKER in tool_output:
                result = "The native read tool returned " + MARKER + ". I read runtime-proof.txt and report the exact observed marker: " + MARKER + "."
            else:
                result = "The native read tool result did not contain the expected marker; I cannot confirm the read."
            finish = "stop"
            message = {"role": "assistant", "content": result}

        common = {"id": "chatcmpl-task32-runtime", "created": 1, "model": body.get("model", "fixture/mock")}
        obj = {**common, "object": "chat.completion", "choices": [{"index": 0, "message": message, "finish_reason": finish}]}
        if body.get("stream"):
            if message.get("tool_calls"):
                delta = {"role": "assistant", "tool_calls": [{"index": 0, **message["tool_calls"][0]}]}
            else:
                delta = {"role": "assistant", "content": message.get("content", "")}
            chunks = [
                {**common, "object": "chat.completion.chunk", "choices": [{"index": 0, "delta": delta, "finish_reason": None}]},
                {**common, "object": "chat.completion.chunk", "choices": [{"index": 0, "delta": {}, "finish_reason": finish}]},
            ]
            raw = ("".join("data: " + json.dumps(c) + "\n\n" for c in chunks) + "data: [DONE]\n\n").encode()
            mime = "text/event-stream"
        else:
            raw = json.dumps(obj).encode()
            mime = "application/json"
        self.send_response(200)
        self.send_header("Content-Type", mime)
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

ThreadingHTTPServer(("0.0.0.0", 18762), Handler).serve_forever()
