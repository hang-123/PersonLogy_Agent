from __future__ import annotations

import sqlite3
import sys
from pathlib import Path


PLUGIN_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PLUGIN_ROOT / "scripts"))

from personlogy_hook.core import build_candidate, enqueue, load_rules
from sender import parse_response, run_once


def test_candidate_contains_stable_identity(monkeypatch, tmp_path):
    monkeypatch.setenv("PERSONLOGY_HOOK_DB", str(tmp_path / "hook.sqlite3"))
    monkeypatch.setenv("PERSONLOGY_HOOK_SCOPE", "global")
    event = {
        "session_id": "session-1",
        "turn_id": "turn-1",
        "cwd": str(tmp_path),
        "prompt": "我明年可能想读研，但现在还是先准备秋招。",
    }
    candidate1 = build_candidate(event, load_rules())
    candidate2 = build_candidate(event, load_rules())
    assert candidate1 is not None
    assert candidate1["event_id"] == candidate2["event_id"]
    assert candidate1["payload_hash"] == candidate2["payload_hash"]


def test_duplicate_capture_is_idempotent(monkeypatch, tmp_path):
    db_path = tmp_path / "hook.sqlite3"
    monkeypatch.setenv("PERSONLOGY_HOOK_DB", str(db_path))
    event = {
        "session_id": "session-1",
        "turn_id": "turn-1",
        "cwd": str(tmp_path),
        "prompt": "我现在优先准备秋招。",
    }
    candidate = build_candidate(event, load_rules())
    assert candidate is not None
    assert enqueue(candidate) == "queued"
    assert enqueue(candidate) == "duplicate"
    with sqlite3.connect(db_path) as connection:
        assert connection.execute("select count(*) from capture_events").fetchone()[0] == 1
        assert connection.execute("select count(*) from deliveries").fetchone()[0] == 1


def test_same_source_different_payload_records_conflict(monkeypatch, tmp_path):
    db_path = tmp_path / "hook.sqlite3"
    monkeypatch.setenv("PERSONLOGY_HOOK_DB", str(db_path))
    first = {
        "session_id": "session-1",
        "turn_id": "turn-1",
        "cwd": str(tmp_path),
        "prompt": "我现在优先准备秋招。",
    }
    second = dict(first, prompt="我现在优先准备读研。")
    candidate1 = build_candidate(first, load_rules())
    candidate2 = build_candidate(second, load_rules())
    assert candidate1 is not None and candidate2 is not None
    assert enqueue(candidate1) == "queued"
    assert enqueue(candidate2) == "conflict"
    with sqlite3.connect(db_path) as connection:
        assert connection.execute("select count(*) from capture_events").fetchone()[0] == 1
        assert connection.execute("select count(*) from capture_conflicts").fetchone()[0] == 1


def test_non_personal_prompt_is_skipped(monkeypatch, tmp_path):
    monkeypatch.setenv("PERSONLOGY_HOOK_DB", str(tmp_path / "hook.sqlite3"))
    event = {
        "session_id": "session-1",
        "turn_id": "turn-1",
        "cwd": str(tmp_path),
        "prompt": "请解释一下 Python 中的装饰器。",
    }
    assert build_candidate(event, load_rules()) is None


def test_sender_persists_server_receipt(monkeypatch, tmp_path):
    db_path = tmp_path / "hook.sqlite3"
    monkeypatch.setenv("PERSONLOGY_HOOK_DB", str(db_path))
    event = {
        "session_id": "session-1",
        "turn_id": "turn-1",
        "cwd": str(tmp_path),
        "prompt": "我现在优先准备秋招。",
    }
    candidate = build_candidate(event, load_rules())
    assert candidate is not None
    assert enqueue(candidate) == "queued"

    monkeypatch.setattr(
        "sender.post_event",
        lambda row: ("received", "receipt-1", None),
    )
    assert run_once(1) == 1
    with sqlite3.connect(db_path) as connection:
        assert connection.execute(
            "select status, server_receipt_id from deliveries"
        ).fetchone() == ("received", "receipt-1")


def test_sender_maps_already_received_to_received() -> None:
    status, receipt, error = parse_response(
        '{"results":[{"event_id":"event-1","status":"already_received",'
        '"server_receipt_id":"receipt-1"}]}',
        "event-1",
    )
    assert (status, receipt, error) == ("received", "receipt-1", None)


def test_sender_maps_conflict_to_blocked() -> None:
    status, receipt, error = parse_response(
        '{"results":[{"event_id":"event-1","status":"conflict",'
        '"error_code":"source_conflict"}]}',
        "event-1",
    )
    assert status == "blocked"
    assert receipt is None
    assert error == "source_conflict"


def test_sender_maps_retryable_to_retry_wait() -> None:
    status, receipt, error = parse_response(
        '{"results":[{"event_id":"event-1","status":"retryable",'
        '"error_summary":"database unavailable"}]}',
        "event-1",
    )
    assert (status, receipt, error) == ("retry_wait", None, "database unavailable")


def test_sender_retries_incomplete_response() -> None:
    status, receipt, error = parse_response("{}", "event-1")
    assert status == "retry_wait"
    assert receipt is None
    assert error is not None and error.startswith("invalid_response:")


def test_sender_retries_non_object_response() -> None:
    status, receipt, error = parse_response("[]", "event-1")
    assert status == "retry_wait"
    assert receipt is None
    assert error is not None and error.startswith("invalid_response:")
