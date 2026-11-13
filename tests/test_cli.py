from pathlib import Path

import pytest

from ipo_engine.cli import main
from ipo_engine.ingest.manifest import DocType, Manifest, ManifestEntry, Platform, sha256_file
from tests.pdfgen import PageSpec, build_pdf


def test_parse_command_end_to_end(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    from datetime import UTC, datetime

    raw = tmp_path / "raw"
    raw.mkdir()
    pdf = raw / "demo.pdf"
    pdf.write_bytes(build_pdf([PageSpec().text(72, 72, "Objects of the Issue")]))
    Manifest(tmp_path / "manifest.jsonl").add(
        ManifestEntry(
            doc_id="demo",
            url="https://example.invalid/demo.pdf",
            issuer="Demo Ltd",
            doc_type=DocType.PROSPECTUS,
            platform=Platform.SME,
            sha256=sha256_file(pdf),
            size_bytes=pdf.stat().st_size,
            fetched_at=datetime.now(UTC),
            local_path="raw/demo.pdf",
            content_type="application/pdf",
        )
    )
    assert main(["--data-dir", str(tmp_path), "parse"]) == 0
    assert "| demo |" in capsys.readouterr().out
    assert "[PDF_PAGE_1]" in (tmp_path / "parsed" / "demo.tagged.txt").read_text()
    assert (tmp_path / "parsed" / "demo.json").exists()


def _register(tmp_path: Path, doc_id: str, content: bytes) -> None:
    from datetime import UTC, datetime

    raw = tmp_path / "raw"
    raw.mkdir(exist_ok=True)
    pdf = raw / f"{doc_id}.pdf"
    pdf.write_bytes(content)
    Manifest(tmp_path / "manifest.jsonl").add(
        ManifestEntry(
            doc_id=doc_id,
            url=f"https://example.invalid/{doc_id}.pdf",
            issuer="Demo Ltd",
            doc_type=DocType.PROSPECTUS,
            platform=Platform.SME,
            sha256=sha256_file(pdf),
            size_bytes=pdf.stat().st_size,
            fetched_at=datetime.now(UTC),
            local_path=f"raw/{doc_id}.pdf",
            content_type="application/pdf",
        )
    )


def test_parse_continues_past_a_corrupt_pdf(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _register(tmp_path, "bad", b"%PDF-1.4\nthis is not a real pdf\n")
    _register(tmp_path, "good", build_pdf([PageSpec().text(72, 72, "Objects of the Issue")]))
    assert main(["--data-dir", str(tmp_path), "parse"]) == 1  # non-zero: one failure
    captured = capsys.readouterr()
    assert "FAIL  bad" in captured.err
    assert "| good |" in captured.out
    assert (tmp_path / "parsed" / "good.json").exists()
    assert not (tmp_path / "parsed" / "bad.json").exists()


def test_parse_reuses_output_when_hash_unchanged(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _register(tmp_path, "good", build_pdf([PageSpec().text(72, 72, "Objects of the Issue")]))
    assert main(["--data-dir", str(tmp_path), "parse"]) == 0
    capsys.readouterr()
    assert main(["--data-dir", str(tmp_path), "parse"]) == 0
    assert "cached good" in capsys.readouterr().err
    assert main(["--data-dir", str(tmp_path), "parse", "--force"]) == 0
    assert "parsed good" in capsys.readouterr().err


def test_parse_ignores_output_from_older_parser_version(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    import json

    _register(tmp_path, "good", build_pdf([PageSpec().text(72, 72, "Objects of the Issue")]))
    assert main(["--data-dir", str(tmp_path), "parse"]) == 0
    out = tmp_path / "parsed" / "good.json"
    data = json.loads(out.read_text())
    data["parser_version"] = 0  # as written by a pre-versioning parser
    out.write_text(json.dumps(data))
    capsys.readouterr()
    assert main(["--data-dir", str(tmp_path), "parse"]) == 0
    assert "parsed good" in capsys.readouterr().err  # re-parsed, not "cached"


def test_parse_skips_regulations_unless_named(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _register(tmp_path, "filing", build_pdf([PageSpec().text(72, 72, "Objects of the Issue")]))
    _register(tmp_path, "icdr", build_pdf([PageSpec().text(72, 72, "Regulation 7")]))
    m = Manifest(tmp_path / "manifest.jsonl")
    m.add(m.get("icdr").model_copy(update={"doc_type": DocType.REGULATION}))  # type: ignore[union-attr]
    assert main(["--data-dir", str(tmp_path), "parse"]) == 0
    out = capsys.readouterr().out
    assert "| filing |" in out
    assert "| icdr |" not in out
    assert main(["--data-dir", str(tmp_path), "parse", "--doc-id", "icdr"]) == 0
    assert "| icdr |" in capsys.readouterr().out


def test_serve_is_a_subcommand_bound_to_this_machine_by_default() -> None:
    from ipo_engine.cli import build_parser

    args = build_parser().parse_args(["serve"])
    assert (args.host, args.port) == ("127.0.0.1", 8000)


def test_add_registers_a_local_pdf_that_parse_then_reads(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    src = tmp_path / "mine.pdf"
    src.write_bytes(build_pdf([PageSpec().text(72, 72, "Objects of the Issue")]))
    data = tmp_path / "data"
    args = ["--data-dir", str(data)]
    rc = main([*args, "add", str(src), "--doc-id", "acme_drhp_2026", "--issuer", "Acme Ltd"])
    assert rc == 0
    entry = Manifest(data / "manifest.jsonl").get("acme_drhp_2026")
    assert entry is not None and entry.url == "../raw/acme_drhp_2026.pdf"
    assert (data / "raw" / "acme_drhp_2026.pdf").read_bytes() == src.read_bytes()
    assert main([*args, "parse", "--doc-id", "acme_drhp_2026"]) == 0
    assert (data / "parsed" / "acme_drhp_2026.json").exists()


def test_add_refuses_a_duplicate_id_and_a_truncated_file(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    good = tmp_path / "good.pdf"
    good.write_bytes(build_pdf([PageSpec().text(72, 72, "x")]))
    bad = tmp_path / "bad.pdf"
    bad.write_bytes(b"%PDF-1.4 truncated")
    args = ["--data-dir", str(tmp_path / "data")]
    base = ["add", "--issuer", "Acme Ltd", "--doc-id"]
    assert main([*args, *base, "acme_one", str(good)]) == 0
    assert main([*args, *base, "acme_one", str(good)]) == 1  # already registered
    assert main([*args, *base, "acme_two", str(bad)]) == 1  # no %%EOF
    err = capsys.readouterr().err
    assert "already in the manifest" in err and "complete PDF" in err


def test_run_does_everything_for_one_pdf(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    src = tmp_path / "Acme DRHP (final).pdf"
    src.write_bytes(build_pdf([PageSpec().text(72, 72, "Objects of the Issue")]))
    data = tmp_path / "data"
    assert main(["--data-dir", str(data), "run", str(src), "--issuer", "Acme Ltd"]) == 0
    reports = data / "reports"
    assert (reports / "brief_acme_drhp_final.html").exists()
    assert (reports / "acme_drhp_final.html").exists()
    home = (reports / "index.html").read_text()
    assert "Acme Ltd" in home and "brief_acme_drhp_final.html" in home
    assert main(["--data-dir", str(data), "run", str(src)]) == 0  # running again is harmless
    other = tmp_path / "acme_drhp_final.pdf"
    other.write_bytes(build_pdf([PageSpec().text(72, 72, "A different document")]))
    assert main(["--data-dir", str(data), "run", str(other)]) == 1  # same id, different file
    assert "already used by a different file" in capsys.readouterr().err
