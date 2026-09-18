from dataclasses import dataclass, field


@dataclass
class ParsedUnit:
    raw_text: str
    speaker_sender: str | None = None
    speaker_email: str | None = None
    timestamp_text: str | None = None
    thread_context: str | None = None
    is_truncated: bool = False
    # A message's own date, when it differs from the document's overall
    # source_date -- true for every email/report message except the
    # newest, since a reverse-chronological thread spans many dates.
    # None means "use the document's source_date", correct for
    # transcripts where one meeting has exactly one date throughout.
    event_date: str | None = None
    # A locator inherent to the source itself (an email's Date header, a
    # transcript turn's timestamp) that is already stable without help.
    # None means this unit has no such natural identifier and must go
    # through the persistent source-locator manifest instead.
    natural_locator: str | None = None


@dataclass
class TranscriptFragment:
    """One raw caption/dialogue fragment, before same-speaker merging.
    Kept separate from ParsedUnit because merging can only be decided
    safely once each fragment has a genesis position from the locator
    manifest -- see locator_manifest.py's module docstring."""

    raw_text: str
    speaker_sender: str
    timestamp_text: str | None = None
    natural_locator: str | None = None  # Teams: f"t{seconds}"; INTERNAL: None


@dataclass
class ParsedDocument:
    document_id: str
    filename: str
    document_type: str
    title: str | None
    source_date: str | None
    thread_context: str | None
    units: list[ParsedUnit] = field(default_factory=list)
    # Populated instead of `units` for TRANSCRIPT documents; service.py
    # turns these into final `units` via transcript.assign_locators_and_merge
    # once each fragment has a genesis position to merge safely against.
    fragments: list[TranscriptFragment] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    attendees: list[str] = field(default_factory=list)
