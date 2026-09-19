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
