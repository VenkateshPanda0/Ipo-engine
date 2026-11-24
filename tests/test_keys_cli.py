import hashlib
import io

import pytest

from ipo_engine.cli import main
from ipo_engine.screening.core.config import Settings
from ipo_engine.screening.core.security import authenticate


def test_keys_hash_prints_the_sha256_form_the_api_accepts(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr("sys.stdin", io.StringIO("my-key\n"))
    assert main(["keys", "hash"]) == 0
    out = capsys.readouterr().out.strip()
    assert out == "sha256=" + hashlib.sha256(b"my-key").hexdigest()
    settings = Settings(API_KEYS=f"ann|reviewer|{out}")
    assert authenticate(settings, "Bearer my-key").user_id == "ann"


def test_keys_hash_rejects_an_empty_key(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr("sys.stdin", io.StringIO("\n"))
    assert main(["keys", "hash"]) == 1
    assert "empty" in capsys.readouterr().err.lower()
