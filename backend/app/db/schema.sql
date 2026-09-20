-- Evidence Locker schema.
--
-- Two classes of table, distinguished by how `rebuild` treats them:
--
-- PERSISTENT (never dropped by rebuild; only ever grow or change state via
-- explicit deletion/pseudonymisation):
--   source_locators, people, person_aliases, privacy_operations
--
-- REBUILDABLE (dropped and regenerated from data/source/ plus the reviewed
-- identity manifest, data/source/reviewed_identities.json, on every
-- ingestion run):
--   documents, evidence_units, evidence_people, evidence_embeddings,
--   evidence_fts
--
-- Architecture v1.6 (AGENTS.md/CLAUDE.md 18.0): people/person_aliases moved
-- from rebuildable to persistent. A subject's subject_id and display_alias
-- must survive a normal rebuild -- and, more importantly, a rebuild must
-- never be able to mint a *second* identity for someone already known --
-- so identity can no longer be a name-derived function recomputed from
-- scratch every run the way it was under the old person_id=slugify(name)
-- design. Ingestion instead resolves each structural name it finds against
-- the persistent table (by an existing FULL_NAME alias, or by an existing
-- display_alias when the name it finds *is* someone's already-assigned
-- alias, e.g. after pseudonymisation rewrote the source to say so) and
-- only creates a new subject_id/display_alias when nothing matches. See
-- app/ingestion/people.py. evidence_people stays rebuildable: it is a pure
-- join of (now-stable) subject_id against (already-stable) evidence_id, so
-- recomputing it fresh every run is still safe and still self-heals a
-- stale relationship left by a since-corrected source file.
--
-- source_locators stays persistent so that pseudonymising one person's
-- evidence and then running the normal rebuild command can never renumber
-- anything: rebuild only ever re-derives evidence_units for source_locators
-- entries that still exist. See CLAUDE.md section 7.3 and 18.3.

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
    revoked_at TEXT NULL,
    -- Whether this transcript fragment began a new Evidence Unit at genesis
    -- (1) or continued the previous one (0); NULL = not yet recorded. Persisted
    -- so redaction, which makes several speakers share one generic label, can
    -- never fuse two different people's adjacent turns (CLAUDE.md 18.8).
    starts_group INTEGER NULL,
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

-- subject_id is a cryptographically random UUID (never a name slug) and is
-- the stable relational key everywhere -- profiles, evidence relationships,
-- privacy_operations, and API routes. display_alias is generated
-- independently and just as randomly, for *every* participant (not only a
-- pseudonymised one), so a pseudonymisation operation never needs to mint a
-- fresh identifier at the moment it runs: it switches which fields are
-- public, it does not create the alias. display_name holds the real name
-- only while privacy_state = 'ACTIVE'; pseudonymisation clears it to NULL.
CREATE TABLE IF NOT EXISTS people (
    subject_id TEXT PRIMARY KEY,
    display_alias TEXT NOT NULL UNIQUE,
    privacy_state TEXT NOT NULL DEFAULT 'ACTIVE' CHECK (privacy_state IN ('ACTIVE', 'PSEUDONYMISED')),
    display_name TEXT,
    profile_metadata_json TEXT,
    pseudonymised_at TEXT,
    pseudonymisation_operation_id TEXT,
    verification_result_json TEXT
);

-- Only ACTIVE, original-identity-bearing strings live here (full name,
-- email, and reviewed short forms). A subject's display_alias is never
-- duplicated into this table -- it lives solely on people.display_alias --
-- so pseudonymisation's "remove original aliases" step is one DELETE by
-- subject_id, and this table is provably empty for every pseudonymised
-- subject rather than merely missing certain rows.
CREATE TABLE IF NOT EXISTS person_aliases (
    alias_id TEXT PRIMARY KEY,
    subject_id TEXT NOT NULL REFERENCES people(subject_id) ON DELETE RESTRICT,
    alias TEXT NOT NULL,
    alias_type TEXT NOT NULL,
    UNIQUE(subject_id, alias)
);
CREATE INDEX IF NOT EXISTS idx_person_aliases_alias ON person_aliases(alias);

-- ON DELETE RESTRICT (not CASCADE): pseudonymisation must never delete a
-- participant row or their evidence relationships, so the schema itself
-- refuses a query that tried to cascade one away (CLAUDE.md 18.0.1).
CREATE TABLE IF NOT EXISTS evidence_people (
    evidence_id TEXT NOT NULL REFERENCES evidence_units(evidence_id) ON DELETE CASCADE,
    subject_id TEXT NOT NULL REFERENCES people(subject_id) ON DELETE RESTRICT,
    relation TEXT NOT NULL, -- AUTHOR | SPEAKER | MENTIONED
    PRIMARY KEY (evidence_id, subject_id, relation)
);
CREATE INDEX IF NOT EXISTS idx_evidence_people_subject ON evidence_people(subject_id);

-- Public pseudonymisation audit trail (CLAUDE.md 18.0.3). Deliberately thin:
-- no original name/email, no raw text, no reversible mapping. The original
-- identity exists only as ciphertext in the separate vault file.
CREATE TABLE IF NOT EXISTS privacy_operations (
    operation_id TEXT PRIMARY KEY,
    subject_id TEXT NOT NULL REFERENCES people(subject_id) ON DELETE RESTRICT,
    from_state TEXT NOT NULL,
    to_state TEXT NOT NULL,
    display_alias TEXT NOT NULL,
    pseudonymised_at TEXT,
    verification_result_json TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_privacy_operations_subject ON privacy_operations(subject_id);

CREATE TABLE IF NOT EXISTS evidence_embeddings (
    evidence_id TEXT PRIMARY KEY REFERENCES evidence_units(evidence_id) ON DELETE CASCADE,
    model_name TEXT NOT NULL,
    vector_json TEXT NOT NULL
);

-- thread_context and speaker_sender are indexed beside the text so a short
-- unit ("Received, thank you.") stays findable through its thread title or
-- sender. Retrieval weights them below raw_text (retrieval/lexical.py).
-- Anything that scrubs a person from application storage must scrub these
-- two columns as well as raw_text (CLAUDE.md 18.5).
CREATE VIRTUAL TABLE IF NOT EXISTS evidence_fts USING fts5(
    evidence_id UNINDEXED,
    raw_text,
    thread_context,
    speaker_sender
);

-- Version stamps for derived structures (e.g. which text FTS was built from), so
-- a stale index is rebuilt in place rather than silently served.
CREATE TABLE IF NOT EXISTS derived_meta (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
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
