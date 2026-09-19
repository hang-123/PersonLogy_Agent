def test_api_and_worker_share_service_composition() -> None:
    from app import runtime
    from app.core.config import Settings
    from app.worker import run_worker as legacy_worker
    from personlogy.runtime import services
    from personlogy.runtime.worker import run_worker
    from personlogy_worker.main import run_worker as deployed_worker

    assert deployed_worker is run_worker is legacy_worker
    assert runtime.compilation_service is services.compilation_service
    assert runtime.job_service is services.job_service
    assert Settings is services.settings.__class__


def test_worker_enforces_execution_deadline(tmp_path, monkeypatch) -> None:
    import asyncio
    from contextlib import suppress

    from personlogy.adapters.sqlite import SQLiteJobQueue, SQLiteStore, SQLiteUnitOfWorkFactory
    from personlogy.application.orchestration import JobService
    from personlogy.domain.job import JobStatus
    from personlogy.runtime import worker

    async def run() -> None:
        store = SQLiteStore(tmp_path / "deadline.sqlite3")
        service = JobService(SQLiteUnitOfWorkFactory(store), SQLiteJobQueue(store))
        job = await service.submit(
            kind="pdf.parse",
            idempotency_key="deadline",
            payload={},
            timeout_seconds=1,
            max_attempts=1,
        )

        class SlowParser:
            async def process_pdf_job(self, job):
                await asyncio.sleep(30)
                raise AssertionError("deadline did not cancel parsing")

        monkeypatch.setattr(worker, "job_service", service)
        monkeypatch.setattr(worker, "pdf_import_service", SlowParser())
        task = asyncio.create_task(worker.run_worker())
        try:
            async with asyncio.timeout(5):
                while True:
                    current = await service.get(job.id)
                    if current.status is JobStatus.FAILED:
                        assert current.failure_reason == "job execution timed out"
                        break
                    await asyncio.sleep(0.05)
        finally:
            task.cancel()
            with suppress(asyncio.CancelledError):
                await task

    asyncio.run(run())
