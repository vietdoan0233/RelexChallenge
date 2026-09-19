-- Evidence Locker schema.
--
-- Two classes of table, distinguished by how `rebuild` treats them:
--
-- PERSISTENT (never dropped by rebuild; only shrinks via explicit deletion):
--   source_locators
--
-- REBUILDABLE (dropped and regenerated from data/source/ plus the reviewed
-- identity manifest, data/source/reviewed_identities.json, on every
-- ingestion run):
--   documents, evidence_units, people, person_aliases, evidence_people,
--   evidence_embeddings, evidence_fts
--
-- people/person_aliases are rebuildable, not persistent: identity is a
-- pure function of two sanitizable inputs (data/source/ and the reviewed
-- identity manifest), so regenerating it from scratch every run is safe --
-- a deleted person's traces are already gone from both inputs by the time
-- a rebuild runs -- and it is what stops a false identity from an earlier,
-- looser extraction pass from surviving forever just because INSERT OR
-- IGNORE never removes anything on its own.
--
-- source_locators stays persistent so that deleting one person's evidence
-- and then running the normal rebuild command can never renumber or
-- resurrect anything: rebuild only ever re-derives evidence_units for
-- source_locators entries that still exist. See CLAUDE.md section 7.3
-- and 18.3.

CREATE TABLE IF NOT EXISTS documents (
    document_id TEXT PRIMARY KEY,
    filename TEXT NOT NULL,
    document_type TEXT NOT NULL,
    title TEXT,
    source_date TEXT,
    thread_context TEXT
);

-- Persistent source-locator manifest (CLAUDE.md 7.3). Assigns each source
-- unit a locator once, at first ingestion, and never renumbers it. A
-- position-shaped locator (genesis_position) is safe here specifically
-- because it is captured once and looked up thereafter, not recomputed
-- from the current (post-deletion) unit count on every rebuild.
CREATE TABLE IF NOT EXISTS source_locators (
    document_id TEXT NOT NULL,
    source_locator TEXT NOT NULL,
    content_fingerprint TEXT NOT NULL,
    genesis_position INTEGER NOT NULL,
    first_seen_at TEXT NOT NULL,
    PRIMARY KEY (document_id, source_locator)
);
CREATE INDEX IF NOT EXISTS idx_source_locators_fingerprint
    ON source_locators(document_id, content_fingerprint);

CREATE TABLE IF NOT EXISTS evidence_units (
    evidence_id TEXT PRIMARY KEY,
    document_id TEXT NOT NULL REFERENCES documents(document_id) ON DELETE CASCADE,
    source_locator TEXT NOT NULL,
    unit_index INTEGER NOT NULL,
    speaker_sender TEXT,
    event_date TEXT,
    timestamp_text TEXT,
    thread_context TEXT,
    raw_text TEXT NOT NULL,
    text_hash TEXT NOT NULL,
    is_truncated INTEGER NOT NULL DEFAULT 0,
    UNIQUE(document_id, unit_index),
    UNIQUE(document_id, source_locator)
);
CREATE INDEX IF NOT EXISTS idx_evidence_units_document ON evidence_units(document_id);

CREATE TABLE IF NOT EXISTS people (
    person_id TEXT PRIMARY KEY,
    canonical_name TEXT NOT NULL UNIQUE
);

CREATE TABLE IF NOT EXISTS person_aliases (
    alias_id TEXT PRIMARY KEY,
    person_id TEXT NOT NULL REFERENCES people(person_id) ON DELETE CASCADE,
    alias TEXT NOT NULL,
    alias_type TEXT NOT NULL,
    UNIQUE(person_id, alias)
);
CREATE INDEX IF NOT EXISTS idx_person_aliases_alias ON person_aliases(alias);

CREATE TABLE IF NOT EXISTS evidence_people (
    evidence_id TEXT NOT NULL REFERENCES evidence_units(evidence_id) ON DELETE CASCADE,
    person_id TEXT NOT NULL REFERENCES people(person_id) ON DELETE CASCADE,
    relation TEXT NOT NULL, -- AUTHOR | SPEAKER | MENTIONED
    PRIMARY KEY (evidence_id, person_id, relation)
);
CREATE INDEX IF NOT EXISTS idx_evidence_people_person ON evidence_people(person_id);

CREATE TABLE IF NOT EXISTS evidence_embeddings (
    evidence_id TEXT PRIMARY KEY REFERENCES evidence_units(evidence_id) ON DELETE CASCADE,
    model_name TEXT NOT NULL,
    vector_json TEXT NOT NULL
);

CREATE VIRTUAL TABLE IF NOT EXISTS evidence_fts USING fts5(
    evidence_id UNINDEXED,
    raw_text
);

CREATE TABLE IF NOT EXISTS cases (
    case_id TEXT PRIMARY KEY,
    query TEXT NOT NULL,
    receipt_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS case_evidence (
    case_id TEXT NOT NULL REFERENCES cases(case_id) ON DELETE CASCADE,
    evidence_id TEXT NOT NULL REFERENCES evidence_units(evidence_id) ON DELETE CASCADE,
    usage TEXT NOT NULL, -- SUPPORT | CONFLICT | TIMELINE
    PRIMARY KEY(case_id, evidence_id, usage)
);

CREATE TABLE IF NOT EXISTS pulse_findings (
    finding_id TEXT PRIMARY KEY,
    category TEXT NOT NULL,
    title TEXT NOT NULL,
    summary TEXT NOT NULL,
    status TEXT NOT NULL,
    finding_json TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS finding_evidence (
    finding_id TEXT NOT NULL REFERENCES pulse_findings(finding_id) ON DELETE CASCADE,
    evidence_id TEXT NOT NULL REFERENCES evidence_units(evidence_id) ON DELETE CASCADE,
    PRIMARY KEY(finding_id, evidence_id)
);
