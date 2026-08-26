from datetime import UTC, datetime, timedelta

import pytest
from personlogy.domain.job import Job, JobStatus
from personlogy.shared.errors import InvalidStateTransitionError


def test_job_retry_preserves_failure_reason_and_attempt() -> None:
    now = datetime(2026, 1, 1, tzinfo=UTC)
    job = Job("conversation.normalize", "conversation:1", {}, max_attempts=2)
    running = job.start(now)
    retrying = running.fail(
        "LLM timeout", retryable=True, retry_delay=timedelta(seconds=5), now=now
    )

    assert retrying.status is JobStatus.RETRYING
    assert retrying.attempt == 1
    assert retrying.failure_reason == "LLM timeout"
    assert retrying.next_attempt_at == now + timedelta(seconds=5)


def test_terminal_job_cannot_be_started() -> None:
    job = Job("index", "index:1", {}).start().succeed()
    with pytest.raises(InvalidStateTransitionError):
        job.start()
