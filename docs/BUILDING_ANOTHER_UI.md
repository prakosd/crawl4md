# Building Another UI

← Back to [README](../README.md)

The bundled Streamlit app is a reference adapter over the `crawl4md` library, not a
required runtime. Another UI stack (such as React) can reproduce the same crawl
behavior and generated files by calling `crawl4md` from a Python backend or worker
and letting the library keep ownership of crawling, extraction, file writing, final
output generation, and YAML front matter.

To match the bundled app's behavior, build `CrawlerConfig` and `PageConfig`, create
a `ContentExtractor` and `FileWriter` from that page config, then run `SiteCrawler`
with the same optional integration hooks the Streamlit adapter uses: `output_base`,
`session_id`, `progress_callback`, and `should_cancel`. Your UI can render progress
from the emitted events and serve the generated files afterward, but it should not
reimplement the crawl pipeline or output writer if you want the same result structure.

`SiteCrawler` also writes `progress_history.jsonl` in each crawl root's `logs/`
subdirectory as a chart-ready cumulative timeline (page limit, discovered pages,
successful pages, failed pages, processed pages, elapsed seconds). UIs can read this
file to restore chart history after page reloads.

## Example adapter setup

```python
from crawl4md import CrawlerConfig, PageConfig, SiteCrawler
from crawl4md.extractor import ContentExtractor
from crawl4md.writer import FileWriter

crawler_config = CrawlerConfig(urls=["https://example.com"], limit=20, max_depth=2)
page_config = PageConfig(output_extension=".md")

extractor = ContentExtractor(page_config)
writer = FileWriter(
    max_file_size_mb=page_config.max_file_size_mb,
    file_extension=page_config.output_extension,
)

crawler = SiteCrawler(
    crawler_config,
    page_config,
    output_base="outputs/my_ui/session_123/crawl_001",
    session_id="session_123",
    extractor=extractor,
    writer=writer,
    progress_callback=lambda event: print(event),
    should_cancel=lambda: False,
)

results = crawler.crawl()
```

`crawl4md` is a Python library, so a browser-only frontend cannot run it directly.
A different frontend stack needs a Python service, worker, or desktop shell to call
the library.

## Structured messages — let the library own the wording

Every progress, warning, and error that needs to reach a user originates in the
libraries as **structured data**, never as UI-only strings. This keeps any frontend
(React, Vue, PHP, a CLI, an API server) able to render and localize the same
information without parsing English prose.

The shared primitive is `artifact_store.LibraryMessage`:

| Field | Meaning |
|---|---|
| `code` | Stable identifier, e.g. `"vector.model_unavailable"` or `"crawl.browser_missing"`. Map it to your own localized template. Never shown verbatim. |
| `default_text` | A complete English sentence. `str(message)` returns it, so logs and JSON stay readable when you have no localization. |
| `params` | Structured values behind the message (counts, file names, model ids) to interpolate into your localized template. |
| `severity` | `"info"`, `"warning"`, or `"error"`. |

`message.as_dict()` returns a JSON-serializable `{code, text, severity, params}` for
APIs and message queues.

**Vector indexing** returns these directly on the result:

```python
result = VectorIndexer().run(config, inputs, output_base)
for message in result.warnings + result.errors:
    payload = message.as_dict()          # send to your frontend
    text = my_i18n.get(payload["code"], payload["text"]).format(**payload["params"])
```

`manifest.json` records the same `code`/`text` for each warning and error.

**Crawling** surfaces messages two ways:

- Per-page failures set `CrawlResult.error_code` (e.g. `"crawl.blocked"`,
  `"crawl.empty_content"`) alongside the free-text `error`.
- Crawl-level warnings arrive through the `progress_callback` as `crawl_warning`
  events: `{"event": "crawl_warning", "code", "text", "severity", "params"}` — for
  example OCR-unavailable or "the site is blocking us, backing off". Classify a fatal
  crawl exception with `crawl4md.messages.classify_crawl_error(str(exc))` to get a
  coded `LibraryMessage` (missing browser, missing engine, TLS failure, or generic).

Because the classification lives in the libraries, your UI never has to substring-match
backend error text. Map codes to your own localized strings and fall back to
`default_text` for any code you have not translated yet. The Streamlit app's
`i18n.localize_message` helper is a minimal reference implementation of exactly this.

## Adding vector indexing to your UI

The same pattern applies to Step 2: call the `vector_indexer` library from your
backend. Build an `IndexingConfig`, then run `VectorIndexer.run(config, inputs,
output_base, progress_callback=..., should_cancel=...)`. It returns a structured
`IndexingResult` and writes a langchain-chroma index plus a `manifest.json`. The
embeddings (LangChain `Embeddings`) and vector store sit behind the library's
interfaces, so you can swap backends without changing your UI. See
[src/vector_indexer/README.md](../src/vector_indexer/README.md).

## Adding RAG (Steps 3-5) to your UI

Steps 3-5 are driven by the `rag_engine` library, callable from any UI exactly like
the crawler and indexer. Point it at an index directory produced by Step 2 (discover
them from the run `manifest.json`):

- **Semantic search (Step 3):** `retrieve(run_dir, query, RagConfig(...))` returns a
  `RetrievalResult` with ranked `RetrievedChunk`s (text, source, score).
- **QA (Step 4):** `answer_question(run_dir, question, RagConfig(...))` returns a
  `RagAnswer` (answer text, source chunks, `model_used`).
- **Conversational (Step 5):** `chat_answer(run_dir, question, history, RagConfig(...))`
  rewrites the follow-up from `history` before retrieving, then answers.

`RagAnswer` / `RetrievalResult` carry `warnings` / `errors` as the same
`LibraryMessage` data (codes `rag.*`), so your UI localizes them the same way. Chat
models resolve through LangChain's `init_chat_model`; with no cloud credentials the
library falls back to an offline echo model so the flow still runs. See
[src/rag_engine/README.md](../src/rag_engine/README.md).
