"""One package version, read from the installed metadata, shown identically everywhere."""

import subprocess
import sys
import tomllib
from importlib.metadata import version
from pathlib import Path

import ipo_engine

ROOT = Path(__file__).resolve().parent.parent


def test_package_version_comes_from_pyproject_only() -> None:
    declared = tomllib.loads((ROOT / "pyproject.toml").read_text())["project"]["version"]
    assert ipo_engine.__version__ == declared == version("ipo-engine")


def test_the_cli_prints_the_same_version() -> None:
    code = "import sys; from ipo_engine.cli import main; sys.exit(main(['--version']))"
    out = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True)
    assert out.returncode == 0
    assert out.stdout.strip() == f"ipo {ipo_engine.__version__}"


def test_frontend_version_matches_the_package() -> None:
    import json

    pkg = json.loads((ROOT / "frontend/package.json").read_text())["version"]
    assert pkg == ipo_engine.__version__
