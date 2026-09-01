---
description: "Use when writing or editing tests under tests/ or apps/streamlit/tests/. Covers mocking policy, required coverage per change, app linting, and how to invoke the test-runner agent."
applyTo: "tests/**, apps/streamlit/tests/**"
---

# Testing Rules

- Every code change needs unit tests (happy path + key edge cases). Bug fixes need a reproducing test.
- **Tests use mocked HTTP — never real network requests.** No real filesystem outside `tmp_path` / fixtures.
- **Never download embedding models.** `vector_indexer` tests must use a fake `Embeddings`, `pytest.importorskip` for the langchain-chroma store, and an injected embedding resolver — the offline embedder downloads ~80 MB on first use. `rag_engine` tests must never make network calls: use the offline echo model (real, deterministic), fake `BaseChatModel` subclasses for generation failures, and injected resolver / `embedding_loader` / `store_opener` seams; the boundary/lazy-import subprocess check forbids eager `langchain`/`langchain_aws`/`langchain_openai`/`langchain_chroma`/`sentence_transformers`. **Never download the cross-encoder:** re-ranking tests inject a fake `encoder_loader` / `chat_model` and simulate `ImportError`, and `conversational_answer` tests use `reranker="off"` (or inject fakes) so the local cross-encoder is never loaded.
- Tests are focused — do not assert many unrelated things in one test.
- Core tests run via `python -m pytest tests/ -q`. Core lint runs via `python -m ruff check src/ tests/` and `python -m ruff format --check src/ tests/`.
- Streamlit app tests run via `python -m pytest apps/streamlit/tests/ -q`. App lint runs via `python -m ruff check apps/streamlit/streamlit_app.py apps/streamlit/app_pages/ apps/streamlit/src/ apps/streamlit/tests/` and `python -m ruff format --check apps/streamlit/streamlit_app.py apps/streamlit/app_pages/ apps/streamlit/src/ apps/streamlit/tests/`.
- **Delegate test/lint runs to the `test-runner` agent.** It uses a two-pass strategy (quiet first, verbose re-run of failures only) and is required because the suite is ~500 tests — full verbose output is too large for the main context.
- Task is complete only when both tests AND linting are clean.

## Streamlit Tests (apps/streamlit/**)

**Do not test:** static rendering (`st.title`/`st.markdown`/etc.), exact labels, layout, styling, spacing, ordering, icons, individual widgets, Streamlit framework behavior, or chart styling (colors, legend, axes). For charts, test only the data — counts, time/series values, row shapes — never the visual style.

**Do test:** pure business/data logic (transforms, filtering, aggregation, validation, formatting), auth/permission logic, integration behavior (API/file/browser-storage/crawl-job) with mocks, error handling for invalid input, critical user flows where a broken UI corrupts output, and an app-startup smoke test.

Prefer extracting testable logic out of `streamlit_app.py` into pure modules (`app_support.support`, `controls`, etc.) and test those instead of mocking Streamlit calls. When reviewing existing tests, recommend removing ones that only assert static UI, visual layout, or framework behavior.
