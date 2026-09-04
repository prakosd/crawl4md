# Development

← Back to [README](../README.md)

## Setup

```bash
python dev.py install   # create .venv and install everything (one command)
```

Prefer to manage the virtualenv yourself:

```bash
pip install -e ".[dev,all]" -e "apps/streamlit[dev]"
```

The distribution is `rag-playground`; `[all]` pulls every library extra
(`crawl`, `vector`, `bedrock`, `openai`) and `[dev]` adds pytest/ruff. To work on a
single library, install just its extra instead (e.g. `pip install -e ".[dev,vector]"`).
See [INSTALLATION.md](INSTALLATION.md) for the full extras matrix.

## Tests and lint

```bash
# Core library (includes artifact_store, vector_indexer, and rag_engine)
python -m pytest tests/ -q
python -m ruff check src/ tests/
python -m ruff format --check src/ tests/

# Streamlit app
python -m pytest apps/streamlit/tests/ -q
python -m ruff check apps/streamlit/streamlit_app.py apps/streamlit/app_pages/ apps/streamlit/src/ apps/streamlit/tests/
python -m ruff format --check apps/streamlit/streamlit_app.py apps/streamlit/app_pages/ apps/streamlit/src/ apps/streamlit/tests/
```

- Core tests (including `artifact_store`, `vector_indexer`, and `rag_engine`) live in `tests/`.
- Streamlit app helper tests live in `apps/streamlit/tests/`.
- Tests use mocked HTTP — no real network requests are made, no embedding
  models are downloaded (use fakes / explicit embeddings), and RAG tests use the
  offline echo chat model.

## Conventions

- Python 3.10+, type hints on all public APIs, Pydantic v2.
- No inline magic values — use `_UPPER_SNAKE_CASE` constants and module-level
  compiled regexes.
- Keep the libraries UI-independent: `log4py`, `crawl4md`, `artifact_store`,
  `vector_indexer`, and `rag_engine` must not import Streamlit. `log4py` is the
  zero-dependency base (no project imports at all). Boundary tests enforce this.
- All user-facing Streamlit text lives in the `i18n` catalog (English + Indonesian)
  and is referenced via `get_strings()` — never hardcoded in components.
- Logging goes through `log4py`: modules call `get_logger(__name__)` and only emit
  (`%`-style deferred args); the Streamlit app calls `configure_logging` once. Set
  `LOG_LEVEL=DEBUG` in `.env` for verbose local traces — the app writes each browser
  session's log under its own session folder (`logs/app.log`), viewable in the
  Files & folders panel. Never log secrets, PII, or prompt/query text. See
  [logging.instructions.md](../.github/instructions/logging.instructions.md).
- The Streamlit app's deployment-tunable, non-secret config lives in
  `app_support.settings` (`pydantic-settings`), loaded from `.env.defaults`
  → `.env` → environment; secrets (`AWS_*`, `OPENAI_API_KEY`) stay environment-only.
  See [CONFIGURATION.md](CONFIGURATION.md#environment-configuration--secrets-streamlit-app).
- Lint and format with **Ruff** (configured in `pyproject.toml`); the repo does not
  use Pylint. `.vscode/` disables the Pylint extension and recommends the Ruff
  extension so editor diagnostics match the CI gate.

## Component guides

| Component | Guide |
|---|---|
| Logging base | [src/log4py/README.md](../src/log4py/README.md) |
| Core crawler | [src/crawl4md/README.md](../src/crawl4md/README.md) |
| Shared foundation | [src/artifact_store/README.md](../src/artifact_store/README.md) |
| Vector indexer | [src/vector_indexer/README.md](../src/vector_indexer/README.md) |
| RAG engine | [src/rag_engine/README.md](../src/rag_engine/README.md) |
| Streamlit app | [apps/streamlit/README.md](../apps/streamlit/README.md) |
| Building another UI | [BUILDING_ANOTHER_UI.md](BUILDING_ANOTHER_UI.md) |

## Agent skills

Development guidance in this repository uses external agent skills:

- Streamlit app: [Developing with Streamlit](https://skills.sh/streamlit/agent-skills/developing-with-streamlit)
- Async Python patterns: [async-python-patterns](https://www.skills.sh/wshobson/agents/async-python-patterns)
- crawl4md library performance: [python-performance-optimization](https://www.skills.sh/wshobson/agents/python-performance-optimization)
- Python design patterns: [python-design-patterns](https://www.skills.sh/wshobson/agents/python-design-patterns)
- Python testing patterns: [python-testing-patterns](https://www.skills.sh/wshobson/agents/python-testing-patterns)
- Python project structure: [python-project-structure](https://www.skills.sh/wshobson/agents/python-project-structure)

### Three.js skills

Three.js development guidance is provided by 10 skill files sourced from
[CloudAI-X/threejs-skills](https://github.com/CloudAI-X/threejs-skills) (MIT),
installed via [skills.sh](https://www.skills.sh/):

| Skill | Covers |
|---|---|
| `threejs-fundamentals` | Scene setup, cameras, renderer, Object3D hierarchy, coordinate systems |
| `threejs-geometry` | Built-in shapes, BufferGeometry, custom geometry, instancing |
| `threejs-materials` | PBR, basic/phong/standard materials, shader materials |
| `threejs-lighting` | Light types, shadows, environment lighting |
| `threejs-textures` | Texture types, UV mapping, environment maps, render targets |
| `threejs-animation` | Keyframe animation, skeletal animation, morph targets, animation mixing |
| `threejs-loaders` | GLTF/GLB loading, texture loading, async patterns, caching |
| `threejs-shaders` | GLSL, ShaderMaterial, uniforms, custom effects |
| `threejs-postprocessing` | EffectComposer, bloom, DOF, screen effects, custom passes |
| `threejs-interaction` | Raycasting, controls, mouse/touch input, object selection |
