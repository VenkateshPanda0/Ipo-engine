"""The software runs offline: no language model, and no network access outside `ipo ingest`."""

import ast
from pathlib import Path

SRC = Path(__file__).resolve().parent.parent / "src" / "ipo_engine"

NETWORK = {
    "urllib", "http", "socket", "ssl", "requests", "httpx", "aiohttp", "ftplib", "smtplib",
    "xmlrpc", "websocket", "websockets", "grpc",
}  # fmt: skip
MODELS = {
    "anthropic", "openai", "cohere", "mistralai", "google.generativeai", "google.genai",
    "langchain", "llama_index", "ollama", "transformers", "torch", "litellm", "vertexai",
    "boto3", "huggingface_hub",
}  # fmt: skip
DOWNLOADER = SRC / "ingest" / "fetch.py"
# The web app's optional network features (sign-in with Google, later webhooks, e-mail, storage)
# live in one package that nothing imports unless the feature is switched on; see
# tests/test_network_boundary.py. `urllib.parse` only splits and builds strings, so it is allowed
# everywhere; the rest of `urllib` (which can open connections) is not.
PURE = {"urllib.parse"}
NETWORK_PACKAGE = SRC / "screening" / "network"


def _imports(path: Path) -> set[str]:
    names: set[str] = set()
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Import):
            names.update(a.name for a in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            names.add(node.module)
    return names


def _matches(imported: set[str], banned: set[str]) -> set[str]:
    return {
        i for i in imported for b in banned if (i == b or i.startswith(b + ".")) and i not in PURE
    }  # a package and everything inside it


def test_no_module_imports_a_language_model_sdk() -> None:
    offenders = {
        str(p.relative_to(SRC)): sorted(_matches(_imports(p), MODELS)) for p in SRC.rglob("*.py")
    }
    assert {k: v for k, v in offenders.items() if v} == {}


def test_only_the_downloader_imports_a_network_library() -> None:
    offenders = {
        str(p.relative_to(SRC)): sorted(_matches(_imports(p), NETWORK))
        for p in SRC.rglob("*.py")
        if p != DOWNLOADER and NETWORK_PACKAGE not in p.parents
    }
    assert {k: v for k, v in offenders.items() if v} == {}


def test_the_language_model_package_is_gone() -> None:
    assert not (SRC / "llm").exists()
    assert not list(SRC.rglob("*llm*"))
