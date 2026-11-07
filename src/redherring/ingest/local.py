"""Register a PDF that is already on this machine, with no download.

The entry goes into the same manifest as a downloaded filing, so parse, analyze, brief and report
work on it unchanged. Its `url` is a path relative to `data/reports/`, where the brief and the
report are written, so the "open p.N" links open the local copy.
"""

from __future__ import annotations

import re
import shutil
from datetime import UTC, date, datetime
from pathlib import Path

from redherring.ingest.fetch import looks_complete
from redherring.ingest.manifest import DocType, Manifest, ManifestEntry, Platform, sha256_file

_ID = re.compile(r"^[a-z0-9][a-z0-9_-]{2,79}$")


class AddError(Exception):
    pass


def add_local(
    data_dir: Path,
    manifest: Manifest,
    pdf: Path,
    *,
    doc_id: str,
    issuer: str,
    doc_type: DocType,
    platform: Platform | None,
    filing_date: date | None = None,
) -> ManifestEntry:
    if not _ID.match(doc_id):
        raise AddError("doc id must be 3 to 80 characters: lower-case letters, digits, _ or -")
    if not pdf.is_file():
        raise AddError(f"{pdf} is not a file")
    if not looks_complete(pdf):
        raise AddError(f"{pdf} does not look like a complete PDF (no %%EOF marker)")
    if manifest.get(doc_id) is not None:
        raise AddError(f"doc id {doc_id!r} is already in the manifest; choose another")
    raw_dir = data_dir / "raw"
    raw_dir.mkdir(parents=True, exist_ok=True)
    final = raw_dir / f"{doc_id}.pdf"
    shutil.copyfile(pdf, final)
    entry = ManifestEntry(
        doc_id=doc_id,
        url=f"../raw/{final.name}",
        issuer=issuer,
        doc_type=doc_type,
        platform=platform,
        filing_date=filing_date,
        notes=f"added from a local file ({pdf.name})",
        sha256=sha256_file(final),
        size_bytes=final.stat().st_size,
        fetched_at=datetime.now(UTC),
        local_path=str(final.relative_to(data_dir)),
        content_type="application/pdf",
    )
    manifest.add(entry)
    return entry
