"""The documentation stays navigable: links resolve, nothing is orphaned, named files exist."""

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DOCS = ROOT / "docs"
SKIP_DIRS = {"node_modules", ".venv", ".git", ".next", ".pytest_cache", "data"}

# Historical records keep the paths of their day (the decision log, held-out run notes, the old
# changelogs, the audit); they say so, and are not rewritten.
HISTORICAL = (
    "audit_reports/05_AGENT_REPORTS/",  # raw reviewer reports: evidence, not current docs
    "docs/decisions.md",
    "docs/history/",
    "docs/screening/CHANGELOG.md",
    "docs/screening/audit/",
)
# Named in prose but generated or placeholders, not files in the repository.
GENERATED = ("data/", "docs/history/heldout-run-N.md", "labels/DOC.json")
ROOTS = (
    "src/",
    "tests/",
    "tools/",
    "docs/",
    "labels/",
    "frontend/",
    "site/",
    ".github/",
    "benchmark/",
    "sample_data/",
    "Makefile",
    "Dockerfile",
    "compose.yaml",
    "pyproject.toml",
)


def _markdown_files() -> list[Path]:
    return sorted(p for p in ROOT.rglob("*.md") if not SKIP_DIRS & set(p.relative_to(ROOT).parts))


def _strip_code(text: str) -> str:
    return re.sub(r"```.*?```", "", text, flags=re.S)


def _links(path: Path) -> list[str]:
    text = _strip_code(path.read_text(encoding="utf-8"))
    return [
        m.group(1) or m.group(2)
        for m in re.finditer(
            r"(?<!!)\[[^\]]*\]\(([^)\s]+)[^)]*\)|!\[[^\]]*\]\(([^)\s]+)[^)]*\)", text
        )
    ]


def _local(target: str) -> str | None:
    if re.match(r"^(https?:|mailto:|#)", target):
        return None
    return target.split("#")[0] or None


def test_every_relative_link_and_image_resolves() -> None:
    broken = []
    for md in _markdown_files():
        for target in _links(md):
            rel = _local(target)
            if rel and not (md.parent / rel).resolve().exists():
                broken.append(f"{md.relative_to(ROOT)}: {target}")
    assert not broken, "broken links:\n" + "\n".join(broken)


def test_every_document_under_docs_is_linked_from_the_index() -> None:
    index = DOCS / "README.md"
    linked = {(index.parent / rel).resolve() for t in _links(index) if (rel := _local(t))}
    orphans = [
        str(p.relative_to(ROOT))
        for p in DOCS.rglob("*.md")
        if p != index and p.resolve() not in linked
    ]
    assert not orphans, "not linked from docs/README.md:\n" + "\n".join(orphans)


def test_backticked_repository_paths_in_current_docs_exist() -> None:
    missing = []
    for md in _markdown_files():
        rel_md = str(md.relative_to(ROOT))
        if rel_md.startswith(HISTORICAL):
            continue
        for m in re.finditer(r"`([^`\n]+)`", _strip_code(md.read_text(encoding="utf-8"))):
            token = m.group(1).strip().rstrip(".,:;")
            if " " in token or not token.startswith(ROOTS) or token.startswith(GENERATED):
                continue
            if any(c in token for c in "*<>{}$|"):
                continue
            token = token.split("#")[0].split("::")[0]
            if not (ROOT / token).exists() and not (md.parent / token).exists():
                missing.append(f"{rel_md}: {token}")
    assert not missing, "named files that do not exist:\n" + "\n".join(missing)
