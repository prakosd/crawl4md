# rag_engine

UI-independent retrieval-augmented generation over the vector indexes built by
[`vector_indexer`](../vector_indexer/README.md). It powers **Steps 3-5** of the
app — semantic search, single-turn QA, and conversational (history-aware) RAG —
and stays usable from a notebook, CLI, or tests without Streamlit.

## Data flow

```
retrieve(run_dir, query, config)            # Step 3
  ├─ load_manifest(run_dir)                  → embedding model + collection name
  ├─ resolve_embedding(model, dim)           → LangChain Embeddings (or raises if unavailable)
  └─ VectorSearcher.search(...)               → RetrievedChunk[] (+ similarity scores)

answer_question(run_dir, question, config)  # Step 4 (one-call convenience)
  ├─ retrieve(...)                           → context chunks
  ├─ resolve_chat_model(llm_model)           → BaseChatModel (init_chat_model, echo fallback)
  └─ prompt | model | StrOutputParser        → RagAnswer(answer, sources, warnings, errors)

build_rag_prompt(question, chunks, tone, *, template=RAG_PROMPT_TEMPLATE)  # Step 4 editable prompt; template overridable
  └─ format_knowledge(chunks)                → source-labelled, delimiter-fenced knowledge
stream_prompt(chat_model, prompt)           # Step 4 (send the raw prompt, streamed)
  └─ PromptGeneration                        → streams answer text; exposes TokenUsage after

chat_answer(run_dir, question, history, config)  # Step 5 (simple, history-aware)
  ├─ condense_question(model, history, q)    → standalone search query
  ├─ retrieve(...)                           → context chunks
  └─ generate_chat_answer(...)               → RagAnswer (history-aware)

conversational_answer(run_dir, question, state, config)  # Step 5 (advanced pipeline)
  ├─ plan_queries(...)                       → QueryPlan (decompose via aux model)
  ├─ retrieve_multi(...)                     → merged, deduped chunks (parallel)
  ├─ rerank_chunks(...)                      → off / local cross-encoder / LLM
  ├─ generate_chat_answer(...)               → grounded answer
  ├─ suggest_followups / validate_followups  → ValidatedFollowup[] (answerable only)
  └─ update_state(...)                       → next ConversationState
                                             → ConversationalAnswer (+ plan, timings)
```

## Install

```bash
pip install -e ".[vector,rag]"            # retrieval + QA + chat (offline echo model)
pip install -e ".[vector,rag,bedrock]"    # + Amazon Bedrock chat models (langchain-aws)
pip install -e ".[vector,rag,openai]"     # + OpenAI chat models (langchain-openai)
```

`rag_engine` depends on `vector_indexer` to open indexes, so the `vector` extra is
always required alongside `rag`. Cloud chat models are additional opt-in extras.

## Quick start

```python
from rag_engine import RagConfig, answer_question

config = RagConfig(llm_model="anthropic.claude-3-5-sonnet-20240620-v1:0", top_k=4)
answer = answer_question(run_dir, "What does the API return on error?", config)

print(answer.answer)              # generated answer (or an echo when no credentials)
for chunk in answer.sources:      # the retrieved context, with provenance + score
    print(chunk.source, round(chunk.score, 3))
for message in answer.warnings:   # structured LibraryMessage warnings (e.g. echo fallback)
    print(message)
```

`run_dir` is a timestamped index directory produced by `VectorIndexer.run`.

## Design

### Chat models — one interface, graceful fallback

The application layer never depends on a specific LLM SDK. `resolve_chat_model`
maps a catalogued model id to a LangChain `BaseChatModel` through the umbrella
`langchain` package's `init_chat_model`, gating on the provider package and
credentials **before** construction so the offline path never touches the network.
When a requested cloud model is unavailable it falls back to the offline **echo**
model (which repeats the question instead of generating an answer) and appends a
warning, so the workflow always produces output. Credentials come **only** from
environment variables (`AWS_*`, `OPENAI_API_KEY`).

`CHAT_MODEL_OPTIONS` / `get_chat_model_info` expose the catalog (Bedrock, OpenAI,
echo — each with a `size` of small/medium/large and an offline/cloud `kind`) for a
UI to render a model picker without constructing anything.

### Retrieval — reopen the exact index

`retrieve` reads the run `manifest.json` to learn which embedding model and
collection produced the vectors, rebuilds the matching embeddings with
`vector_indexer.resolve_embedding`, and runs the query through a `VectorSearcher`
— a small backend-neutral interface (`search.py`). Its only implementation,
`ChromaSearcher`, reopens the collection with the same `langchain_chroma.Chroma`
class the indexer wrote with (guaranteeing on-disk compatibility) and returns
plain `SearchHit`s, so no LangChain types leak across the boundary. Swapping
vector backends later means writing one new `VectorSearcher`, not touching the
pipeline. The embedding loader and `searcher_factory` are injectable so the flow
can be tested without ChromaDB or network access.

