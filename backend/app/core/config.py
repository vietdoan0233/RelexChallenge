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

    @property
    def app_name_display(self) -> str:
        return self.app_name or _DEFAULT_APP_NAME

    @property
    def database_path_resolved(self) -> Path:
        return _resolve(self.database_path)

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
