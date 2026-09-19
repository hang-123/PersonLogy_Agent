from __future__ import annotations

import argparse
import json
import os
import socket
import time
import urllib.error
import urllib.request
import uuid

from personlogy_hook.core import claim_due, mark_delivery


def endpoint() -> str:
    return os.environ.get(
        "PERSONLOGY_ENDPOINT",
        "http://127.0.0.1:8000/v1/capture/events",
    )


def post_event(row) -> tuple[str, str | None, str | None]:
    body = {
        "events": [
            {
                "schema_version": row["schema_version"],
                "event_id": row["event_id"],
                "producer_id": row["producer_id"],
                "stream_id": row["stream_id"],
                "sequence": row["sequence"],
                "source": {
                    "kind": row["source_kind"],
                    "scope": row["source_scope"],
                    "session_key": row["session_key"],
                    "item_key": row["source_item_key"],
                    "revision": row["source_revision"],
                },
                "occurred_at": row["occurred_at"],
                "captured_at": row["captured_at"],
                "rule_version": row["rule_version"],
                "payload_hash": row["payload_hash"],
                "payload": json.loads(row["payload_json"]),
            }
        ]
    }
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json",
        "Idempotency-Key": row["event_id"],
    }
    token = os.environ.get("PERSONLOGY_TOKEN")
    if token:
        headers["Authorization"] = f"Bearer {token}"
    request = urllib.request.Request(
        endpoint(),
        data=json.dumps(body, ensure_ascii=False).encode("utf-8"),
        headers=headers,
        method="POST",
    )
    try:
        with urllib.request.urlopen(
            request,
            timeout=float(os.environ.get("PERSONLOGY_HTTP_TIMEOUT", "10")),
        ) as response:
            response_body = response.read().decode("utf-8", errors="replace")
            parsed = json.loads(response_body) if response_body.strip() else {}
            receipt = parsed.get("receipt_id") or parsed.get("server_receipt_id")
            return "received", receipt, None
    except urllib.error.HTTPError as exc:
        detail = exc.read(512).decode("utf-8", errors="replace")
        if exc.code == 429 or exc.code >= 500:
            return "retry_wait", None, f"http_{exc.code}: {detail[:240]}"
        return "blocked", None, f"http_{exc.code}: {detail[:240]}"
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        return "retry_wait", None, f"network_error: {str(exc)[:240]}"
    except (ValueError, KeyError) as exc:
        return "retry_wait", None, f"invalid_response: {str(exc)[:240]}"


def run_once(limit: int) -> int:
    owner = f"{socket.gethostname()}:{os.getpid()}:{uuid.uuid4().hex[:8]}"
    rows = claim_due(limit, owner)
    for row in rows:
        status, receipt, error = post_event(row)
        if status == "received":
            mark_delivery(
                row["event_id"],
                row["destination_id"],
                "received",
                receipt_id=receipt,
            )
        elif status == "blocked":
            mark_delivery(
                row["event_id"],
                row["destination_id"],
                "blocked",
                error_code="non_retryable",
                error_summary=error,
            )
        else:
            delay = min(3600, 2 ** min(int(row["attempt_count"]), 8))
            mark_delivery(
                row["event_id"],
                row["destination_id"],
                "retry_wait",
                error_code="retryable",
                error_summary=error,
                retry_after_seconds=delay,
            )
    return len(rows)


def main() -> int:
    parser = argparse.ArgumentParser(description="Drain the PersonLogy local outbox.")
    parser.add_argument("--once", action="store_true", help="Drain one batch and exit.")
    parser.add_argument("--loop", action="store_true", help="Keep draining until interrupted.")
    parser.add_argument("--limit", type=int, default=20)
    args = parser.parse_args()
    if not args.once and not args.loop:
        parser.error("choose --once or --loop")
    while True:
        processed = run_once(max(1, args.limit))
        if not args.loop:
            return 0
        if processed == 0:
            time.sleep(float(os.environ.get("PERSONLOGY_SENDER_IDLE_SECONDS", "5")))


if __name__ == "__main__":
    raise SystemExit(main())
