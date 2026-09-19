import asyncio
from functools import partial
from uuid import UUID

import structlog

from personlogy.runtime.config import get_settings
from personlogy.runtime.logging import configure_logging
from personlogy.runtime.services import (
    compilation_service,
    job_service,
    pdf_import_service,
    replay_service,
    retrieval_indexer,
    shutdown,
    stage_runner,
    writeback_service,
)
from personlogy.shared.trace import TraceContext


async def run_worker() -> None:
    settings = get_settings()
    configure_logging(settings.log_level)
    logger = structlog.get_logger()
    logger.info("worker_started", queue_backend=settings.queue_backend)
    while True:
        await job_service.recover_stale_running()
        job = await job_service.start_next(timeout_seconds=settings.queue_poll_interval_seconds)
        if job is None:
            continue
        context = TraceContext.from_job(
            trace_id=job.trace_id,
            span_id=job.span_id,
            parent_span_id=job.parent_span_id,
            request_id=job.request_id,
        )
        with context.activate():
            structlog.contextvars.bind_contextvars(
                request_id=job.request_id,
                trace_id=context.trace_id,
                span_id=context.span_id,
            )
            logger.info("job_claimed", job_id=str(job.id), kind=job.kind, attempt=job.attempt)
            try:
                async with asyncio.timeout(job.timeout_seconds):
                    if job.kind == "pdf.parse":
                        await job_service.report_progress(job.id, 20, "parsing")
                        block_count = await stage_runner.run(
                            stage="pdf.parse",
                            job=job,
                            operation=partial(pdf_import_service.process_pdf_job, job),
                        )
                        await job_service.report_progress(
                            job.id, 90, f"content_blocks_written:{block_count}"
                        )
                        await compilation_service.submit_for_version(
                            project_id=UUID(str(job.payload["project_id"])),
                            source_version_id=UUID(str(job.payload["source_version_id"])),
                        )
                    elif job.kind == "knowledge.compile":
                        await job_service.report_progress(job.id, 20, "compiling_candidates")
                        result = await stage_runner.run(
                            stage="knowledge.compile",
                            job=job,
                            operation=partial(compilation_service.process_compile_job, job),
                        )
                        replay_plan_id = job.payload.get("replay_plan_id")
                        if replay_service is not None and isinstance(replay_plan_id, str):
                            await replay_service.compare(
                                UUID(replay_plan_id),
                                replay_output={
                                    "node_count": result.node_count,
                                    "citation_count": result.citation_count,
                                    "claim_count": result.claim_count,
                                    "relation_count": result.relation_count,
                                    "governance_status": result.governance_status,
                                },
                            )
                        await job_service.report_progress(
                            job.id,
                            90,
                            f"governance:{result.governance_status}:review_tasks:{result.review_task_count}",
                        )
                    elif job.kind == "retrieval.index":
                        if retrieval_indexer is None:
                            raise RuntimeError("SQLite retrieval indexer is not configured")
                        await job_service.report_progress(job.id, 20, "rebuilding_retrieval_index")
                        project_id = UUID(str(job.payload["project_id"]))
                        count = await stage_runner.run(
                            stage="retrieval.index",
                            job=job,
                            operation=partial(
                                retrieval_indexer.rebuild_project,
                                project_id,
                                job_id=job.id,
                            ),
                        )
                        await job_service.report_progress(
                            job.id, 90, f"retrieval_documents_indexed:{count}"
                        )
                    elif job.kind == "knowledge.writeback.effects":
                        await job_service.report_progress(job.id, 20, "publishing_writeback_okf")
                        record = await stage_runner.run(
                            stage="knowledge.writeback.effects",
                            job=job,
                            operation=partial(writeback_service.process_effects_job, job),
                        )
                        await job_service.report_progress(
                            job.id,
                            90,
                            f"writeback_completed:{record.id}",
                        )
                    else:
                        await job_service.report_progress(job.id, 10, "accepted")
                    await job_service.succeed(job.id)
            except Exception as error:
                logger.exception("job_failed", job_id=str(job.id), error=str(error))
                await job_service.fail(
                    job.id, str(error) or "job execution timed out", retryable=True
                )
            finally:
                structlog.contextvars.clear_contextvars()


async def _run_and_close() -> None:
    try:
        await run_worker()
    finally:
        await shutdown()


def main() -> None:
    try:
        asyncio.run(_run_and_close())
    except KeyboardInterrupt:
        structlog.get_logger().info("worker_stopped")


if __name__ == "__main__":
    main()
