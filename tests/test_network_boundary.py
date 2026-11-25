"""
The network stays in one place, and stays off unless asked for.

The reader and the analysis are offline (tests/test_offline.py). The web app may, when an operator
turns a feature on, talk to an identity provider (and later send webhooks, e-mail or use object
storage). That code is confined to ``screening/network/``; this file checks that nothing else
reaches into it, and that a default start never loads it.
"""

from __future__ import annotations

import ast
import subprocess
import sys
from pathlib import Path

import pytest

from ipo_engine.screening.network.http import HttpError, UrllibHttp, require_https

SRC = Path(__file__).resolve().parent.parent / "src" / "ipo_engine"
PACKAGE = "ipo_engine.screening.network"
# Modules that may import the network package, and only inside a function (lazily).
ALLOWED_IMPORTERS = {
    "screening/api/dependencies.py",
    "screening/services/mailer.py",
    "screening/services/signin.py",
    "screening/services/webhooks.py",
}


def _importers() -> dict[str, list[tuple[int, bool]]]:
    """module path -> [(line, at_module_level)] for every import of the network package."""
    found: dict[str, list[tuple[int, bool]]] = {}
    for path in SRC.rglob("*.py"):
        rel = str(path.relative_to(SRC))
        if rel.startswith("screening/network/"):
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"))
        top_level = {id(n) for n in tree.body}
        for node in ast.walk(tree):
            names: list[str] = []
            if isinstance(node, ast.Import):
                names = [a.name for a in node.names]
            elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
                names = [node.module]
            if any(n == PACKAGE or n.startswith(PACKAGE + ".") for n in names):
                found.setdefault(rel, []).append(
                    (getattr(node, "lineno", 0), id(node) in top_level)
                )
    return found


def test_only_known_modules_import_the_network_package_and_only_lazily() -> None:
    found = _importers()
    assert set(found) <= ALLOWED_IMPORTERS, set(found) - ALLOWED_IMPORTERS
    eager = {k: v for k, v in found.items() if any(top for _, top in v)}
    assert eager == {}, f"imported at module level (loads the network code at start): {eager}"


def test_a_default_start_never_loads_the_network_package() -> None:
    code = (
        "import sys, tempfile, pathlib\n"
        "from ipo_engine.screening.core.config import Settings\n"
        "from ipo_engine.screening.main import create_app\n"
        "d = pathlib.Path(tempfile.mkdtemp())\n"
        "create_app(Settings(DATA_DIR=str(d / 'd'), DATABASE_URL=f'sqlite:///{d}/a.db'))\n"
        "create_app(Settings(DATA_DIR=str(d / 'e'), DATABASE_URL=f'sqlite:///{d}/b.db',\n"
        "                    ACCOUNTS_ENABLED='true'))  # accounts alone still need no network\n"
        "loaded = sorted(m for m in sys.modules if m.startswith('ipo_engine.screening.network'))\n"
        "print('LOADED', loaded)\n"
    )
    out = subprocess.run(
        [sys.executable, "-I", "-c", code], capture_output=True, text=True, check=True, timeout=120
    )
    assert "LOADED []" in out.stdout, out.stdout + out.stderr


@pytest.mark.parametrize(
    "url", ["http://example.com/x", "ftp://example.com/x", "file:///etc/passwd", "https:///nohost"]
)
def test_the_real_client_refuses_anything_but_https(url: str) -> None:
    with pytest.raises(HttpError):
        require_https(url)
    with pytest.raises(HttpError):
        UrllibHttp().get_json(url)


def test_loopback_http_is_allowed_for_a_local_identity_provider() -> None:
    assert require_https("http://localhost:9000/x") and require_https("http://127.0.0.1/x")
