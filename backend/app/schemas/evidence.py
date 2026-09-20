from pydantic import BaseModel

from app.core.enums import DocumentType, PersonRelation


class Document(BaseModel):
    document_id: str
    filename: str
    document_type: DocumentType
    title: str | None = None
    source_date: str | None = None
    thread_context: str | None = None


class EvidenceUnit(BaseModel):
    evidence_id: str
    document_id: str
    source_locator: str
    unit_index: int
    speaker_sender: str | None = None
    event_date: str | None = None
    timestamp_text: str | None = None
    thread_context: str | None = None
    raw_text: str
    text_hash: str
    is_truncated: bool = False


class Person(BaseModel):
    subject_id: str
    display_alias: str
    privacy_state: str = "ACTIVE"
    display_name: str | None = None


class PersonAlias(BaseModel):
    alias_id: str
    subject_id: str
    alias: str
    alias_type: str


class EvidencePersonLink(BaseModel):
    evidence_id: str
    subject_id: str
    relation: PersonRelation
