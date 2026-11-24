"""The release workflow takes a version's notes from CHANGELOG.md; this keeps that parseable."""

import importlib.util
import re
import subprocess
import sys
from pathlib import Path
from types import ModuleType

import pytest

ROOT = Path(__file__).resolve().parent.parent


def _load() -> ModuleType:
    spec = importlib.util.spec_from_file_location("release_notes", ROOT / "tools/release_notes.py")
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


release_notes = _load()

SAMPLE = """# Changelog

## [Unreleased]

### Added
- New thing.

## [0.4.0] - 2026-12-01

### Fixed
- A bug.

## [0.3.0] - 2026-11-13

### Added
- Older thing.
"""


def test_extracts_one_version_section_without_its_heading() -> None:
    body = release_notes.extract(SAMPLE, "0.4.0")
    assert body.startswith("### Fixed") and "- A bug." in body
    assert "Older thing" not in body and "New thing" not in body


def test_a_version_with_a_v_prefix_is_accepted() -> None:
    assert "A bug" in release_notes.extract(SAMPLE, "v0.4.0")


def test_a_missing_or_empty_section_is_an_error_not_an_empty_release() -> None:
    with pytest.raises(release_notes.NoNotes):
        release_notes.extract(SAMPLE, "9.9.9")
    with pytest.raises(release_notes.NoNotes):
        release_notes.extract("## [1.0.0] - 2026-01-01\n\n## [0.9.0] - 2025-12-01\n- x\n", "1.0.0")


def test_the_real_changelog_is_keep_a_changelog() -> None:
    text = (ROOT / "CHANGELOG.md").read_text()
    heads = re.findall(r"^## (.+)$", text, re.M)
    assert heads[0] == "[Unreleased]"
    assert heads[-1] == "Earlier history: screening app"
    for h in heads[1:-1]:
        assert re.fullmatch(r"\[\d+\.\d+\.\d+\] - \d{4}-\d{2}(-\d{2})?", h), h
    pkg = re.search(r'^version = "(.+)"', (ROOT / "pyproject.toml").read_text(), re.M)
    assert pkg and release_notes.extract(text, pkg.group(1))  # the shipped version has notes


def test_the_script_prints_the_notes() -> None:
    out = subprocess.run(
        [sys.executable, str(ROOT / "tools/release_notes.py"), "0.3.0"],
        capture_output=True,
        text=True,
    )
    assert out.returncode == 0 and "Demo site" in out.stdout
