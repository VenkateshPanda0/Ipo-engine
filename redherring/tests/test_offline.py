"""The software runs offline: no language model, and no network access outside `rh ingest`."""

import ast
from pathlib import Path

SRC = Path(__file__).resolve().parent.parent / "src" / "redherring"

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
        i for i in imported for b in banned if i == b or i.startswith(b + ".")
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
        if p != DOWNLOADER
    }
    assert {k: v for k, v in offenders.items() if v} == {}


def test_the_language_model_package_is_gone() -> None:
    assert not (SRC / "llm").exists()
    assert not list(SRC.rglob("*llm*"))
