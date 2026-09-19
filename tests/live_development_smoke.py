"""Exercise real API/worker processes with isolated data and optional configured LLM.

Run from the repository root: .venv/Scripts/python tests/live_development_smoke.py --external-llm
Only synthetic source text is sent to the configured provider. Credentials stay in the environment.
"""

import argparse
import asyncio
import json
import os
import socket
import subprocess
import sys
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4

import httpx
from dotenv import dotenv_values

from personlogy.adapters.sqlite import SQLiteStore, SQLiteUnitOfWorkFactory
from personlogy.adapters.sqlite_features import SQLiteFeatureStore, SQLiteSchemaRegistry
from personlogy.domain.job import Job
from personlogy.domain.schema import SchemaSnapshot

ROOT = Path(__file__).resolve().parents[1]


def synthetic_pdf() -> bytes:
    stream = (
        b"BT /F1 12 Tf 30 250 Td (Gel is a database.) Tj "
        b"0 -20 Td (A database stores structured knowledge.) Tj ET\n"
    )
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 600 300] /Contents 4 0 R "
        b"/Resources << /Font << /F1 5 0 R >> >> >>",
        f"<< /Length {len(stream)} >>\nstream\n".encode() + stream + b"endstream",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    data = bytearray(b"%PDF-1.4\n")
    offsets = [0]
    for i, body in enumerate(objects, 1):
        offsets.append(len(data))
        data.extend(f"{i} 0 obj\n".encode() + body + b"\nendobj\n")
    xref = len(data)
    data.extend(f"xref\n0 {len(objects) + 1}\n0000000000 65535 f \n".encode())
    for offset in offsets[1:]:
        data.extend(f"{offset:010d} 00000 n \n".encode())
    data.extend(f"trailer\n<< /Size 6 /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode())
    return bytes(data)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--external-llm", action="store_true")
    args = parser.parse_args()
    run_dir = ROOT / ".tmp" / f"live-smoke-{uuid4().hex[:10]}"
    run_dir.mkdir(parents=True)
    env = {**os.environ, **{k: v for k, v in dotenv_values(ROOT / ".env").items() if v is not None}}
    env.update(
        PKS_ENVIRONMENT="local",
        PKS_STORAGE_BACKEND="sqlite",
        PKS_QUEUE_BACKEND="sqlite",
        PKS_SQLITE_PATH=str(run_dir / "data.sqlite3"),
        PKS_PDF_STORAGE_ROOT=str(run_dir / "files"),
        PKS_QUEUE_POLL_INTERVAL_SECONDS="0.1",
        PKS_RERANK_PROVIDER="none",
        PKS_EMBEDDING_PROVIDER="none",
        PYTHONUNBUFFERED="1",
    )
    if not args.external_llm:
        env["PKS_LLM_PROVIDER"] = "none"
    elif env.get("PKS_LLM_PROVIDER") != "openai_compatible":
        raise RuntimeError("--external-llm requires a configured provider in .env")
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    processes = []
    logs = []

    def start(name: str, *command: str) -> None:
        log = (run_dir / f"{name}.log").open("w", encoding="utf-8")
        logs.append(log)
        processes.append(
            subprocess.Popen(
                [sys.executable, *command],
                cwd=ROOT / "apps" / name,
                env=env,
                stdout=log,
                stderr=subprocess.STDOUT,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
            )
        )

    report = {"run_dir": str(run_dir), "external_llm": args.external_llm}
    try:
        start("api", "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", str(port))
        with httpx.Client(
            base_url=f"http://127.0.0.1:{port}/v1", timeout=15, trust_env=False
        ) as client:

            def request(method: str, path: str, **kwargs):
                response = client.request(method, path, **kwargs)
                if response.is_error:
                    raise AssertionError(f"{method} {path}: {response.status_code} {response.text}")
                return response.json()

            def until(check, seconds=120):
                deadline = time.monotonic() + seconds
                while time.monotonic() < deadline:
                    result = check()
                    if result:
                        return result
                    time.sleep(0.25)
                raise AssertionError("live development check timed out")

            def ready():
                try:
                    return request("GET", "/health/ready")
                except httpx.ConnectError:
                    return None

            until(ready, 30)
            # Seed a crashed execution after API startup; worker must recover it during polling.
            stale = Job("smoke.recovery", f"stale-{uuid4()}", {}, timeout_seconds=1).start(
                datetime.now(UTC) - timedelta(minutes=1)
            )

            async def seed():
                registry = SQLiteSchemaRegistry(SQLiteFeatureStore(run_dir / "data.sqlite3"))
                await registry.save_snapshot(
                    SchemaSnapshot.create(
                        namespace="personlogy",
                        version=1,
                        definition={
                            "entities": {"Claim": {"fields": {"statement": {"type": "text"}}}}
                        },
                    )
                )
                async with SQLiteUnitOfWorkFactory(SQLiteStore(run_dir / "data.sqlite3"))() as uow:
                    await uow.jobs.add(stale)
                    await uow.commit()

            asyncio.run(seed())
            start("worker", "-m", "personlogy_worker.main")
            upload = request(
                "POST",
                "/pdfs/upload",
                data={
                    "project_name": "Optimization smoke",
                    "project_slug": f"smoke-{uuid4().hex}",
                    "title": "Synthetic database knowledge",
                },
                files={"file": ("synthetic.pdf", synthetic_pdf(), "application/pdf")},
            )
            project_id = upload["project_id"]

            def compiled():
                jobs = request("GET", "/jobs", params={"project_id": project_id})
                for job in jobs:
                    if job["status"] == "failed":
                        raise AssertionError(f"job failed: {job['kind']}: {job['failure_reason']}")
                    if job["kind"] == "knowledge.compile" and job["status"] == "succeeded":
                        return job
                return None

            compile_job = until(compiled, 180)
            report["compile_job"] = compile_job["id"]
            okf_path = (
                run_dir
                / "files"
                / "projects"
                / project_id
                / "compilations"
                / f"{compile_job['id']}.okf.json"
            )
            okf = json.loads(okf_path.read_text(encoding="utf-8"))
            assert okf["claims"] and okf["citations"]
            report["model"] = okf["provenance"]["model_name"]
            report["claims"] = len(okf["claims"])
            assert request("GET", "/jobs", params={"project_id": str(uuid4())}) == []
            assert request("GET", "/review-tasks", params={"project_id": str(uuid4())}) == []
            tasks = request("GET", "/review-tasks", params={"project_id": project_id})
            assert tasks
            approved = [
                request(
                    "POST",
                    f"/review-tasks/{task['id']}/decision",
                    json={
                        "decision": "approved",
                        "reviewer_id": "synthetic-smoke-test",
                        "reason": "Synthetic source verified by test",
                        "expected_version": task["version"],
                    },
                )
                for task in tasks
            ]
            record = request(
                "POST",
                "/writebacks",
                headers={"X-Idempotency-Key": f"smoke-{uuid4()}"},
                json={
                    "project_id": project_id,
                    "governance_run_id": tasks[0]["run_id"],
                    "candidates": [
                        {
                            "candidate_id": task["candidate_id"],
                            "candidate_kind": task["candidate_kind"],
                            "expected_review_version": task["version"],
                        }
                        for task in approved
                    ],
                },
            )

            def published():
                current = request("GET", f"/writebacks/{record['id']}")
                return current if current["status"] == "completed" else None

            published_record = until(published)

            def indexed():
                job = request("GET", f"/jobs/{published_record['index_job_id']}")
                return job if job["status"] == "succeeded" else None

            until(indexed)
            hits = request(
                "GET", "/retrieval/search", params={"project_id": project_id, "q": "database"}
            )
            assert hits["hits"] and hits["hits"][0]["evidence"]
            report["retrieval_hits"] = len(hits["hits"])

            def recovered():
                job = request("GET", f"/jobs/{stale.id}")
                return job if job["status"] == "succeeded" else None

            recovered_job = until(recovered, 45)
            assert recovered_job["attempt"] == 2
            report["recovered_attempt"] = recovered_job["attempt"]
            # Verify persisted instrumentation after the public workflow.
            import sqlite3

            with sqlite3.connect(run_dir / "data.sqlite3") as db:
                report["audit_events"] = db.execute("select count(*) from audit_event").fetchone()[
                    0
                ]
                report["lineage_links"] = db.execute(
                    "select count(*) from lineage_link"
                ).fetchone()[0]
            assert report["audit_events"] > 0 and report["lineage_links"] > 0
            report["status"] = "passed"
    finally:
        for process in reversed(processes):
            process.terminate()
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()
        for log in logs:
            log.close()
        (run_dir / "report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
        print(json.dumps(report, indent=2), flush=True)


if __name__ == "__main__":
    main()
