# System Optimization Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [x]`) syntax for tracking.

**Goal:** Close the correctness, security, reliability, isolation, and deployment gaps identified in `.tmp/optimization-review/recommendations.md`.

**Architecture:** Preserve the modular-monolith boundaries. Harden the existing LLM adapters and compilation contract, extend the job/application ports for recovery and project scoping, and keep SQLite/Gel differences behind adapters. API and Worker will share configuration conventions while unsupported Gel retrieval remains explicit.

**Tech Stack:** Python 3.12, FastAPI, SQLite/Gel adapters, httpx, pytest, Ruff, mypy, React/Vite, GitHub Actions.

**Spec:** `.tmp/optimization-review/recommendations.md`

## Global Constraints

- Domain code must not depend on FastAPI, Gel, HTTP clients, or UI frameworks.
- Existing user changes in `.env.example`, `.gitignore`, `README.md`, and `start.ps1` must be preserved.
- No destructive Git history rewrite without separate explicit authorization.
- Every behavior change gets a regression test before production code changes.

### Task 1: Harden provider response and compilation contracts

**Files:**
- Modify: `packages/personlogy_core/src/personlogy/adapters/llm_openai.py`
- Modify: `packages/personlogy_core/src/personlogy/application/compilation/service.py`
- Modify: `packages/personlogy_core/pyproject.toml`
- Test: `apps/api/tests/test_llm_adapters.py`

- [x] Add failing tests for malformed completion JSON, unmatched quotes, relation-only citations, and OKF identifiers.
- [x] Run the focused tests and observe expected failures.
- [x] Implement strict response normalization, exact quote matching, independent relation citations, and the established OKF v0.2 shape.
- [x] Add `httpx` to runtime core dependencies and run focused tests plus Ruff.

### Task 2: Make jobs recoverable and project-scoped

**Files:**
- Modify: `packages/personlogy_core/src/personlogy/domain/job.py`
- Modify: `packages/personlogy_core/src/personlogy/application/orchestration/service.py`
- Modify: `packages/personlogy_core/src/personlogy/ports/repositories.py`
- Modify: `packages/personlogy_core/src/personlogy/adapters/sqlite.py`
- Modify: `packages/personlogy_core/src/personlogy/adapters/memory.py`
- Modify: `apps/api/app/modules/jobs/router.py`
- Modify: `apps/api/app/modules/governance/router.py`
- Test: `apps/api/tests/test_jobs_domain.py`, `apps/api/tests/test_jobs_api.py`, `apps/api/tests/test_governance_api.py`

- [x] Add failing tests for retry progress reset, stale running job recovery, and project filters.
- [x] Implement the smallest domain and repository changes to satisfy those tests.
- [x] Run job/governance tests and the full API suite.

### Task 3: Align runtime, Gel TLS, CI, and explicit capability behavior

**Files:**
- Modify: `GEL/scripts/gel-migrate.ps1`
- Modify: `GEL/README.md`
- Modify: `.github/workflows/ci.yml`
- Modify: `apps/api/app/runtime.py`
- Modify: `apps/worker/src/personlogy_worker/main.py`
- Modify: `compose.yaml`
- Test: `apps/api/tests/test_health.py`, `apps/api/tests/test_llm_adapters.py`

- [x] Add checks for secure default Gel configuration and explicit unsupported retrieval behavior.
- [x] Remove unconditional insecure TLS flags and raw password interpolation.
- [x] Make CI install the local core package and test current entrypoints instead of Alembic/PostgreSQL.
- [x] Share provider configuration between API and Worker and fail clearly when Gel retrieval is unavailable.

### Task 4: Verification and documentation

**Files:**
- Modify: `.gitignore`
- Modify: `README.md`
- Modify: `docs/plans/project-status-overview.md`

- [x] Add `.tmp/` and generated artifacts to ignore rules without removing user data.
- [x] Document recovery, TLS, capability flags, and current validation commands.
- [x] Run full backend tests, Ruff, mypy, frontend typecheck, and frontend build.


## Implementation outcome (2026-09-06)

All four tasks are implemented and validated. API and Worker now share `personlogy.runtime`;
API compatibility modules keep existing imports working. Worker deadlines and continuous
stale-running recovery use the persisted job state. Job filtering is performed before LIMIT
inside each repository. Frontend job/review lists send the selected project ID.

Additional defects found by real development testing were fixed: heuristic quotations must
preserve whitespace, and writeback audit metadata must permit governance_run_id,
schema_namespace and index_job_id. The writeback regression now uses a real audit store.

Validation: 91 backend tests passed with the real Gel suite enabled (zero skips), Ruff,
mypy (141 source files), frontend typecheck/build, real API/Worker + DeepSeek + SQLite
end-to-end workflow, and production container startup/job processing.
See `docs/engineering/system-optimization-validation-2026-09-06.md` for commands and evidence.

Scope boundary: vector retrieval, Chinese paraphrase evaluation, incremental indexing,
and a unified visual import pipeline remain follow-up work from the broader recommendation
list. Gel retrieval/indexing is explicitly unsupported; this iteration does not implement it.