### Prompts — injection-defensive

Retrieved context is wrapped in `<context>` delimiters and the model is told to
treat it as data only and never follow instructions embedded inside it (see
`prompts.py`). The prompts also tell the model to answer directly and naturally —
no "the retrieved knowledge…" / "the context…" meta-phrasing — and to weave a
source's URL into the reply the way a helpful person would (mentioning it in
passing, not as a stiff labelled "Sources" list) only when it genuinely
supports the answer, never invented; `format_context` / `format_knowledge`
surface each chunk's `source_url` from its metadata so a link is available to
cite. `build_rag_prompt` (Step 4) assembles a complete, human-readable
prompt whose retrieved knowledge is fenced between explicit delimiters and marked
data-only, so a UI can show and edit exactly what the model receives. Its outer
wording is overridable via the `template` keyword — a template missing a required
`{question}`/`{start}`/`{knowledge}`/`{end}`/`{tone}` field falls back to the
built-in default — while the fenced, data-only knowledge block is always the
library's.

### Structured results

`answer_question` / `chat_answer` return a `RagAnswer` (answer text, source
chunks, `model_used`, and `warnings` / `errors` as
[`artifact_store.LibraryMessage`](../artifact_store/README.md) objects with stable
codes); `retrieve` returns a `RetrievalResult`. They never raise on expected
failures (missing index, unavailable model) — they record a structured error so a
UI can render it. Message codes/builders live in `rag_engine.messages`.

## Module map

| Module | Responsibility |
|---|---|
| `config.py` | `RagConfig` (Pydantic v2): `llm_model`, `temperature`, `max_tokens`, `top_k`, `score_threshold`, `search_type`, `fetch_k`, `lambda_mult`, `source_filter`; `ConversationalConfig` (Step 5 stage flags + thresholds, wraps a `RagConfig`) |
| `catalog.py` | `ChatModelInfo`, `CHAT_MODEL_OPTIONS` (Bedrock Nova/Claude APAC profiles + Qwen3/Gemma/Mistral/NVIDIA in-Region + OpenAI Direct API, echo; sorted by cloud → provider → size → name), `DEFAULT_CHAT_MODEL` (pinned to Bedrock Claude), `ECHO_MODEL` |
| `llm/` | `resolve_chat_model` (init_chat_model + echo fallback), `resolve_auxiliary_model` (small helper model for Step 5), `thinking_disabled_model_kwargs`, lazy echo model |
| `retrieval.py` | reopen a persisted index via a `VectorSearcher`, run similarity or MMR search with an optional source filter, post-filter by score threshold (Step 3); `retrieve_multi` (parallel per-sub-question, deduped) |
| `search.py` | `VectorSearcher` interface + `ChromaSearcher` + backend-neutral `SearchHit` |
| `prompts.py` | QA + condense-question prompts, context formatting; `build_rag_prompt` / `format_knowledge` (Step 4); Step 5 auxiliary templates + tolerant JSON parsers |
| `qa.py` | `answer_question` / `generate_answer` / `stream_answer`; `stream_prompt` / `generate_from_prompt` (raw editable prompt, Step 4) |
| `chat.py` | `chat_answer` / `condense_question` / `generate_chat_answer`; `conversational_answer` (advanced Step 5 pipeline) |
| `decompose.py` | `plan_queries` (reference resolution + decomposition) + `update_state` (rolling conversation state) |
| `rerank.py` | `rerank_chunks` (off / local cross-encoder / LLM), lazy `load_cross_encoder` |
| `followups.py` | `suggest_followups` + `validate_followups` (probe-retrieve + threshold gate) + `answerability_check` |
| `models.py` | `RetrievedChunk`, `RagAnswer`, `ChatTurn`, `TokenUsage`; `QueryPlan`, `ConversationState`, `ValidatedFollowup`, `ConversationalAnswer` |
| `messages.py` | stable `rag.*` message codes + builders |

## Constraints

- **No UI / crawler imports.** `rag_engine` must not import `streamlit`,
  `app_support`, or `crawl4md`. It may depend on `vector_indexer`,
  `artifact_store`, and `pydantic`. A boundary test enforces this.
- **Lazy heavy imports.** `langchain` (umbrella), `langchain_aws`,
  `langchain_openai`, and `langchain_chroma` are imported inside the functions
  that need them, so `import rag_engine` stays light.
