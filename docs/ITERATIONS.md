# ITERATIONS

- 2026-04-10: Began readability-focused refactor after multiple prompt/formatting iterations increased duplication.
- 2026-04-10: Split persisted search document handling into `agents/search_store.py`.
- 2026-04-10: Split final report post-processing into `agents/report_formatting.py`.
- 2026-04-10: Replaced broken `_calculate_latest_doc_ratio` usage with shared `calculate_latest_doc_ratio`.
- 2026-04-10: Collapsed duplicated web search collection loops into a shared helper and cleaned report evidence retrieval.
- 2026-04-10: Verified `py_compile` and `app.py --help` after refactor.
