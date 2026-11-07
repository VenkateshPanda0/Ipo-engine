"""
src/ipo_engine/screening/reports/report_generator.py

ReportGenerator dispatches a completed IPOReport to JSON, text, or HTML
formatters.

This module MUST NOT import from:
  - ipo_engine.screening.rules
  - ipo_engine.screening.intelligence
  - ipo_engine.screening.api
  - ipo_engine.screening.services
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Protocol

from ipo_engine.screening.models.ipo_report import IPOReport
from ipo_engine.screening.reports.formatters.html_formatter import HTMLReportFormatter
from ipo_engine.screening.reports.formatters.json_formatter import JSONReportFormatter
from ipo_engine.screening.reports.formatters.text_formatter import TextReportFormatter


class ReportFormatter(Protocol):
    """Formatter interface used by ReportGenerator."""

    def format(self, report: IPOReport) -> str:
        """Render an IPOReport."""


class ReportGenerator:
    """Dispatch IPOReport rendering to a requested output format."""

    def __init__(self) -> None:
        self._formatters: Mapping[str, ReportFormatter] = {
            "json": JSONReportFormatter(),
            "text": TextReportFormatter(),
            "html": HTMLReportFormatter(),
        }

    def generate(self, report: IPOReport, format: str = "json") -> str:
        """Render a report in the requested format.

        Args:
            report: Completed IPOReport.
            format: One of "json", "text", or "html".

        Returns:
            Rendered report string.

        Raises:
            ValueError: If the format is unsupported.
        """
        normalized = format.lower()
        formatter = self._formatters.get(normalized)
        if formatter is None:
            available = ", ".join(self.get_available_formats())
            raise ValueError(f"Unsupported report format '{format}'. Available: {available}.")
        return formatter.format(report)

    def get_available_formats(self) -> list[str]:
        """Return supported report format names."""
        return sorted(self._formatters)
