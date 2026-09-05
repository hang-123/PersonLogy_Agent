# Prioritized optimization recommendations
1. Unify API and deployed Worker configuration, service composition and instrumentation; declare httpx as a runtime dependency.
2. Reject unmatched source quotations, add quote offsets and independent relation citations; unify OKF contracts.
3. Reset or separately track retry progress; implement execution deadlines and leased-job recovery.
4. Implement Gel indexing/retrieval or expose unsupported capability explicitly; avoid silently empty results.
5. Scope job/review listing by project on the backend; make import stages visible as one pipeline in the UI.
6. Align CI with local core package, SQLite/Gel adapters and actual worker entrypoint; add isolated container startup checks.
7. Once correctness is addressed, connect vector retrieval/reranking, evaluate Chinese paraphrase recall, and batch/incrementally update indexes.
Validation: 19 existing backend tests and frontend typecheck passed. Four focused offline failure probes confirmed gaps described in notes.md.
