"""Write docs/API.md from the application's own OpenAPI schema.

uv run python tools/api_doc.py          # rewrite docs/API.md
uv run python tools/api_doc.py --check  # exit 1 if it is out of date (a test does this too)
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "docs" / "API.md"
ORDER = [
    ("system", "System and health"),
    ("v1", "Cases, documents, reviews, screenings, reports"),
    ("accounts", "Organisation, members, tokens, settings, webhooks"),
    ("auth", "Sign-in, sessions, invitations"),
    ("share", "Public share links"),
]


def render() -> str:
    from fastapi.testclient import TestClient

    from ipo_engine.screening.core.config import Settings
    from ipo_engine.screening.main import create_app

    tmp = Path(tempfile.mkdtemp())
    app = create_app(
        Settings(  # type: ignore[arg-type]
            DATA_DIR=str(tmp / "d"),
            DATABASE_URL=f"sqlite:///{tmp / 'doc.db'}",
            ACCOUNTS_ENABLED="true",
            WEBHOOK_SIGNING_KEY="doc",
        )
    )
    with TestClient(app) as client:
        schema = client.get("/openapi.json").json()
    groups: dict[str, list[tuple[str, str, str]]] = {}
    for path, ops in sorted(schema["paths"].items()):
        if not path.startswith("/api/v1"):
            continue
        for method, op in sorted(ops.items()):
            if method not in {"get", "post", "put", "patch", "delete"}:
                continue
            tag = (op.get("tags") or ["v1"])[0]
            text = (op.get("description") or op.get("summary") or "").strip().splitlines()
            first = text[0].strip() if text else ""
            groups.setdefault(tag, []).append((method.upper(), path, first.replace("|", "\\|")))
    out = [
        "# API reference",
        "",
        "Generated from the running application by `tools/api_doc.py`; a test fails if this",
        "file is out of date. The interactive version is at `/docs` when `APP_ENV` is not",
        "`production`.",
        "",
        "**Authentication.** Send `Authorization: Bearer <token>` (a personal token from",
        "`POST /api/v1/tokens`, or a key from `API_KEYS`), or use the browser session cookie",
        "with the `X-CSRF-Token` header on every change. Roles, lowest to highest: viewer,",
        "analyst, reviewer, admin. An id that belongs to another organisation answers 404, the",
        "same as an id that does not exist. Errors are",
        '`{"error": {"code", "message", "request_id"}}`.',
        "",
        f"**Version.** API {schema['info']['version']}. Breaking changes bump the major version;",
        "the unversioned routes are deprecated (see `docs/VERSIONING.md`).",
        "",
    ]
    for tag, title in ORDER:
        rows = groups.pop(tag, [])
        if tag == "v1":
            rows += groups.pop("v1", [])
        if not rows:
            continue
        out += [f"## {title}", "", "| Method | Path | What it does |", "|---|---|---|"]
        out += [f"| {m} | `{p}` | {d} |" for m, p, d in rows]
        out.append("")
    for tag, rows in sorted(groups.items()):
        out += [f"## {tag}", "", "| Method | Path | What it does |", "|---|---|---|"]
        out += [f"| {m} | `{p}` | {d} |" for m, p, d in rows]
        out.append("")
    return "\n".join(out).rstrip() + "\n"


def main() -> int:
    text = render()
    if "--check" in sys.argv:
        return 0 if OUT.exists() and OUT.read_text() == text else 1
    OUT.write_text(text)
    print(f"wrote {OUT} ({text.count(chr(10))} lines)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
