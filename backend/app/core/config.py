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


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=_REPO_ROOT / ".env", extra="ignore")

    # Organizer-provided GPT connection details. These remain empty placeholders
    # until the hackathon API contract and credentials are available.
    gpt_api_key: str = ""
    gpt_base_url: str = ""
    gpt_model: str = ""
    gpt_embedding_model: str = ""
    database_path: str = "./data/keeper.db"
    source_data_dir: str = "./data/source"

    @property
    def database_path_resolved(self) -> Path:
        return _resolve(self.database_path)

    @property
    def source_data_dir_resolved(self) -> Path:
        return _resolve(self.source_data_dir)


def _resolve(value: str) -> Path:
    path = Path(value)
    return path if path.is_absolute() else _REPO_ROOT / path


@lru_cache
def get_settings() -> Settings:
    return Settings()
