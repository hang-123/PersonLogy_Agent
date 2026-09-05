# Optimization review evidence
Reviewed current HEAD faebf1c; no business code modified.

Confirmed by offline reproduction:
- Unmatched LLM quote is attached to blocks[0]. Compilation validation checks identifiers, not quote text.
- Relation evidence on a block with no claim citation raises DomainValidationError.
- Progress 90 -> failure -> retry -> progress 20 raises DomainValidationError.
- SQLite running job with started_at one hour old and timeout_seconds=1 remains running after service reconstruction; not reclaimed.

Confirmed by source inspection:
- Compose starts personlogy_worker.main, whose compiler is fixed to DocumentHeuristicCompiler; it lacks API runtime provider and audit wiring.
- Core llm_openai imports httpx at module scope; core runtime dependencies omit it; API lists it only under dev. Clean production dependency installation therefore lacks a required client (image not built in this review).
- Non-SQLite API retrieval uses _EmptyRetrievalReader; Gel worker has no retrieval indexer.
- Embedding/reranker are instantiated but not consumed by retrieval service; answer concatenates retrieved claims.
- Job/review list APIs and screens do not receive selected project filtering.
- CI still invokes Alembic and missing migrations directory, and provisions PostgreSQL despite current backend architecture.
- Indexing deletes/rebuilds all project documents and queries citations once per claim; search loads evidence per hit.
- Existing plan still marks phases beyond P0 unstarted despite implemented code.

Verification: 19 selected existing backend tests passed; frontend typecheck passed. No full suite, live Gel, external LLM, UI browser or container build run.
Old UUID JSON serialization issue is already fixed at HEAD and covered by an existing test; do not report it again.
Original user deletions of root notes.md and task_plan.md were preserved.
Errors: sandbox process startup failure resolved through approved elevated execution; initial Windows wildcard rg operand failed, replaced with exact paths.
