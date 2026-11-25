"""docs/API.md is generated from the application; it must not drift."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent


def _tool() -> Any:
    spec = importlib.util.spec_from_file_location("api_doc", ROOT / "tools" / "api_doc.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules["api_doc"] = module
    spec.loader.exec_module(module)
    return module


def test_the_api_reference_is_current() -> None:
    fresh = _tool().render()
    on_disk = (ROOT / "docs" / "API.md").read_text()
    assert fresh == on_disk, "docs/API.md is out of date: run `uv run python tools/api_doc.py`"


def test_every_v1_route_is_in_the_reference() -> None:
    text = (ROOT / "docs" / "API.md").read_text()
    for path in (
        "/api/v1/cases",
        "/api/v1/webhooks",
        "/api/v1/org/export",
        "/api/v1/shared/{token}",
    ):
        assert f"`{path}`" in text
