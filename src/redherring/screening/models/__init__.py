"""
src/redherring/screening/models/__init__.py

Public model exports for the domain layer.

This module MUST NOT import from: redherring.screening.intelligence, redherring.screening.api, redherring.screening.engine, redherring.screening.rules.
It depends only on the standard library and Pydantic.

Exports:
    - All domain enumerations (IPOStatus, Verdict, RuleCategory, etc.)
    - Domain exceptions (DomainError and subclasses)
    - Core value types (ExtractedValue, SourceCitation)
    - Domain models (CompanyData and all sub-models)
    - Result/report models (RuleResult, RuleMetadata, IPOReport, etc.)
    - Versioning models (RulesetVersion)
"""

from redherring.screening.models.company_data import (
    AuditCommittee,
    AuditorData,
    CompanyData,
    CompanyIdentification,
    EligibilityDeclarations,
    FinancialHistory,
    FiscalYear,
    GovernanceData,
    IssueDetails,
    LitigationCase,
    LitigationData,
    PromoterData,
    PromoterEntity,
    RelatedPartyData,
    RPTTransaction,
)
from redherring.screening.models.enums import (
    ConfidenceLevel,
    ExtractionMethod,
    FieldStatus,
    IPOStatus,
    LegalCategory,
    ListingRoute,
    RuleCategory,
    ScreeningOutcome,
    StatementBasis,
    Verdict,
    VerificationStatus,
)
from redherring.screening.models.evidence import EvidenceRef
from redherring.screening.models.exceptions import (
    DomainError,
    ReportNotFoundError,
    UnsupportedDocumentError,
)
from redherring.screening.models.extracted_value import ExtractedValue
from redherring.screening.models.human_review import (
    HumanFinalDecision,
    HumanReviewRecord,
    HumanReviewStatus,
)
from redherring.screening.models.ipo_report import EligibilityProgress, GapAnalysisItem, IPOReport
from redherring.screening.models.rule_result import RuleMetadata, RuleResult
from redherring.screening.models.ruleset_version import DEFAULT_RULESET_VERSION, RulesetVersion
from redherring.screening.models.source_citation import SourceCitation

__all__ = [
    # Enumerations
    "FieldStatus",
    "LegalCategory",
    "ListingRoute",
    "ScreeningOutcome",
    "StatementBasis",
    "VerificationStatus",
    "EligibilityDeclarations",
    "EvidenceRef",
    "IPOStatus",
    "Verdict",
    "RuleCategory",
    "ConfidenceLevel",
    "ExtractionMethod",
    "HumanReviewStatus",
    "HumanFinalDecision",
    # Exceptions
    "DomainError",
    "UnsupportedDocumentError",
    "ReportNotFoundError",
    # Value types
    "ExtractedValue",
    "SourceCitation",
    "HumanReviewRecord",
    # Company data models
    "CompanyData",
    "CompanyIdentification",
    "FinancialHistory",
    "FiscalYear",
    "PromoterData",
    "PromoterEntity",
    "GovernanceData",
    "AuditCommittee",
    "IssueDetails",
    "LitigationData",
    "LitigationCase",
    "RelatedPartyData",
    "RPTTransaction",
    "AuditorData",
    # Rule / result models
    "RuleMetadata",
    "RuleResult",
    # Report models
    "EligibilityProgress",
    "GapAnalysisItem",
    "IPOReport",
    # Versioning
    "RulesetVersion",
    "DEFAULT_RULESET_VERSION",
]
