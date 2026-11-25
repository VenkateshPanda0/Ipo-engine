"""System-wide constants for the IPO Engine."""

from __future__ import annotations

API_VERSION = "2.0.0"

# Every case belongs to an organisation. Without accounts there is exactly one, this one, so the
# data model is the same whether or not accounts are switched on.
DEFAULT_ORG_ID = "org-default"
DEFAULT_ORG_NAME = "Default organisation"
