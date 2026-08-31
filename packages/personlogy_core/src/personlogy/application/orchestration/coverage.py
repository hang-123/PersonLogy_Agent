"""Coverage contract for jobs that execute through StageRunner."""

from dataclasses import dataclass

REQUIRED_STAGE_EVENTS = ("stage.started", "stage.succeeded", "stage.failed")


@dataclass(frozen=True, slots=True)
class JobStageCoverage:
    job_kind: str
    stage: str
    required_events: tuple[str, ...] = REQUIRED_STAGE_EVENTS


JOB_STAGE_COVERAGE = (
    JobStageCoverage("pdf.parse", "pdf.parse"),
    JobStageCoverage("knowledge.compile", "knowledge.compile"),
    JobStageCoverage("retrieval.index", "retrieval.index"),
)


def coverage_for(job_kind: str) -> JobStageCoverage | None:
    return next((item for item in JOB_STAGE_COVERAGE if item.job_kind == job_kind), None)


__all__ = [
    "JOB_STAGE_COVERAGE",
    "REQUIRED_STAGE_EVENTS",
    "JobStageCoverage",
    "coverage_for",
]
