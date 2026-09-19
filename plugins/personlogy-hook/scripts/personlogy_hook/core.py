from __future__ import annotations

import hashlib
import json
import os
import re
import sqlite3
import sys
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


PLUGIN_ROOT = Path(
    os.environ.get("PLUGIN_ROOT")
    or os.environ.get("CLAUDE_PLUGIN_ROOT")
    or Path(__file__).resolve().parents[2]
).resolve()


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


def data_dir() -> Path:
    configured = os.environ.get("PERSONLOGY_HOOK_DATA_DIR")
    if configured:
        return Path(configured).expanduser().resolve()
    plugin_data = os.environ.get("PLUGIN_DATA") or os.environ.get("CLAUDE_PLUGIN_DATA")
    if plugin_data:
        return Path(plugin_data).expanduser().resolve()
    if sys.platform == "win32":
        base = os.environ.get("LOCALAPPDATA") or (Path.home() / "AppData" / "Local")
    else:
        base = os.environ.get("XDG_DATA_HOME") or (Path.home() / ".local" / "share")
    return Path(base) / "personlogy-hook"


def database_path() -> Path:
    configured = os.environ.get("PERSONLOGY_HOOK_DB")
    return Path(configured).expanduser().resolve() if configured else data_dir() / "personlogy-hook.sqlite3"


def rules_path() -> Path:
    configured = os.environ.get("PERSONLOGY_HOOK_RULES")
    return Path(configured).expanduser().resolve() if configured else PLUGIN_ROOT / "config" / "rules.json"


def load_rules() -> dict[str, Any]:
    path = rules_path()
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {"schema_version": 1, "rule_version": "missing-rules", "rules": [], "redactions": []}
    except (OSError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"cannot load rules from {path}: {exc}") from exc


def canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def normalize_text(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


def redact_text(value: str, rules: dict[str, Any]) -> tuple[str, list[str]]:
    redacted = value
    names: list[str] = []
    for item in rules.get("redactions", []):
        try:
            updated, count = re.subn(
                item["pattern"],
                item.get("replacement", "[REDACTED]"),
                redacted,
            )
        except (KeyError, re.error):
            continue
        if count:
            names.append(str(item.get("name", "unnamed")))
            redacted = updated
    return redacted, names


@dataclass(frozen=True)
class MatchResult:
    category: str
    confidence: str
    rule_id: str
    matched_patterns: tuple[str, ...]


def match_rules(prompt: str, rules: dict[str, Any]) -> list[MatchResult]:
    results: list[MatchResult] = []
    for item in rules.get("rules", []):
        matched: list[str] = []
        for pattern in item.get("patterns", []):
            try:
                if re.search(pattern, prompt):
                    matched.append(str(pattern))
            except re.error:
                continue
        if matched:
            results.append(
                MatchResult(
                    category=str(item.get("category", "uncategorized")),
                    confidence=str(item.get("confidence", "medium")),
                    rule_id=str(item.get("id", "unnamed-rule")),
                    matched_patterns=tuple(matched),
                )
            )
    return results


def project_scope(cwd: str) -> str:
    scope = os.environ.get("PERSONLOGY_HOOK_SCOPE", "project").strip() or "project"
    if scope == "global":
        return "global"
    normalized = str(Path(cwd or os.getcwd()).expanduser().resolve()).replace("\\", "/").lower()
    return f"project:{sha256_text(normalized)[:16]}"


def source_item_key(event: dict[str, Any], prompt: str, session_id: str) -> str:
    turn_id = str(event.get("turn_id") or "").strip()
    if turn_id:
        return turn_id
    return f"prompt-hash:{sha256_text(session_id + chr(0) + prompt)[:32]}"


def build_candidate(event: dict[str, Any], rules: dict[str, Any]) -> dict[str, Any] | None:
    prompt = event.get("prompt")
    if not isinstance(prompt, str):
        return None
    prompt = normalize_text(prompt)
    if len(prompt) < int(rules.get("minimum_prompt_length", 2)):
        return None

    matches = match_rules(prompt, rules)
    if not matches:
        return None

    session_id = str(event.get("session_id") or "unknown-session")
    cwd = str(event.get("cwd") or os.getcwd())
    redacted_prompt, redaction_names = redact_text(prompt, rules)
    source_scope = project_scope(cwd)
    item_key = source_item_key(event, prompt, session_id)
    revision = int(event.get("source_revision", 0) or 0)
    source_key = "|".join(["codex", source_scope, session_id, item_key, str(revision)])
    event_id = str(uuid.uuid5(uuid.NAMESPACE_URL, "personlogy-hook:" + source_key))
    captured_at = utc_now()
    categories = sorted({item.category for item in matches})
    payload = {
        "message": {"role": "user", "text": redacted_prompt},
        "source": {
            "kind": "codex",
            "scope": source_scope,
            "session_id": session_id,
            "turn_id": event.get("turn_id"),
            "item_key": item_key,
            "revision": revision,
            "cwd": cwd,
            "transcript_path": event.get("transcript_path"),
            "model": event.get("model"),
            "permission_mode": event.get("permission_mode"),
        },
        "selection": {
            "categories": categories,
            "matched_rules": [
                {
                    "id": item.rule_id,
                    "category": item.category,
                    "confidence": item.confidence,
                    "matched_patterns": list(item.matched_patterns),
                }
                for item in matches
            ],
            "rule_version": rules.get("rule_version", "unknown"),
            "redactions": redaction_names,
        },
    }
    payload_json = canonical_json(payload)
    payload_hash = sha256_text(payload_json)
    stream_id = os.environ.get("PERSONLOGY_HOOK_STREAM_ID", "codex:" + source_scope)
    return {
        "schema_version": 1,
        "event_id": event_id,
        "producer_id": os.environ.get("PERSONLOGY_HOOK_PRODUCER_ID", "local-codex"),
        "source_kind": "codex",
        "source_scope": source_scope,
        "session_key": session_id,
        "source_item_key": item_key,
        "source_revision": revision,
        "stream_id": stream_id,
        "occurred_at": None,
        "captured_at": captured_at,
        "rule_version": str(rules.get("rule_version", "unknown")),
        "payload_hash": payload_hash,
        "payload_json": payload_json,
    }


SCHEMA = """
CREATE TABLE IF NOT EXISTS capture_events (
    event_id TEXT PRIMARY KEY,
    producer_id TEXT NOT NULL,
    source_kind TEXT NOT NULL,
    source_scope TEXT NOT NULL,
    session_key TEXT NOT NULL,
    source_item_key TEXT NOT NULL,
    source_revision INTEGER NOT NULL DEFAULT 0,
    stream_id TEXT NOT NULL,
    sequence INTEGER NOT NULL,
    occurred_at TEXT,
    captured_at TEXT NOT NULL,
    rule_version TEXT NOT NULL,
    schema_version INTEGER NOT NULL,
    payload_hash TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    UNIQUE(source_kind, source_scope, session_key, source_item_key, source_revision),
    UNIQUE(producer_id, stream_id, sequence)
);
CREATE INDEX IF NOT EXISTS idx_capture_events_stream_sequence
    ON capture_events(stream_id, sequence);
CREATE INDEX IF NOT EXISTS idx_capture_events_created_at
    ON capture_events(created_at);

CREATE TABLE IF NOT EXISTS deliveries (
    event_id TEXT NOT NULL REFERENCES capture_events(event_id) ON DELETE CASCADE,
    destination_id TEXT NOT NULL,
    status TEXT NOT NULL CHECK(status IN ('pending', 'in_flight', 'retry_wait', 'received', 'blocked')),
    attempt_count INTEGER NOT NULL DEFAULT 0,
    next_attempt_at TEXT,
    lease_owner TEXT,
    lease_until TEXT,
    server_receipt_id TEXT,
    last_error_code TEXT,
    last_error_summary TEXT,
    first_sent_at TEXT,
    received_at TEXT,
    updated_at TEXT NOT NULL,
    PRIMARY KEY(event_id, destination_id)
);
CREATE INDEX IF NOT EXISTS idx_deliveries_due
    ON deliveries(status, next_attempt_at);

CREATE TABLE IF NOT EXISTS stream_state (
    producer_id TEXT NOT NULL,
    stream_id TEXT NOT NULL,
    next_sequence INTEGER NOT NULL DEFAULT 1,
    last_contiguous_received_sequence INTEGER NOT NULL DEFAULT 0,
    updated_at TEXT NOT NULL,
    PRIMARY KEY(producer_id, stream_id)
);

CREATE TABLE IF NOT EXISTS capture_conflicts (
    conflict_id INTEGER PRIMARY KEY AUTOINCREMENT,
    source_kind TEXT NOT NULL,
    source_scope TEXT NOT NULL,
    session_key TEXT NOT NULL,
    source_item_key TEXT NOT NULL,
    source_revision INTEGER NOT NULL,
    existing_event_id TEXT NOT NULL,
    existing_payload_hash TEXT NOT NULL,
    incoming_event_id TEXT NOT NULL,
    incoming_payload_hash TEXT NOT NULL,
    created_at TEXT NOT NULL,
    UNIQUE(source_kind, source_scope, session_key, source_item_key, source_revision,
           existing_payload_hash, incoming_payload_hash)
);
"""


def connect() -> sqlite3.Connection:
    path = database_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path, timeout=3.0)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA journal_mode=WAL")
    connection.execute("PRAGMA synchronous=FULL")
    connection.execute("PRAGMA foreign_keys=ON")
    connection.execute("PRAGMA busy_timeout=3000")
    connection.executescript(SCHEMA)
    return connection


