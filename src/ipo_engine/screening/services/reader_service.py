"""The reader's brief for an uploaded document.

The screening pipeline reads the handful of figures the eligibility rules need. The reader
(`ipo_engine.parse`, `.analyze`, `.brief`) reads the offer document more broadly: issue size, annual
financials, red flags, related-party rows, figures the document's own tables disagree on. This
service runs the reader on a stored upload, in the background because a long filing takes minutes,
and caches the result by content hash and reader version, so the same file is read once.

State is deliberately simple: finished results live on disk, running and failed jobs in memory. After
a restart a job that was running is simply "not started" again.
"""

from __future__ import annotations

import json
import logging
import tempfile
import threading
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from ipo_engine.analyze import ANALYSIS_VERSION, analyze_document
from ipo_engine.brief import build_brief
from ipo_engine.ingest.manifest import DocType, ManifestEntry, Platform
from ipo_engine.parse.models import PARSER_VERSION
from ipo_engine.parse.pdf import default_workers, parse_pdf
from ipo_engine.screening.services.documents import DocumentService

logger = logging.getLogger("ipo_engine.screening.reader")

READER_VERSION = f"{PARSER_VERSION}.{ANALYSIS_VERSION}"


def read_pdf(content: bytes, *, sha256: str, name: str, workers: int = 1) -> dict[str, Any]:
    """Run the reader on PDF bytes and return its brief as plain JSON data."""
    with tempfile.TemporaryDirectory(prefix="ipo-reader-") as tmp:
        path = Path(tmp) / "document.pdf"
        path.write_bytes(content)
        doc = parse_pdf(path, doc_id=sha256[:16], sha256=sha256, workers=workers)
        report = analyze_document(doc, path, platform=Platform.MAINBOARD.value)
    entry = ManifestEntry(
        doc_id=sha256[:16],
        url="",
        issuer=name,
        doc_type=DocType.DRHP,
        platform=Platform.MAINBOARD,
        sha256=sha256,
        size_bytes=len(content),
        fetched_at=datetime.now(UTC),
        local_path="",
        content_type="application/pdf",
    )
    brief = asdict(build_brief(report, entry))
    for key in ("issuer", "doc_type", "platform", "filed", "url"):
        brief.pop(key)  # the case and the document record carry these; the reader guessed them
    brief["pages"] = doc.n_pages
    brief["sections"] = [s.model_dump() for s in report.sections]
    # Decimals become strings: amounts are rupees and must not pass through binary floats.
    return json.loads(json.dumps(brief, default=str))  # type: ignore[no-any-return]


class ReaderService:
    def __init__(
        self, documents: DocumentService, cache_dir: Path, *, inline: bool = False
    ) -> None:
        self._documents = documents
        self._cache_dir = cache_dir
        self._inline = inline
        self._executor = (
            None if inline else ThreadPoolExecutor(max_workers=1, thread_name_prefix="reader")
        )
        self._lock = threading.Lock()
        self._running: set[str] = set()
        self._failed: dict[str, str] = {}

    def shutdown(self) -> None:
        if self._executor is not None:
            self._executor.shutdown(wait=False, cancel_futures=True)

    def _cache_path(self, sha256: str) -> Path:
        return self._cache_dir / f"{sha256}.reader-{READER_VERSION}.json"

    def status(self, document_id: str) -> dict[str, Any]:
        sha = self._documents.get(document_id)["sha256"]
        out: dict[str, Any] = {
            "document_id": document_id,
            "reader_version": READER_VERSION,
            "status": "not_started",
            "error": None,
            "brief": None,
        }
        path = self._cache_path(sha)
        if path.exists():
            out["status"] = "ready"
            out["brief"] = json.loads(path.read_text(encoding="utf-8"))
            return out
        with self._lock:
            if sha in self._running:
                out["status"] = "running"
            elif sha in self._failed:
                out["status"] = "failed"
                out["error"] = self._failed[sha]
        return out

    def start(self, document_id: str) -> dict[str, Any]:
        """Start reading (no-op if it is running or done). Raises if the file is not retained."""
        doc = self._documents.get(document_id)
        sha = doc["sha256"]
        if self._cache_path(sha).exists():
            return self.status(document_id)
        content = self._documents.content(document_id)
        with self._lock:
            already = sha in self._running
            if not already:
                self._running.add(sha)
                self._failed.pop(sha, None)
        if already:
            return self.status(document_id)
        if self._executor is None:
            self._job(sha, content, doc["filename"])
        else:
            self._executor.submit(self._job, sha, content, doc["filename"])
        return self.status(document_id)

    def _job(self, sha: str, content: bytes, name: str) -> None:
        try:
            workers = 1 if self._inline else default_workers()
            brief = read_pdf(content, sha256=sha, name=name, workers=workers)
            self._cache_dir.mkdir(parents=True, exist_ok=True)
            tmp = self._cache_path(sha).with_suffix(".part")
            tmp.write_text(json.dumps(brief), encoding="utf-8")
            tmp.replace(self._cache_path(sha))
        except Exception as exc:  # job boundary: record the failure, keep the service alive
            logger.exception("reader failed for %s", sha[:12])
            with self._lock:
                self._failed[sha] = f"{type(exc).__name__}: {exc}"[:300]
        finally:
            with self._lock:
                self._running.discard(sha)
