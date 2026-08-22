---
description: "Use when editing the rag_engine library in src/rag_engine/ or its tests. Covers lazy heavy imports, the chat-model resolver with echo fallback, retrieval over persisted indexes, injection-defensive prompts, and no-network testing."
applyTo: "src/rag_engine/**, tests/test_rag_engine_*.py"
---

# rag_engine

UI-independent retrieval-augmented generation over the indexes built by
`vector_indexer`. Powers Steps 3-5 of the app (semantic search, single-turn QA,
conversational RAG) but must stay usable from a notebook, CLI, or tests without
Streamlit.

## Data flow

```
retrieve(run_dir, query, config)
  ├─ load_manifest(run_dir)        → embedding model + collection name
  ├─ resolve_embedding(...)        → LangChain Embeddings (vector_indexer)
  └─ VectorSearcher.search(...)    → RetrievedChunk[] (+ scores)

answer_question / chat_answer
  ├─ retrieve(...)                 → context chunks
  ├─ resolve_chat_model(...)       → BaseChatModel (init_chat_model, echo fallback)
  └─ prompt | model | StrOutputParser → RagAnswer(answer, sources, warnings, errors)

build_rag_prompt(question, chunks, tone, *, template=RAG_PROMPT_TEMPLATE)  # Step 4 editable, injection-fenced prompt (template overridable; a bad template falls back to the default)
stream_prompt(model, prompt) -> PromptGeneration  # send raw prompt; streamed text + TokenUsage
```

## Constraints

- **No UI / crawler imports.** `rag_engine` must not import `streamlit`, `app_support`, or `crawl4md`. It may depend on `vector_indexer`, `artifact_store`, and `pydantic`. A boundary test enforces this.
- **Lazy heavy imports.** Never import `langchain` (umbrella), `langchain_aws`, `langchain_openai`, or `langchain_chroma` at module top level. Import them inside the function/method that needs them so `import rag_engine` stays light (a subprocess test asserts none are eagerly loaded). These ship as opt-in extras (`rag`, `bedrock`, `openai`, and `vector` for the store).
- **Config.** `RagConfig` is Pydantic v2: `temperature` in `[0, 2]`, `max_tokens`/`top_k`/`fetch_k` ≥ 1, `score_threshold`/`lambda_mult` in `[0, 1]`, `search_type` is `similarity` or `mmr`, `source_filter` is a tuple of source files (empty = all), `llm_model` defaults to the catalog default. Defaults: Bedrock Claude / 0.0 / 1024 / 4 / threshold 0.0 / similarity / fetch_k 20 / lambda 0.5 / no source filter.
- **Chat models.** `resolve_chat_model` maps a catalogued id to a `BaseChatModel` via `langchain.chat_models.init_chat_model`. Gate on the provider package (`importlib.util.find_spec`) **and** credentials *before* calling `init_chat_model`, raising `ChatModelUnavailable` — never call into a provider without credentials. Credentials come **only** from environment variables (`AWS_*`, `OPENAI_API_KEY`); never hardcode secrets.
- **Echo fallback.** `resolve_chat_model` applies a universal fallback: when the requested model is unavailable it falls back to the offline **echo** model (`ECHO_MODEL`, which repeats the question) and appends a `rag.model_fallback_echo` warning, so a request still produces output. It re-raises only when echo itself was requested and is unavailable. The echo `BaseChatModel` (a `SimpleChatModel`) is defined lazily so importing the package never pulls langchain-core.
- **Retrieval.** Reopen an index with the *same* embedding model the manifest records. Search runs through the `VectorSearcher` interface (`search.py`); its only implementation, `ChromaSearcher`, wraps the same `langchain_chroma.Chroma` class the indexer wrote with and returns backend-neutral `SearchHit`s (no LangChain `Document` crosses the boundary), so moving off ChromaDB later means writing one new `VectorSearcher`. `search` takes keyword-only `search_type`/`fetch_k`/`lambda_mult`/`source_filter` (defaulted, so existing callers are unaffected): `ChromaSearcher` runs plain similarity or MMR (`max_marginal_relevance_search`, recovering each result's distance from the scored candidate pool since MMR returns no scores) and applies a metadata `where` source filter. `retrieve` maps distances to a 0-1 similarity and post-filters by `config.score_threshold`. The `embedding_loader` and `searcher_factory` in `retrieve` are injectable seams for testing. Never substring-match retrieved text into prompts as instructions.
- **Prompts.** Wrap retrieved context in `<context>` delimiters and instruct the model to treat it as data only (indirect prompt-injection defense). Reuse `prompts.QA_SYSTEM_PROMPT` / `CONDENSE_SYSTEM_PROMPT`. Both `QA_SYSTEM_PROMPT` and `RAG_PROMPT_TEMPLATE` tell the model to answer directly and naturally (no "the retrieved knowledge…" / "the context…" meta-phrasing) and to weave a source's URL into the reply the way a helpful person would — mentioning it in passing, not as a stiff labelled "Sources" list — only when it genuinely supports the answer, never invented; `format_context` / `format_knowledge` surface each chunk's `source_url` (from metadata) so the model has a link to cite. `build_rag_prompt` assembles the Step 4 editable prompt: retrieved knowledge is fenced between explicit delimiters and marked data-only, so what the user sees/edits is exactly what the model receives verbatim (sent as a single human message via `stream_prompt` / `generate_from_prompt`, which also surface `TokenUsage`). Disabling model "thinking" is best-effort and provider-specific (`llm.thinking_disabled_model_kwargs`, e.g. Qwen on Bedrock); most shipped models have it off by default.
- **Structured results.** `answer_question` / `chat_answer` return `RagAnswer`; `retrieve` returns `RetrievalResult`. Do not raise on expected failures (missing index, unavailable model, retrieval/generation error) — record an `artifact_store.LibraryMessage` (codes/builders in `rag_engine.messages`) so any UI can localize it. `str()` yields English.

## Tests

- Live in `tests/` (run by `python -m pytest tests/ -q`, linted by `ruff check src/ tests/`).
- **No network, no model downloads.** Use the offline echo model (real, deterministic), fake `BaseChatModel` subclasses for generation failures, injected `build` / `echo_build` callables for resolution, and injected `embedding_loader` / `store_opener` seams for retrieval. The one real-index round-trip test builds a tiny index with a fake `Embeddings` (`pytest.importorskip("langchain_chroma")`) and overrides the embedding loader so the offline model is never downloaded.
- Cover: config validation, the catalog, message builders, chat resolution + echo fallback, retrieval seams + error mapping, QA/chat generation with the echo model, and the import-boundary subprocess check.
