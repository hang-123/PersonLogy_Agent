from __future__ import annotations

import json
import sys

from personlogy_hook.core import build_candidate, enqueue, load_rules


def main() -> int:
    try:
        input_stream = getattr(sys.stdin, "buffer", sys.stdin)
        raw_bytes = input_stream.read()
        raw = raw_bytes.decode("utf-8") if isinstance(raw_bytes, bytes) else raw_bytes
        event = json.loads(raw) if raw.strip() else {}
        candidate = build_candidate(event, load_rules())
        if candidate is None:
            return 0
        result = enqueue(candidate)
        if result == "conflict":
            print(
                json.dumps(
                    {
                        "continue": True,
                        "systemMessage": "PersonLogy capture conflict recorded; the prompt was not blocked.",
                    },
                    ensure_ascii=False,
                )
            )
        return 0
    except Exception as exc:
        print(f"PersonLogy capture failed: {exc}", file=sys.stderr)
        print(
            json.dumps(
                {
                    "continue": True,
                    "systemMessage": "PersonLogy local capture failed; the prompt was not blocked.",
                },
                ensure_ascii=False,
            )
        )
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
