# Review: latest two commits

Scope: `722552a` and `9a07fae`.

## Findings

1. **Blocking — LLM compilation fails when the model returns a relation.**
   `llm_openai.py` places UUID objects directly into `bundle.okf`; `CompilationService` serializes that object with `json.dumps`, producing `TypeError: Object of type UUID is not JSON serializable`. Reproduced with the existing test payload.

2. **Important — LLM OKF claims do not follow the existing v0.2 shape.**
   The adapter emits `subject=claim.statement` and omits `id`, `subject_id`, `status`, and `citation_ids`, unlike the heuristic compiler. This makes the output incompatible with the established OKF contract.

3. **Important — invalid quotes are silently attached to the first content block.**
   `_find_block` falls back to `blocks[0]` when the quote is empty or unmatched, despite the documented requirement that quotes must be present verbatim in source content. This can create false provenance.

4. **Important — relation-only evidence aborts compilation.**
   Relation citations are looked up only among citations created for claims. A valid relation whose evidence block has no claim citation raises `DomainValidationError`.

5. **Important — test artifacts were committed.**
   The two commits add 149 `.tmp/accept` paths, about 20.3 MB of PDFs, SQLite databases, and test output. The repository has no matching ignore rule. These should be removed from the commits/history as appropriate and `.tmp/` should be ignored.

6. **Suggestion — password interpolation in the Gel script is not DSN-safe.**
   `gel-migrate.ps1` inserts the raw password into a DSN. Passwords containing URL-reserved characters can produce an invalid DSN, and the resulting command line may expose the password to process inspection.

## Verification

- LLM adapter tests: passed (`6 passed`).
- API test suite: passed; Gel integration tests were skipped in this environment.
- Ruff on changed Python files: passed.
- `git diff --check`: reports trailing whitespace in committed PDF test artifacts.

## Verdict

Request changes before treating the LLM-enabled path as ready. The Gel schema/migration additions are directionally sound, but the two blocking data-contract issues in the LLM adapter need fixes and regression tests first.
