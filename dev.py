#!/usr/bin/env python3
"""Developer task runner: one-command environment setup and app launch.

Run with the system Python (no virtualenv needed for ``install``)::

    python dev.py install   # create .venv and install everything
    python dev.py run       # launch the Streamlit app
    python dev.py test      # run the test suite and ruff checks

Every task operates on the project ``.venv``; ``install`` creates it on first
run. Uses only the standard library so it works before any dependency exists.
"""

from __future__ import annotations

import argparse
import os
import platform
import subprocess
import sys
import venv
from pathlib import Path

ROOT = Path(__file__).resolve().parent
VENV_DIR = ROOT / ".venv"
APP_ENTRY = ROOT / "apps" / "streamlit" / "streamlit_app.py"


def _venv_bin(name: str) -> Path:
    """Return the path to an executable inside the project virtualenv."""
    if os.name == "nt":
        return VENV_DIR / "Scripts" / f"{name}.exe"
    return VENV_DIR / "bin" / name


def _playwright_args() -> list[str]:
    """Browser-install arguments; ``--with-deps`` needs apt, so Linux only."""
    if platform.system() == "Linux":
        return ["install", "--with-deps", "chromium"]
    return ["install", "chromium"]


def _run(cmd: list[str | Path]) -> None:
    printable = " ".join(str(part) for part in cmd)
    print(f"\n$ {printable}", flush=True)
    subprocess.run([str(part) for part in cmd], cwd=str(ROOT), check=True)


def _require_venv() -> Path:
    python = _venv_bin("python")
    if not python.exists():
        sys.exit("Virtualenv not found — run `python dev.py install` first.")
    return python


def install() -> None:
    if VENV_DIR.exists():
        print(f"Using existing virtualenv at {VENV_DIR}")
    else:
        print(f"Creating virtualenv at {VENV_DIR} ...")
        venv.EnvBuilder(with_pip=True).create(VENV_DIR)
    python = _venv_bin("python")
    _run([python, "-m", "pip", "install", "--upgrade", "pip"])
    _run([python, "-m", "pip", "install", "-e", ".[dev,all]", "-e", "apps/streamlit[dev]"])
    _run([python, "-m", "playwright", *_playwright_args()])
    _run([_venv_bin("crawl4ai-setup")])
    print("\nSetup complete. Start the app with:  python dev.py run")


def run() -> None:
    _run([_require_venv(), "-m", "streamlit", "run", APP_ENTRY])


def test() -> None:
    python = _require_venv()
    _run([python, "-m", "pytest", "tests", "apps/streamlit/tests", "-q"])
    _run([_venv_bin("ruff"), "check", "."])


_COMMANDS = {"install": install, "run": run, "test": test}


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Developer task runner for rag-playground.")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("install", help="Create .venv and install all dependencies.")
    sub.add_parser("run", help="Launch the Streamlit app.")
    sub.add_parser("test", help="Run the test suite and ruff lint checks.")
    args = parser.parse_args(argv)
    try:
        _COMMANDS[args.command]()
    except subprocess.CalledProcessError as exc:
        sys.exit(exc.returncode)


if __name__ == "__main__":
    main()
