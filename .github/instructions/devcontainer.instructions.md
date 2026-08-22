---
description: "Use when editing the dev container, pyproject.toml, or adding/removing Python or system dependencies. Covers shm size, Tesseract, Streamlit auto-start, port 8501, apt source fixes, and setup order."
applyTo: ".devcontainer/**, pyproject.toml"
---

# Dev Environment & Dependencies

Dev container is defined in `.devcontainer/devcontainer.json` (Python 3.12 + Chromium via Playwright + Tesseract OCR + Streamlit app forwarding).

## Constraints

- `--shm-size=2g` is required — Chromium crashes with Docker's default 64 MB `/dev/shm`.
- Tesseract `eng` + `msa` are pre-installed to match `PageConfig.ocr_languages` defaults.
- The yarn apt source is removed before `apt-get update` (expired GPG key in the base image).
- Setup order: `pip install -e '.[dev,all]' -e 'apps/streamlit[dev]'` → `playwright install --with-deps chromium` → `crawl4ai-setup`. The `all` extra pulls every library (`crawl`, `vector`, `bedrock`, `openai`, `rag`); `dev` adds the test/lint tools.
- Port `8501` is forwarded for the Streamlit app and should keep the `Streamlit rag-playground app` label.
- `postAttachCommand` starts Streamlit with `python -m streamlit run apps/streamlit/streamlit_app.py --server.address=0.0.0.0 --server.port=8501`; keep `0.0.0.0` so forwarded ports work from containers and Codespaces.
- `ANONYMIZED_TELEMETRY=False` is set in `containerEnv` to disable ChromaDB telemetry.

## Dependencies

The distribution is named `rag-playground`. The base install carries **no**
third-party dependencies (the `artifact_store` library is pure standard library);
every library is an opt-in extra in the root `pyproject.toml` so installs stay
lightweight and atomic:

- `crawl` → `crawl4ai`, `trafilatura`, `markdownify`, `beautifulsoup4`, `mdformat`,
  `mdformat-gfm`, `nest-asyncio`, `httpx`, `pydantic`, `pymupdf4llm`, `mammoth` (the
  crawler; `mammoth` converts `.docx` and is pure Python, so it needs no system package).
- `vector` → `langchain-chroma`, `langchain-text-splitters`, `langchain-core`, `pydantic`
  (chunking + vector store; pulls `chromadb` transitively; local offline embeddings work
  with just this).
- `bedrock` → `langchain-aws` (Amazon Titan embeddings + Bedrock chat models; pulls `boto3`).
- `openai` → `langchain-openai` (OpenAI embeddings + chat models; pulls `openai`).
- `rag` → `langchain` (umbrella) + `langchain-core` + `pydantic` (`rag_engine`: retrieval +
  QA + conversational RAG; `init_chat_model` for provider switching).
- `all` → `crawl` + `vector` + `bedrock` + `openai` + `rag` (convenience meta-extra).

Streamlit app dependencies, including `streamlit`, live in `apps/streamlit/pyproject.toml`;
the app depends on `rag-playground[crawl,vector,bedrock,openai,rag]` so installing it pulls the
crawler, indexing backends, and the RAG engine. It also pulls `python-dotenv` and
`pydantic-settings` for the app's env-driven, non-secret settings layer
(`app_support.settings`, loaded `.env.defaults` → `.env` → environment), and `PyYAML`
for the RAG model pricing/metadata catalog (`config/model_pricing.yaml`, read by
`app_support.model_pricing`).

Cloud embedding credentials are read from the environment (`AWS_ACCESS_KEY_ID`,
`AWS_SECRET_ACCESS_KEY`, `AWS_REGION`, `OPENAI_API_KEY`). See `.env.example`. In
Codespaces/CI, set them as environment secrets/variables; never commit real values.
The offline default embedding model needs no credentials.

When adding or removing a Python or system dependency, also update `.devcontainer/devcontainer.json` to keep the image in sync.
