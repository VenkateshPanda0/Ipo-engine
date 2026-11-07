"""
Import-boundary tests for the documented architecture.

These tests parse source files instead of importing modules, so they catch
violations without triggering side effects.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

APP_ROOT = Path(__file__).resolve().parents[3] / "src" / "ipo_engine" / "screening"

_INFRA = ("ipo_engine.screening.api", "ipo_engine.screening.services", "ipo_engine.screening.db")
BOUNDARY_RULES = {
    # Document intelligence extracts facts; it never evaluates rules.
    "intelligence": (
        "ipo_engine.screening.rules",
        "ipo_engine.screening.engine",
        "ipo_engine.screening.regulatory",
        *_INFRA,
    ),
    # Rules and engine are pure: no extraction, persistence or HTTP.
    "rules": ("ipo_engine.screening.intelligence", *_INFRA),
    "engine": ("ipo_engine.screening.intelligence", *_INFRA),
    "regulatory": (
        "ipo_engine.screening.rules",
        "ipo_engine.screening.engine",
        "ipo_engine.screening.intelligence",
        *_INFRA,
    ),
    "models": (
        "ipo_engine.screening.intelligence",
        "ipo_engine.screening.rules",
        "ipo_engine.screening.engine",
        "ipo_engine.screening.regulatory",
        *_INFRA,
    ),
}


def _python_files(package: str) -> list[Path]:
    return sorted((APP_ROOT / package).rglob("*.py"))


def _imported_modules(path: Path) -> list[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    imported: list[str] = []

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.append(node.module)

    return imported


def _violates_boundary(import_name: str, prohibited_prefix: str) -> bool:
    return import_name == prohibited_prefix or import_name.startswith(f"{prohibited_prefix}.")


@pytest.mark.unit
@pytest.mark.parametrize("package,prohibited_imports", BOUNDARY_RULES.items())
def test_documented_import_boundaries(
    package: str,
    prohibited_imports: tuple[str, ...],
) -> None:
    violations: list[str] = []

    for path in _python_files(package):
        for import_name in _imported_modules(path):
            for prohibited in prohibited_imports:
                if _violates_boundary(import_name, prohibited):
                    rel_path = path.relative_to(APP_ROOT.parent)
                    violations.append(f"{rel_path}: imports {import_name}")

    assert violations == []
