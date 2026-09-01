# Review: latest two commits

Scope: `722552a` and `9a07fae`.

## Findings

1. **Blocking — LLM compilation fails when the model returns a relation.**
   `packages/personlogy_core/src/personlogy/adapters/llm_openai.py:403-409` places UUID objects directly into `bundle.okf`; `CompilationService` serializes that object with `json.dumps`. Any non-empty relation result therefore fails with `TypeError: Object of type UUID is not JSON serializable`. This was confirmed by a minimal reproduction using the existing test payload.

2. **Important — LLM OKF claims do not follow the existing v0.2 shape.**
   `packages/personlogy_core/src/personlogy/adapters/llm_openai.py:400` emits `subject=claim.statement` and omits the established `id`, `subject_id`, `status`, and `citation_ids` fields used by the heuristic compiler. This breaks OKF contract/consumer compatibility.

3. **Important — invalid quotes are silently attached to the first content block.**
   `packages/personlogy_core/src/personlogy/adapters/llm_openai.py:425-432` falls back to `blocks[0]` when the quote is empty or unmatched, despite the documented requirement that quotes must be present verbatim in source content. This can create false provenance.

4. **Important — relation-only evidence aborts compilation.**
   `packages/personlogy_core/src/personlogy/adapters/llm_openai.py:385-386` looks up relation citations only among citations created for claims. A valid relation whose evidence block has no claim citation raises `DomainValidationError`.

5. **Blocking security — a plaintext Gel credential was committed in `notes.md`.**
   The note contains a concrete local DSN/password and a machine-specific compose-file path. Even if this is a development credential, rotate it and remove it from repository history; do not merely edit the current file.

6. **Important security — the Gel script forces insecure TLS.**
   `GEL/scripts/gel-migrate.ps1:68,80,96,106,110,130` passes `--tls-security insecure` for every migration/query, including when a custom remote DSN is supplied. This can disable certificate verification and expose credentials on a non-local connection; make insecure mode an explicit local-only opt-in.

7. **Important — test artifacts were committed.**
   The two commits add 149 `.tmp/accept` paths, about 20.3 MB of PDFs, SQLite databases, and test output. The repository has no matching ignore rule. Remove them from the commits/history as appropriate and ignore `.tmp/`.

8. **Suggestion — password interpolation in the Gel script is not DSN-safe.**
   `GEL/scripts/gel-migrate.ps1:48-50` inserts the raw password into a DSN. URL-reserved characters can produce an invalid DSN, and the resulting command line may expose the password to process inspection.

9. **Important — malformed provider responses are not normalized to the documented domain error.**
   Invalid JSON from `/chat/completions` at `llm_openai.py:115` raises `JSONDecodeError`, while malformed embedding/rerank entries can raise `AttributeError` instead of `DomainValidationError`. Add response-shape tests before enabling these adapters in workers.

## Verification

- LLM adapter tests: passed (`6 passed`).
- API test suite: passed; Gel integration tests were skipped in this environment.
- Ruff on changed Python files: passed.
- `git diff --check`: reports trailing whitespace in committed PDF test artifacts.

## Verdict

Request changes before treating the LLM-enabled path as ready. The Gel schema/migration additions are directionally sound, but the LLM data-contract/serialization issues and committed credential need remediation first.
