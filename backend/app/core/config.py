from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file="../.env", extra="ignore")

    google_api_key: str = ""
    gemini_model: str = ""
    gemini_embedding_model: str = ""
    database_path: str = "./data/keeper.db"
    source_data_dir: str = "./data/source"


@lru_cache
def get_settings() -> Settings:
    return Settings()
