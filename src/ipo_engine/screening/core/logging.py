"""Structured JSON logging.

Log records never include document contents or extracted financial values by
default; callers pass identifiers (request, case, document IDs) via ``extra``.
LOG_FORMAT=json (the default) writes one JSON object per line; LOG_FORMAT=text a readable line.
"""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime

_RESERVED = set(vars(logging.makeLogRecord({})).keys()) | {"message", "asctime"}


class JsonFormatter(logging.Formatter):
    """Format log records as single-line JSON objects."""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, object] = {
            "ts": datetime.fromtimestamp(record.created, tz=UTC).isoformat(timespec="milliseconds"),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        for key, value in vars(record).items():
            if key not in _RESERVED and not key.startswith("_"):
                payload[key] = value
        if record.exc_info:
            payload["exc_type"] = record.exc_info[0].__name__ if record.exc_info[0] else None
            payload["traceback"] = self.formatException(record.exc_info)
        return json.dumps(payload, default=str)


class TextFormatter(logging.Formatter):
    """One readable line: ``time LEVEL logger message key=value ...`` (same fields as the JSON
    form)."""

    def format(self, record: logging.LogRecord) -> str:
        ts = datetime.fromtimestamp(record.created, tz=UTC).isoformat(timespec="milliseconds")
        parts = [ts, f"{record.levelname:<7}", record.name, record.getMessage()]
        for key, value in vars(record).items():
            if key not in _RESERVED and not key.startswith("_"):
                parts.append(f"{key}={value}")
        line = " ".join(parts)
        if record.exc_info:
            line += " | " + self.formatException(record.exc_info).replace("\n", " | ")
        return line


def make_formatter(name: str) -> logging.Formatter:
    """The formatter for LOG_FORMAT (``json`` or ``text``)."""
    if name == "json":
        return JsonFormatter()
    if name == "text":
        return TextFormatter()
    raise ValueError(f"LOG_FORMAT must be 'json' or 'text', not {name!r}")


def configure_logging(level: str = "INFO", fmt: str = "json") -> None:
    """Configure root logging with the chosen formatter (idempotent; the format can be changed)."""
    root = logging.getLogger()
    root.setLevel(getattr(logging, level.upper(), logging.INFO))
    formatter = make_formatter(fmt)
    managed = [h for h in root.handlers if isinstance(h.formatter, (JsonFormatter, TextFormatter))]
    if managed and type(managed[0].formatter) is type(formatter):
        return
    handler = logging.StreamHandler()
    handler.setFormatter(formatter)
    root.handlers = [handler]
