# vector_indexer

UI-independent Python library that turns text documents into a persisted vector
index. It powers **Step 2 — Build Vector Index** in the Streamlit app, but it has
no Streamlit dependency and is equally usable from any UI, a CLI, or tests.

## What it does

```
VectorIndexer.run(config, inputs, output_base)
  ├─ resolve_embedding()      → LangChain Embeddings (or raises if unavailable)
  ├─ load_documents()         → .md / .txt files and .zip members (via artifact_store)
  ├─ split_into_pages()       → drop crawl run metadata, recover per-page title/url (page_source)
  ├─ chunk_documents()        → overlapping chunks, each stamped with a Source line (langchain-text-splitters)
  └─ embed batches (parallel for cloud models) → ChromaVectorStore.add_embeddings / persist
        → vector_<id>/<timestamp>/chroma  +  manifest.json
```

The result is a structured `IndexingResult` (success flag, output directory,
indexed/skipped counts, warnings, errors) that any caller can render. `warnings` and
`errors` are `artifact_store.LibraryMessage` objects: each carries a stable `code`
plus structured `params`, and `str(message)` yields a ready-to-show English
sentence. A UI localizes by `code` and falls back to that text. See
[docs/BUILDING_ANOTHER_UI.md](../../docs/BUILDING_ANOTHER_UI.md).

## Install

The backends are opt-in extras on the `rag-playground` distribution (the library
ships inside it):

```bash
pip install -e ".[vector]"            # langchain-chroma + langchain-text-splitters + langchain-core
pip install -e ".[vector,bedrock]"    # + langchain-aws for Amazon Titan
pip install -e ".[vector,openai]"     # + langchain-openai
```

## Quick start

```python
from vector_indexer import IndexingConfig, VectorIndexer

config = IndexingConfig(
    chunk_size=600,
    chunk_overlap=100,
    embedding_model="amazon.titan-embed-text-v2:0",
    embedding_dimension=512,
    language="english",
)

indexer = VectorIndexer()
result = indexer.run(
    config,
    inputs=["outputs/.../final/sorted_success_content_001.md", "notes.zip"],
    output_base="outputs/.../vector_01_navigate",
)

print(result.success, result.indexed_chunk_count, result.warnings)
```

## Supported inputs

- `.md` and `.txt` files.
- `.zip` archives — only their `.md` / `.txt` members are indexed; everything else
  is ignored. Extraction is zip-slip-safe (handled by `artifact_store.archives`).

Unsupported or unreadable inputs are skipped and reported in `IndexingResult.warnings`
as `LibraryMessage` objects (e.g. code `vector.skipped_unsupported_file`).

## Page-aware indexing

crawl4md output begins with a YAML *front matter* block (crawl run metadata) and wraps
each page's human-readable header (title + `*Source: <url>*`) in render-invisible markers
(`<!-- crawl4md:source -->` … `<!-- /crawl4md:source -->`). `page_source.split_into_pages`
strips the front matter so run metadata never reaches a chunk, splits the body into pages,
and recovers each page's title/URL. `chunk_documents` then prepends a
`Source: [title](url)` line to every chunk and copies the title/URL into chunk metadata
(`source_title`, `source_url`) so retrieval can cite the page. Inputs without markers
(plain `.txt` or non-crawl4md Markdown) degrade to a single untitled page and get no Source
prefix. The marker strings are duplicated in `crawl4md.writer` with a "keep in sync" note;
`vector_indexer` does **not** import `crawl4md`.

## Progress reporting

`VectorIndexer.run` accepts an optional `progress_callback`. It receives two kinds
of event mappings: coarse stage markers `{"stage": ...}` (`resolving_model` →
`loading` → `chunking` → `embedding` → `saving`) emitted at pipeline boundaries, and
per-batch counts `{"processed_chunks": n, "total_chunks": m}` during embedding. A UI
can show the current stage before chunk counts are available, then switch to a ratio
bar. Cancellation stays cooperative via `should_cancel`.

## Embedding models

The application layer never depends on a specific embedding SDK: every backend is a
LangChain `langchain_core.embeddings.Embeddings` object, built by `build_embeddings`
and wrapped in a `ResolvedEmbedding(embeddings, model_id, dimension)`. Models are
selected by id:

