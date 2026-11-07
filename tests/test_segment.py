from ipo_engine.parse.models import BBox, Block, ParsedDocument, ParsedPage
from ipo_engine.segment import build_section_map, section_of

TITLES = ["DEFINITIONS", "RISK FACTORS", "THE OFFER", "OBJECTS OF THE OFFER", "CAPITAL STRUCTURE",
          "OUR BUSINESS"]  # fmt: skip


def _page(n: int, *texts: str) -> ParsedPage:
    blocks = [Block(pdf_page=n, bbox=BBox(x0=0, top=0, x1=1, bottom=1), text=t) for t in texts]
    return ParsedPage(
        pdf_page=n, width=1, height=1, alnum_chars=10, n_images=0, image_coverage=0,
        needs_ocr=False, blocks=blocks,
    )  # fmt: skip


def _doc(offset: int = 3, fake: str | None = None) -> ParsedDocument:
    toc = "TABLE OF CONTENTS\n" + "\n".join(
        f"{t} ........ {1 + 10 * i}" for i, t in enumerate(TITLES)
    )
    pages = [_page(1, toc)] + [_page(p, f"filler {p}") for p in range(2, 80)]
    for i, t in enumerate(TITLES):
        pages[(1 + 10 * i) + offset - 1] = _page((1 + 10 * i) + offset, fake or t, "body")
    return ParsedDocument(doc_id="d", n_pages=len(pages), pages=pages)


def test_entries_are_mapped_through_the_verified_offset() -> None:
    sections = build_section_map(_doc())
    assert [(s.title, s.start_page) for s in sections][1] == ("RISK FACTORS", 14)
    s = section_of(sections, 25)
    assert s is not None and s.title == "THE OFFER"
    assert section_of(sections, 3) is None  # before the first verified section


def test_an_entry_whose_heading_is_not_on_its_page_is_dropped() -> None:
    doc = _doc()
    doc.pages[13] = _page(14, "something else entirely")  # the Risk Factors heading is gone
    titles = [s.title for s in build_section_map(doc)]
    assert "RISK FACTORS" not in titles and "THE OFFER" in titles


def test_no_usable_contents_gives_no_map() -> None:
    doc = ParsedDocument(doc_id="d", n_pages=1, pages=[_page(1, "just text")])
    assert build_section_map(doc) == []
