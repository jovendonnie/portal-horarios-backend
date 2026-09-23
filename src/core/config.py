from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "Portal Horarios Backend"
    mongo_uri: str = "MONGO_URI=mongodb+srv://desarrollo_db_user:odcrCJ4Ae6Wkg3gB@cluster0.a6fysj8.mongodb.net/?appName=Cluster0"
    mongo_db_name: str = "portal_horarios"

    max_failed_attempts: int = 5
    lockout_minutes: int = 15
    session_inactivity_minutes: int = 30

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
