#!/usr/bin/env python3
from __future__ import annotations

import json
import sys
import urllib.request


def _iter_sse_events(raw: str):
    event = None
    data_lines: list[str] = []

    for line in raw.splitlines():
        if not line:
            if event is not None:
                payload = "\n".join(data_lines)
                yield event, payload
            event = None
            data_lines = []
            continue

        if line.startswith(":"):
            continue
        if line.startswith("event:"):
            event = line.split(":", 1)[1].strip()
            continue
        if line.startswith("data:"):
            data_lines.append(line.split(":", 1)[1].lstrip())
            continue


def main() -> int:
    base = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:5000"
    url = base.rstrip("/") + "/build/stream"
    body = json.dumps({"prompt": "Build me a gaming PC for $1000"}).encode("utf-8")

    req = urllib.request.Request(
        url,
        data=body,
        headers={"Content-Type": "application/json", "Accept": "text/event-stream"},
        method="POST",
    )

    saw_trace = False
    saw_complete = False

    with urllib.request.urlopen(req, timeout=60) as resp:
        text = resp.read().decode("utf-8", errors="replace")

    for ev, data in _iter_sse_events(text):
        if ev == "trace":
            saw_trace = True
        if ev == "complete":
            saw_complete = True
            break

    if not saw_trace:
        print("FAIL: did not see event: trace", file=sys.stderr)
        return 2
    if not saw_complete:
        print("FAIL: did not see event: complete", file=sys.stderr)
        return 3

    print("OK: saw trace + complete")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

