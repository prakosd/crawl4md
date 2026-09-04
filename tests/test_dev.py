from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

_DEV_PATH = Path(__file__).resolve().parent.parent / "dev.py"


def _load_dev():
    spec = importlib.util.spec_from_file_location("dev_runner", _DEV_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


dev = _load_dev()


def test_venv_bin_uses_platform_dir(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(dev.os, "name", "posix")
    assert dev._venv_bin("python") == dev.VENV_DIR / "bin" / "python"
    monkeypatch.setattr(dev.os, "name", "nt")
    assert dev._venv_bin("python") == dev.VENV_DIR / "Scripts" / "python.exe"


def test_playwright_args_adds_with_deps_only_on_linux(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(dev.platform, "system", lambda: "Linux")
    assert dev._playwright_args() == ["install", "--with-deps", "chromium"]
    monkeypatch.setattr(dev.platform, "system", lambda: "Darwin")
    assert dev._playwright_args() == ["install", "chromium"]


def test_install_builds_editable_install_command(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[list[str]] = []
    monkeypatch.setattr(dev, "VENV_DIR", tmp_path)  # exists → skip venv creation
    monkeypatch.setattr(dev.platform, "system", lambda: "Darwin")
    monkeypatch.setattr(dev.subprocess, "run", lambda cmd, **_: calls.append(cmd))

    dev.install()

    assert any(".[dev,all]" in c and "apps/streamlit[dev]" in c for c in calls)
    assert any(c[-1].endswith("crawl4ai-setup") for c in calls)
    assert any("playwright" in c and "chromium" in c for c in calls)


def test_run_requires_venv(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(dev, "VENV_DIR", tmp_path / "missing")
    with pytest.raises(SystemExit):
        dev.run()
