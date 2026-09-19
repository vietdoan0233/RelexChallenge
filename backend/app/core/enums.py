from enum import StrEnum


class DocumentType(StrEnum):
    TRANSCRIPT = "TRANSCRIPT"
    EMAIL = "EMAIL"
    REPORT = "REPORT"


class PersonRelation(StrEnum):
    AUTHOR = "AUTHOR"
    SPEAKER = "SPEAKER"
    MENTIONED = "MENTIONED"


class AliasType(StrEnum):
    FULL_NAME = "FULL_NAME"
    EMAIL = "EMAIL"
    FIRST_NAME = "FIRST_NAME"
    LAST_NAME = "LAST_NAME"
    INITIALS = "INITIALS"
    NICKNAME = "NICKNAME"
    VARIANT = "VARIANT"


class Stance(StrEnum):
    """How a piece of evidence relates to a decision. Inferred from the
    conversation itself -- there is no authority hierarchy (CLAUDE.md 2.2)."""

    PROPOSAL = "PROPOSAL"
    ASSUMPTION = "ASSUMPTION"
    OBJECTION = "OBJECTION"
    AGREEMENT = "AGREEMENT"
    COMMITMENT = "COMMITMENT"
    STATUS_UPDATE = "STATUS_UPDATE"
    IMPLEMENTATION_EVIDENCE = "IMPLEMENTATION_EVIDENCE"
    SUPERSEDED = "SUPERSEDED"
    UNCERTAIN = "UNCERTAIN"


class Confidence(StrEnum):
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"


class CaseStatus(StrEnum):
    SUPPORTED = "SUPPORTED"
    PARTIALLY_SUPPORTED = "PARTIALLY_SUPPORTED"
    CONFLICTING_EVIDENCE = "CONFLICTING_EVIDENCE"
    INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"
