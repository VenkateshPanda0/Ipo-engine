"""Backups: a real round trip, and detection of a damaged or incomplete one."""

from __future__ import annotations

import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from tests.screening.fixtures.pdf_factory import standard_drhp

from ipo_engine.cli import main
from ipo_engine.screening.core.config import Settings, get_settings
from ipo_engine.screening.main import create_app
from ipo_engine.screening.services.backup import BackupError, backup, restore, verify

H = {"Authorization": "Bearer k"}


def _mk(**env: str) -> Settings:
    return Settings(**env)  # type: ignore[arg-type]


def _app(tmp: Path, name: str) -> tuple[TestClient, Settings]:
    s = _mk(
        DATA_DIR=str(tmp / name / "data"),
        DATABASE_URL=f"sqlite:///{tmp / name / 'app.db'}",
        API_KEYS="ann|admin|k",
    )
    client = TestClient(create_app(s, inline_processing=True))
    client.__enter__()
    return client, s


def _fill(client: TestClient) -> tuple[str, str]:
    case = client.post("/api/v1/cases", json={"company_name": "Backed Up Ltd"}, headers=H).json()
    doc = client.post(
        f"/api/v1/cases/{case['id']}/documents",
        files={"file": ("d.pdf", standard_drhp(), "application/pdf")},
        headers=H,
    ).json()
    client.post(f"/api/v1/cases/{case['id']}/screenings", headers=H)
    return case["id"], doc["id"]


def test_sqlite_backup_restores_into_a_fresh_install_with_data_and_files(tmp_path: Path) -> None:
    live, settings = _app(tmp_path, "live")
    case_id, doc_id = _fill(live)
    made = backup(settings.database_url, settings.document_dir, tmp_path / "out")
    manifest = verify(made)
    assert manifest["database"] == "sqlite" and any(
        k.startswith("documents/") for k in manifest["files"]
    )

    fresh, fresh_settings = _app(tmp_path, "fresh")  # an empty install, then restore over it
    fresh.__exit__(None, None, None)
    restore(made, fresh_settings.database_url, fresh_settings.document_dir, force=True)
    revived = TestClient(create_app(fresh_settings, inline_processing=True))
    with revived:
        got = revived.get(f"/api/v1/cases/{case_id}", headers=H)
        assert got.status_code == 200 and got.json()["company_name"] == "Backed Up Ltd"
        assert revived.get(f"/api/v1/documents/{doc_id}/content", headers=H).content.startswith(
            b"%PDF"
        )
        assert revived.get(f"/api/v1/cases/{case_id}/screenings", headers=H).json()
    live.__exit__(None, None, None)


def test_a_backup_can_be_taken_while_the_app_is_running(tmp_path: Path) -> None:
    live, settings = _app(tmp_path, "live")
    _fill(live)
    made = backup(settings.database_url, settings.document_dir, tmp_path / "out")
    assert live.get("/api/v1/cases", headers=H).status_code == 200  # still serving
    assert verify(made)
    live.__exit__(None, None, None)


def test_a_damaged_backup_is_caught(tmp_path: Path) -> None:
    live, settings = _app(tmp_path, "live")
    _fill(live)
    made = backup(settings.database_url, settings.document_dir, tmp_path / "out")
    pdf = next((made / "documents").glob("*.pdf"))
    pdf.write_bytes(pdf.read_bytes() + b"x")
    with pytest.raises(BackupError, match="damaged"):
        verify(made)
    pdf.unlink()
    with pytest.raises(BackupError, match="missing"):
        verify(made)
    (made / "manifest.json").unlink()
    with pytest.raises(BackupError, match="manifest"):
        verify(made)
    live.__exit__(None, None, None)


def test_restore_will_not_overwrite_without_force(tmp_path: Path) -> None:
    live, settings = _app(tmp_path, "live")
    made = backup(settings.database_url, settings.document_dir, tmp_path / "out")
    with pytest.raises(BackupError, match="already exists"):
        restore(made, settings.database_url, settings.document_dir)
    live.__exit__(None, None, None)


def test_the_command_line_round_trip(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    live, settings = _app(tmp_path, "live")
    case_id, _ = _fill(live)
    live.__exit__(None, None, None)
    monkeypatch.setenv("DATABASE_URL", settings.database_url)
    monkeypatch.setenv("DATA_DIR", str(settings.data_dir))
    get_settings.cache_clear()
    assert main(["backup", "create", "--out", str(tmp_path / "bk")]) == 0
    folder = next((tmp_path / "bk").iterdir())
    assert main(["backup", "verify", str(folder)]) == 0
    shutil.rmtree(settings.data_dir)
    Path(settings.database_url.removeprefix("sqlite:///")).unlink()
    assert main(["backup", "restore", str(folder)]) == 0
    capsys.readouterr()
    again = TestClient(
        create_app(
            _mk(
                **{
                    "DATA_DIR": str(settings.data_dir),
                    "DATABASE_URL": settings.database_url,
                    "API_KEYS": "ann|admin|k",
                }
            )
        )
    )
    with again:
        assert again.get(f"/api/v1/cases/{case_id}", headers=H).status_code == 200
    assert main(["backup", "verify", str(tmp_path / "nowhere")]) == 1
    get_settings.cache_clear()


def test_a_postgres_backup_round_trips(tmp_path: Path) -> None:
    import os

    pytest.importorskip("psycopg")
    admin = os.environ.get("IPO_TEST_PG_ADMIN_URL")
    if not admin or not shutil.which("pg_dump") or not shutil.which("pg_restore"):
        pytest.skip("needs IPO_TEST_PG_ADMIN_URL and the PostgreSQL client tools")
    import psycopg
    from tests.screening.conftest import _drop_postgres_databases, _new_postgres_database

    said = subprocess.run(["pg_dump", "--version"], capture_output=True, text=True).stdout
    found = re.search(r"\)\s+(\d+)", said)
    client_major = int(found.group(1)) if found else 0
    with psycopg.connect(admin) as probe:
        row = probe.execute("SHOW server_version_num").fetchone()
    server_major = int(row[0]) // 10000 if row else 0
    if client_major > server_major:
        pytest.skip(f"pg_dump {client_major} is newer than the server {server_major}")

    created: list[str] = []
    src = _new_postgres_database(created)
    dst = _new_postgres_database(created)
    try:
        s = _mk(DATA_DIR=str(tmp_path / "d"), DATABASE_URL=src, API_KEYS="ann|admin|k")
        with TestClient(create_app(s, inline_processing=True)) as c:
            case_id, _ = _fill(c)
        made = backup(src, s.document_dir, tmp_path / "out")
        assert json.loads((made / "manifest.json").read_text())["database"] == "postgresql"
        restore(made, dst, tmp_path / "d2" / "documents")
        s2 = _mk(DATA_DIR=str(tmp_path / "d2"), DATABASE_URL=dst, API_KEYS="ann|admin|k")
        with TestClient(create_app(s2, inline_processing=True)) as c2:
            assert c2.get(f"/api/v1/cases/{case_id}", headers=H).status_code == 200
        _ = psycopg
    finally:
        _drop_postgres_databases(created)
