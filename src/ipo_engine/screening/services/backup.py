"""
Backup and restore of the database and the stored documents.

A backup is a directory: the database (a consistent SQLite copy made with SQLite's online backup,
so the app can keep running, or a ``pg_dump`` custom-format file), every stored PDF, and a manifest
with the SHA-256 of each file. ``verify`` re-reads all of it; ``restore`` refuses to write over an
existing database unless told to. Restoring into a newer version of the software runs the
migrations on first start.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import sqlite3
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlsplit

from ipo_engine import __version__
from ipo_engine.screening.db.base import _sqlite_path, is_postgres, normalise_url

MANIFEST = "manifest.json"
FORMAT = 1


class BackupError(RuntimeError):
    """A backup or restore could not be completed; the message says why."""


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _pg_env(url: str) -> tuple[list[str], dict[str, str]]:
    """pg_dump/pg_restore arguments and environment for a URL (the password stays out of argv)."""
    parts = urlsplit(normalise_url(url).replace("postgresql+psycopg", "postgresql", 1))
    env = dict(os.environ)
    if parts.password:
        env["PGPASSWORD"] = unquote(parts.password)
    args = ["-h", parts.hostname or "localhost", "-p", str(parts.port or 5432)]
    if parts.username:
        args += ["-U", unquote(parts.username)]
    return args, {**env, "PGDATABASE": parts.path.lstrip("/")}


def _tool(name: str) -> str:
    found = shutil.which(name)
    if found is None:
        raise BackupError(f"{name} is not installed; install the PostgreSQL client tools.")
    return found


def backup(database_url: str, documents_dir: Path, out_dir: Path) -> Path:
    """Write a backup into a new timestamped folder under ``out_dir``; returns that folder."""
    stamp = datetime.now(tz=UTC).strftime("%Y%m%dT%H%M%SZ")
    dest = out_dir / f"backup-{stamp}"
    dest.mkdir(parents=True, exist_ok=False)
    files: dict[str, str] = {}
    if is_postgres(database_url):
        dump = dest / "database.pgdump"
        args, env = _pg_env(database_url)
        subprocess.run(
            [_tool("pg_dump"), *args, "-Fc", "--no-owner", "-f", str(dump)],
            env=env,
            check=True,
            capture_output=True,
        )
        kind = "postgresql"
    else:
        path = _sqlite_path(database_url)
        if path is None or not path.exists():
            raise BackupError("The SQLite database file does not exist.")
        dump = dest / "database.sqlite3"
        src = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
        try:
            dst = sqlite3.connect(dump)
            try:
                src.backup(dst)  # consistent even while the app is writing
            finally:
                dst.close()
        finally:
            src.close()
        kind = "sqlite"
    files[dump.name] = _sha256(dump)
    doc_out = dest / "documents"
    doc_out.mkdir()
    if documents_dir.exists():
        for pdf in sorted(documents_dir.glob("*.pdf")):
            shutil.copy2(pdf, doc_out / pdf.name)
            files[f"documents/{pdf.name}"] = _sha256(doc_out / pdf.name)
    manifest = {
        "format": FORMAT,
        "software_version": __version__,
        "created_at": datetime.now(tz=UTC).isoformat(),
        "database": kind,
        "files": files,
    }
    (dest / MANIFEST).write_text(json.dumps(manifest, indent=1))
    verify(dest)
    return dest


def verify(folder: Path) -> dict[str, Any]:
    """Check every file against the manifest and the database for integrity; raises on any fault."""
    try:
        manifest = json.loads((folder / MANIFEST).read_text())
    except (OSError, ValueError) as exc:
        raise BackupError("This folder has no readable manifest.json.") from exc
    for name, digest in manifest["files"].items():
        path = folder / name
        if not path.exists():
            raise BackupError(f"missing from the backup: {name}")
        if _sha256(path) != digest:
            raise BackupError(f"damaged (checksum differs): {name}")
    if manifest["database"] == "sqlite":
        conn = sqlite3.connect(folder / "database.sqlite3")
        try:
            result = conn.execute("PRAGMA integrity_check").fetchone()[0]
        finally:
            conn.close()
        if result != "ok":
            raise BackupError(f"the database copy fails its integrity check: {result}")
    return manifest  # type: ignore[no-any-return]


def restore(folder: Path, database_url: str, documents_dir: Path, *, force: bool = False) -> None:
    manifest = verify(folder)
    documents_dir.mkdir(parents=True, exist_ok=True)
    if is_postgres(database_url):
        if manifest["database"] != "postgresql":
            raise BackupError("This backup is not a PostgreSQL backup.")
        args, env = _pg_env(database_url)
        cmd = [_tool("pg_restore"), *args, "--no-owner", "-d", env["PGDATABASE"]]
        if force:
            cmd += ["--clean", "--if-exists"]
        proc = subprocess.run(
            [*cmd, str(folder / "database.pgdump")], env=env, capture_output=True, text=True
        )
        if proc.returncode != 0:
            raise BackupError(f"pg_restore failed: {proc.stderr.strip()[:500]}")
    else:
        if manifest["database"] != "sqlite":
            raise BackupError("This backup is not a SQLite backup.")
        target = _sqlite_path(database_url)
        if target is None:
            raise BackupError("Cannot restore into this database URL.")
        if target.exists() and not force:
            raise BackupError(f"{target} already exists; use --force to replace it.")
        target.parent.mkdir(parents=True, exist_ok=True)
        for suffix in ("", "-wal", "-shm"):
            Path(str(target) + suffix).unlink(missing_ok=True)
        shutil.copy2(folder / "database.sqlite3", target)
    for pdf in (folder / "documents").glob("*.pdf"):
        shutil.copy2(pdf, documents_dir / pdf.name)
