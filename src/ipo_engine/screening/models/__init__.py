"""
src/ipo_engine/screening/models/__init__.py

Public model exports for the domain layer.

This module MUST NOT import from: ipo_engine.screening.intelligence, ipo_engine.screening.api,
ipo_engine.screening.engine, ipo_engine.screening.rules.
It depends only on the standard library and Pydantic.

Exports:
    - All domain enumerations (IPOStatus, Verdict, RuleCategory, etc.)
    - Domain exceptions (DomainError and subclasses)
    - Core value types (ExtractedValue, SourceCitation)
    - Domain models (CompanyData and all sub-models)
    - Result/report models (RuleResult, RuleMetadata, IPOReport, etc.)
    - Versioning models (RulesetVersion)
"""

from ipo_engine.screening.models.company_data import (
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
from ipo_engine.screening.models.enums import (
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
from ipo_engine.screening.models.evidence import EvidenceRef
from ipo_engine.screening.models.exceptions import (
    DomainError,
    ReportNotFoundError,
    UnsupportedDocumentError,
)
from ipo_engine.screening.models.extracted_value import ExtractedValue
from ipo_engine.screening.models.human_review import (
    HumanFinalDecision,
    HumanReviewRecord,
    HumanReviewStatus,
)
from ipo_engine.screening.models.ipo_report import EligibilityProgress, GapAnalysisItem, IPOReport
from ipo_engine.screening.models.rule_result import RuleMetadata, RuleResult
from ipo_engine.screening.models.ruleset_version import DEFAULT_RULESET_VERSION, RulesetVersion
from ipo_engine.screening.models.source_citation import SourceCitation

__all__ = [
    "DEFAULT_RULESET_VERSION",
    "AuditCommittee",
    "AuditorData",
    # Company data models
    "CompanyData",
    "CompanyIdentification",
    "ConfidenceLevel",
    # Exceptions
    "DomainError",
    "EligibilityDeclarations",
    # Report models
    "EligibilityProgress",
    "EvidenceRef",
    # Value types
    "ExtractedValue",
    "ExtractionMethod",
    # Enumerations
    "FieldStatus",
    "FinancialHistory",
    "FiscalYear",
    "GapAnalysisItem",
    "GovernanceData",
    "HumanFinalDecision",
    "HumanReviewRecord",
    "HumanReviewStatus",
    "IPOReport",
    "IPOStatus",
    "IssueDetails",
    "LegalCategory",
    "ListingRoute",
    "LitigationCase",
    "LitigationData",
    "PromoterData",
    "PromoterEntity",
    "RPTTransaction",
    "RelatedPartyData",
    "ReportNotFoundError",
    "RuleCategory",
    # Rule / result models
    "RuleMetadata",
    "RuleResult",
    # Versioning
    "RulesetVersion",
    "ScreeningOutcome",
    "SourceCitation",
    "StatementBasis",
    "UnsupportedDocumentError",
    "Verdict",
    "VerificationStatus",
]
