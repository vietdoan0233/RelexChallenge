from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

# CLAUDE.md's own dev commands always `cd backend` before running uvicorn,
# pytest, or the ingest script, but data/ lives at the repo root as a
# sibling of backend/, not inside it. Anchoring here to a fixed repo-root
# path -- rather than resolving DATABASE_PATH/SOURCE_DATA_DIR against
# whatever the process's current directory happens to be -- means the
# same .env values work no matter where a command is launched from.
_REPO_ROOT = Path(__file__).resolve().parents[3]


_DEFAULT_APP_NAME = "Organizational Memory Auditor"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=_REPO_ROOT / ".env", extra="ignore")

    # "KEEPER" is a temporary project codename, not a frozen brand: runtime
    # surfaces (API title, CLI text, generated artifacts) must read this
    # instead of hardcoding it, so renaming later is a config change, not
    # a code change.
    app_name: str = ""

    # Organizer-provided GPT connection details. These remain empty placeholders
    # until the hackathon API contract and credentials are available.
    gpt_api_key: str = ""
    gpt_base_url: str = ""
    gpt_model: str = ""
    gpt_embedding_model: str = ""
    database_path: str = "./data/app.db"
    source_data_dir: str = "./data/source"

    # Architecture v1.6 (AGENTS.md/CLAUDE.md 18.0.3): the reversal vault is a
    # separate encrypted file, never a table inside database_path, so a plain
    # SQLite connection to the main database has no path to it at all.
    pseudonym_vault_path: str = "./data/private-vault/vault.db.enc"
    pseudonym_vault_key: str = ""

    # Gates POST /api/privacy/pseudonymise and the admin reversal endpoint.
    # Empty means "not configured" -- both endpoints fail closed (401) rather
    # than treating a missing token as "no auth required".
    privacy_admin_token: str = ""

    # The known clean-archive baseline for this challenge's 45-document
    # corpus (AGENTS.md/CLAUDE.md checkpoint, confirmed by the 2026-09-19
    # audit; pseudonymisation/reversal never change these counts, since
    # neither ever adds/removes an Evidence Unit). /api/readiness compares
    # the live counts against these exactly, rather than merely "non-zero",
    # so a partially-ingested or silently drifted archive is reported
    # not-ready. Configurable (not a bare literal in main.py) so a test can
    # point them at a smaller synthetic fixture's real counts instead.
    expected_document_count: int = 45
    expected_evidence_unit_count: int = 2534
    expected_fts_row_count: int = 2534
    expected_embedding_row_count: int = 2534

    @property
    def app_name_display(self) -> str:
        return self.app_name or _DEFAULT_APP_NAME

    @property
    def database_path_resolved(self) -> Path:
        return _resolve(self.database_path)

    @property
    def pseudonym_vault_path_resolved(self) -> Path:
        return _resolve(self.pseudonym_vault_path)

    @property
    def privacy_ops_dir_resolved(self) -> Path:
        """Beside the database, so a test pointing DATABASE_PATH at a temp
        directory gets a temp operations folder too (CLAUDE.md 0.5)."""
        return self.database_path_resolved.parent / "privacy_ops"

    @property
    def derived_artifact_dirs_resolved(self) -> list[Path]:
        base = self.database_path_resolved.parent
        return [base / "artifacts", base / "cache"]

    @property
    def source_data_dir_resolved(self) -> Path:
        return _resolve(self.source_data_dir)

    @property
    def missing_embedding_configuration_fields(self) -> tuple[str, ...]:
        """Names only: callers can explain an incomplete setup without ever
        exposing a credential or endpoint value."""
        configured = {
            "GPT_API_KEY": self.gpt_api_key,
            "GPT_BASE_URL": self.gpt_base_url,
            "GPT_EMBEDDING_MODEL": self.gpt_embedding_model,
        }
        return tuple(name for name, value in configured.items() if not value)

    @property
    def has_any_embedding_configuration(self) -> bool:
        return len(self.missing_embedding_configuration_fields) < 3

    @property
    def has_complete_embedding_configuration(self) -> bool:
        return not self.missing_embedding_configuration_fields


def _resolve(value: str) -> Path:
    path = Path(value)
    return path if path.is_absolute() else _REPO_ROOT / path


@lru_cache
def get_settings() -> Settings:
    return Settings()
