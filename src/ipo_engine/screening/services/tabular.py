# ruff: noqa: E501  (the OOXML namespace and content-type strings cannot be shortened)
"""
Spreadsheet output: CSV and a minimal XLSX writer (no dependency).

Anything a spreadsheet program could run as a formula is neutralised: a cell that starts with
``=``, ``+``, ``-``, ``@``, a tab or a carriage return gets a leading apostrophe, so a company name
typed as ``=HYPERLINK(...)`` arrives as text in the reader's Excel or Sheets.
"""

from __future__ import annotations

import csv
import io
import zipfile
from collections.abc import Sequence
from datetime import datetime
from typing import Any
from xml.sax.saxutils import escape

_DANGEROUS = ("=", "+", "-", "@", "\t", "\r")


def cell_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, datetime):
        value = value.isoformat(timespec="seconds")
    text = str(value)
    return "'" + text if text.startswith(_DANGEROUS) else text


def to_csv(header: Sequence[str], rows: Sequence[Sequence[Any]]) -> bytes:
    out = io.StringIO(newline="")
    writer = csv.writer(out, lineterminator="\r\n")
    writer.writerow(header)
    for row in rows:
        writer.writerow([cell_text(v) for v in row])
    return ("﻿" + out.getvalue()).encode("utf-8")  # BOM so Excel reads UTF-8 correctly


def _col(n: int) -> str:
    name = ""
    n += 1
    while n:
        n, rem = divmod(n - 1, 26)
        name = chr(65 + rem) + name
    return name


def _xml_safe(text: str) -> str:
    """Drop characters XML 1.0 cannot carry."""
    return "".join(ch for ch in text if ch in "\t\n\r" or ord(ch) >= 0x20)


def to_xlsx(sheet: str, header: Sequence[str], rows: Sequence[Sequence[Any]]) -> bytes:
    def cell(r: int, c: int, value: Any) -> str:
        text = escape(_xml_safe(cell_text(value)))
        return f'<c r="{_col(c)}{r}" t="inlineStr"><is><t xml:space="preserve">{text}</t></is></c>'

    body = []
    for r, row in enumerate([list(header), *map(list, rows)], start=1):
        body.append(f'<row r="{r}">' + "".join(cell(r, c, v) for c, v in enumerate(row)) + "</row>")
    sheet_xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
        f"<sheetData>{''.join(body)}</sheetData></worksheet>"
    )
    name = escape(_xml_safe(sheet))[:31] or "Sheet1"
    files = {
        "[Content_Types].xml": (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
            '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
            '<Default Extension="xml" ContentType="application/xml"/>'
            '<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>'
            '<Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>'
            "</Types>"
        ),
        "_rels/.rels": (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/>'
            "</Relationships>"
        ),
        "xl/workbook.xml": (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
            'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
            f'<sheets><sheet name="{name}" sheetId="1" r:id="rId1"/></sheets></workbook>'
        ),
        "xl/_rels/workbook.xml.rels": (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/>'
            "</Relationships>"
        ),
        "xl/worksheets/sheet1.xml": sheet_xml,
    }
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for path, content in files.items():
            z.writestr(path, content)
    return buf.getvalue()
