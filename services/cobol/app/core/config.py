from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    ENVIRONMENT: str = "development"
    LOG_LEVEL: str = "debug"
    ANTHROPIC_API_KEY: str = ""
    PRIMARY_MODEL: str = "claude-sonnet-4-20250514"
    REDIS_URL: str = "redis://:redis_secret@redis:6379/12"
    PROJECTS_SERVICE_URL: str = "http://projects:8002"

    class Config:
        env_file = ".env"


@lru_cache()
def get_settings():
    return Settings()

settings = get_settings()
