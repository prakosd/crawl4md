from __future__ import annotations

import ast
import os
import subprocess
import sys
from pathlib import Path

import rag_engine

_RAG_ENGINE_SRC = Path(__file__).resolve().parents[1] / "src" / "rag_engine"
_FORBIDDEN_IMPORT_PREFIXES = ("streamlit", "crawl4md")
_HEAVY_BACKENDS = (
    "langchain",
    "langchain_aws",
    "langchain_openai",
    "langchain_chroma",
    "chromadb",
    "sentence_transformers",
)


def _imported_modules(path: Path) -> list[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    modules: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            modules.append(node.module)
    return modules


def test_rag_engine_does_not_depend_on_ui_or_crawler() -> None:
    for path in _RAG_ENGINE_SRC.rglob("*.py"):
        for module in _imported_modules(path):
            assert not module.startswith(_FORBIDDEN_IMPORT_PREFIXES), (
                f"{path.name} imports {module!r}"
            )


def test_importing_package_does_not_eagerly_load_heavy_backends() -> None:
    src_dir = str(_RAG_ENGINE_SRC.parent)
    env = os.environ.copy()
    env["PYTHONPATH"] = os.pathsep.join(
        part for part in (src_dir, env.get("PYTHONPATH", "")) if part
    )
    backends = ", ".join(repr(name) for name in _HEAVY_BACKENDS)
    code = (
        "import sys, rag_engine; "
        f"loaded = [m for m in ({backends},) if m in sys.modules]; "
        "raise SystemExit(loaded or 0)"
    )

    result = subprocess.run(
        [sys.executable, "-c", code],
        capture_output=True,
        env=env,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr or result.stdout


def test_public_api_is_importable() -> None:
    assert "answer_question" in rag_engine.__all__
    assert "chat_answer" in rag_engine.__all__
    assert "RagConfig" in rag_engine.__all__
    assert "retrieve" in rag_engine.__all__
