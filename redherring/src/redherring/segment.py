"""Section map: which PDF pages belong to which section of an offer document.

The table of contents names each section and its printed start page. A printed page number is not
a PDF page number, so each entry is checked: its title must be printed as a heading block on the
PDF page the entry points to, using the one offset (PDF page minus printed page) that most entries
agree on. An entry that does not check out is dropped, never guessed, and a page before the first
verified section, or in a document with no usable table of contents, has no section.
"""

from __future__ import annotations

import re
from bisect import bisect_right
from collections import Counter
from dataclasses import dataclass

from redherring.parse.models import ParsedDocument

TOC_SCAN_PAGES = 30
MIN_ENTRIES = 5  # fewer verified entries than this: no map rather than a doubtful one
_TOC_HEAD = re.compile(r"^\s*table\s+of\s+contents?\s*$", re.I | re.M)
_ENTRY = re.compile(r"^(?P<title>.+?)\s*\.{4,}\s*(?P<page>\d{1,4})\s*$")


@dataclass(frozen=True)
class Section:
    title: str
    start_page: int  # PDF page
    printed_page: int


def _norm(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", text.lower()).strip()


def _toc_entries(doc: ParsedDocument) -> tuple[list[tuple[str, int]], int]:
    """(title, printed page) pairs in order, and the last PDF page that held contents."""
    entries: list[tuple[str, int]] = []
    last = 0
    started = False
    for page in doc.pages[:TOC_SCAN_PAGES]:
        text = "\n".join(b.text for b in page.blocks)
        if not started and not _TOC_HEAD.search(text):
            continue
        found = 0
        pending = ""
        for line in text.splitlines():
            m = _ENTRY.match(line.strip())
            if m:
                title = f"{pending} {m['title']}".strip()
                entries.append((title, int(m["page"])))
                found += 1
                pending = ""
            elif line.strip() and not _TOC_HEAD.match(line):
                # a title that wraps onto the next line: keep the first part
                pending = line.strip() if line.strip().isupper() else ""
        if found:
            started = True
            last = page.pdf_page
        elif started:
            break
    return entries, last


def build_section_map(doc: ParsedDocument) -> list[Section]:
    entries, toc_end = _toc_entries(doc)
    if len(entries) < MIN_ENTRIES:
        return []
    heading_pages: dict[str, list[int]] = {}
    for page in doc.pages:
        if page.pdf_page <= toc_end:
            continue
        for b in page.blocks:
            first = _norm(b.text.splitlines()[0]) if b.text.strip() else ""
            if first:
                heading_pages.setdefault(first, []).append(page.pdf_page)
    offsets: Counter[int] = Counter()
    for title, printed in entries:
        for p in heading_pages.get(_norm(title), []):
            offsets[p - printed] += 1
    if not offsets:
        return []
    offset, votes = offsets.most_common(1)[0]
    out = [
        Section(title, printed + offset, printed)
        for title, printed in entries
        if printed + offset in heading_pages.get(_norm(title), [])
    ]
    out.sort(key=lambda s: s.start_page)
    return out if len(out) >= MIN_ENTRIES and votes >= MIN_ENTRIES else []


def section_of(sections: list[Section], pdf_page: int) -> Section | None:
    """The section a PDF page falls in: the last verified start at or before it."""
    i = bisect_right([s.start_page for s in sections], pdf_page) - 1
    return sections[i] if i >= 0 else None