def enqueue(candidate: dict[str, Any]) -> str:
    destination = os.environ.get("PERSONLOGY_DESTINATION_ID", "personlogy-local")
    now = utc_now()
    connection = connect()
    try:
        connection.execute("BEGIN IMMEDIATE")
        existing = connection.execute(
            """
            SELECT event_id, payload_hash
            FROM capture_events
            WHERE source_kind = ? AND source_scope = ? AND session_key = ?
              AND source_item_key = ? AND source_revision = ?
            """,
            (
                candidate["source_kind"],
                candidate["source_scope"],
                candidate["session_key"],
                candidate["source_item_key"],
                candidate["source_revision"],
            ),
        ).fetchone()
        if existing:
            if existing["payload_hash"] == candidate["payload_hash"]:
                connection.commit()
                return "duplicate"
            connection.execute(
                """
                INSERT OR IGNORE INTO capture_conflicts (
                    source_kind, source_scope, session_key, source_item_key,
                    source_revision, existing_event_id, existing_payload_hash,
                    incoming_event_id, incoming_payload_hash, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    candidate["source_kind"],
                    candidate["source_scope"],
                    candidate["session_key"],
                    candidate["source_item_key"],
                    candidate["source_revision"],
                    existing["event_id"],
                    existing["payload_hash"],
                    candidate["event_id"],
                    candidate["payload_hash"],
                    now,
                ),
            )
            connection.commit()
            return "conflict"

        state = connection.execute(
            """
            SELECT next_sequence FROM stream_state
            WHERE producer_id = ? AND stream_id = ?
            """,
            (candidate["producer_id"], candidate["stream_id"]),
        ).fetchone()
        sequence = int(state["next_sequence"]) if state else 1
        connection.execute(
            """
            INSERT INTO stream_state (
                producer_id, stream_id, next_sequence,
                last_contiguous_received_sequence, updated_at
            ) VALUES (?, ?, ?, 0, ?)
            ON CONFLICT(producer_id, stream_id) DO UPDATE SET
                next_sequence = excluded.next_sequence,
                updated_at = excluded.updated_at
            """,
            (candidate["producer_id"], candidate["stream_id"], sequence + 1, now),
        )
        connection.execute(
            """
            INSERT INTO capture_events (
                event_id, producer_id, source_kind, source_scope, session_key,
                source_item_key, source_revision, stream_id, sequence,
                occurred_at, captured_at, rule_version, schema_version,
                payload_hash, payload_json, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                candidate["event_id"],
                candidate["producer_id"],
                candidate["source_kind"],
                candidate["source_scope"],
                candidate["session_key"],
                candidate["source_item_key"],
                candidate["source_revision"],
                candidate["stream_id"],
                sequence,
                candidate["occurred_at"],
                candidate["captured_at"],
                candidate["rule_version"],
                candidate["schema_version"],
                candidate["payload_hash"],
                candidate["payload_json"],
                now,
            ),
        )
        connection.execute(
            """
            INSERT INTO deliveries (event_id, destination_id, status, updated_at)
            VALUES (?, ?, 'pending', ?)
            """,
            (candidate["event_id"], destination, now),
        )
        connection.commit()
        return "queued"
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def claim_due(limit: int, lease_owner: str, lease_seconds: int = 60) -> list[sqlite3.Row]:
    now = utc_now()
    lease_until = datetime.now(timezone.utc).timestamp() + lease_seconds
    lease_until_text = datetime.fromtimestamp(lease_until, timezone.utc).isoformat(timespec="milliseconds")
    destination = os.environ.get("PERSONLOGY_DESTINATION_ID", "personlogy-local")
    connection = connect()
    try:
        connection.execute("BEGIN IMMEDIATE")
        rows = connection.execute(
            """
            SELECT e.*, d.destination_id, d.attempt_count
            FROM capture_events e
            JOIN deliveries d ON d.event_id = e.event_id
            WHERE d.destination_id = ?
              AND (
                (d.status IN ('pending', 'retry_wait')
                 AND (d.next_attempt_at IS NULL OR d.next_attempt_at <= ?))
                OR (d.status = 'in_flight' AND d.lease_until <= ?)
              )
            ORDER BY e.stream_id, e.sequence
            LIMIT ?
            """,
            (destination, now, now, max(1, limit)),
        ).fetchall()
        for row in rows:
            connection.execute(
                """
                UPDATE deliveries
                SET status = 'in_flight', lease_owner = ?, lease_until = ?,
                    attempt_count = attempt_count + 1,
                    first_sent_at = COALESCE(first_sent_at, ?), updated_at = ?
                WHERE event_id = ? AND destination_id = ?
                """,
                (
                    lease_owner,
                    lease_until_text,
                    now,
                    now,
                    row["event_id"],
                    row["destination_id"],
                ),
            )
        connection.commit()
        return rows
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def mark_delivery(
    event_id: str,
    destination_id: str,
    status: str,
    *,
    receipt_id: str | None = None,
    error_code: str | None = None,
    error_summary: str | None = None,
    retry_after_seconds: int | None = None,
) -> None:
    now_dt = datetime.now(timezone.utc)
    next_attempt = None
    if status == "retry_wait":
        delay = max(1, retry_after_seconds or 30)
        next_attempt = datetime.fromtimestamp(
            now_dt.timestamp() + delay, timezone.utc
        ).isoformat(timespec="milliseconds")
    connection = connect()
    try:
        connection.execute("BEGIN IMMEDIATE")
        connection.execute(
            """
            UPDATE deliveries
            SET status = ?, server_receipt_id = COALESCE(?, server_receipt_id),
                last_error_code = ?, last_error_summary = ?,
                next_attempt_at = ?, lease_owner = NULL, lease_until = NULL,
                received_at = CASE WHEN ? = 'received' THEN ? ELSE received_at END,
                updated_at = ?
            WHERE event_id = ? AND destination_id = ?
            """,
            (
                status,
                receipt_id,
                error_code,
                error_summary,
                next_attempt,
                status,
                now_dt.isoformat(timespec="milliseconds"),
                now_dt.isoformat(timespec="milliseconds"),
                event_id,
                destination_id,
            ),
        )
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()