| Model id | Backend | Requirement |
|---|---|---|
| `amazon.titan-embed-text-v2:0` *(default)* | `langchain-aws` `BedrockEmbeddings` | `langchain-aws` + AWS credentials |
| `text-embedding-3-small` | `langchain-openai` `OpenAIEmbeddings` | `langchain-openai` + `OPENAI_API_KEY` |
| `all-MiniLM-L6-v2` | Offline ONNX (ChromaDB), wrapped as an `Embeddings` adapter | none (downloads ~80 MB on first use) |
| `BAAI/bge-*`, `intfloat/e5-*`, `sentence-transformers/*` | known but **disabled** (not shown in UI) | not installed (no PyTorch) |

**Graceful failure (no silent fallback).** When a backend's package or credential is
missing, `build_embeddings` raises `EmbeddingProviderUnavailable` and `resolve_embedding`
propagates it — there is **no automatic fallback** to the local offline model, so a
failed cloud model surfaces an actionable error instead of silently switching backends
(which would change the index's embeddings). The indexer records that error on
`IndexingResult.errors`, classified by cause via `classify_model_unavailable`
(`vector.missing_openai_key`, `vector.missing_aws_credentials`, or the generic
`vector.model_unavailable`), so a UI can guide the user. The local offline model
(`all-MiniLM-L6-v2`) is always selectable explicitly and needs no credentials or network
after its one-time download.

**Model metadata (no provider construction).** `get_embedding_model_info(model_id)`
and `EMBEDDING_MODEL_INFOS` expose static `EmbeddingModelInfo` records — `kind`
(`"local"`/`"cloud"`), `requires_api_key`, `one_time_download`, the supported
embedding dimensions (a discrete tuple, or `None` for a `min`/`max` range), and the
default dimension — so a UI can label models and constrain dimension inputs without
touching the network or any credentials.

### Offline model & corporate TLS

The offline `all-MiniLM-L6-v2` model runs locally, but ChromaDB downloads it once
over HTTPS on first use (~80 MB). On networks that intercept TLS with a private
root CA, that one-time download can fail with a certificate error. Point any of
`SSL_CERT_FILE`, `REQUESTS_CA_BUNDLE`, or `CURL_CA_BUNDLE` at your corporate CA
bundle; the library mirrors a configured value across these variables before the
download so it can succeed. After the first successful download the model is cached
and no network is needed.

## Credentials

Credentials are read only from the environment — never hardcoded:

- Amazon Titan: `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, `AWS_REGION`.
- OpenAI: `OPENAI_API_KEY`.

See [`.env.example`](../../.env.example). In Codespaces/CI, set them as
environment secrets/variables.

## Vector store

`VectorStore` (an ABC with `add_texts` / `persist`) hides the database.
`ChromaVectorStore` is the default implementation; it wraps `langchain_chroma.Chroma`
with an explicit `embedding_function`, so each batch is embedded by the resolved
model and written to a persistent ChromaDB collection under `<run>/chroma/`. The
same `Chroma` class reopens the collection for retrieval (see **Reading an index
back**), which guarantees the on-disk format matches.

## Reading an index back

Each run writes a `manifest.json` (via `manifest.py`) recording the embedding model,
dimension, `collection_name`, the run's `created_at` (ISO-8601 UTC, derived from the
run-directory timestamp; `None` for older manifests), and `indexed_sources` (the distinct
source files that produced chunks, for the Step 3 source filter; `()` for older manifests).
`load_manifest(run_dir)` returns a typed
`IndexManifest`, and the constants `DEFAULT_COLLECTION_NAME` / `CHROMA_SUBDIR` locate
the collection on disk. The [`rag_engine`](../rag_engine/README.md) library uses these
to reopen an index with the same embeddings and run retrieval (Steps 3-5).

## Module map

| Module | Responsibility |
|---|---|
| `config.py` | `IndexingConfig` (Pydantic v2 validation) |
| `models.py` | `Document`, `Chunk`, `IndexingResult` |
| `manifest.py` | `IndexManifest`, `load_manifest` / `write_manifest`, collection + layout constants |
| `languages.py` | `LUCENE_LANGUAGES`, `DEFAULT_LANGUAGE` |
| `document_loader.py` | load `.md` / `.txt` / `.zip` into documents |
| `page_source.py` | strip crawl run metadata, split crawl4md output into per-page sections, build the `Source: [title](url)` line (pure stdlib) |
| `chunking.py` | overlapping chunks via langchain-text-splitters, each stamped with its page Source line |
| `embeddings/` | LangChain `Embeddings` builders, catalog, registry, resolution policy |
| `vector_store/` | `VectorStore` interface and `ChromaVectorStore` (langchain-chroma) |
| `indexer.py` | `VectorIndexer.run` orchestration |
