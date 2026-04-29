import os
from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    ENVIRONMENT: str = "development"
    LOG_LEVEL: str = "debug"
    ANTHROPIC_API_KEY: str = ""
    DATABASE_URL: str = os.getenv("DATABASE_URL", "")
    REDIS_URL: str = os.getenv("REDIS_URL", "redis://:changeme@redis:6379/6")
    PROJECTS_SERVICE_URL: str = "http://projects:8002"
    PRIMARY_MODEL: str = "claude-sonnet-4-20250514"

    # Healing config
    SIMILARITY_THRESHOLD: float = 0.75   # min confidence to auto-apply a fix
    MAX_HEAL_ATTEMPTS: int = 3            # per test case per run
    SELECTOR_CANDIDATE_LIMIT: int = 10   # DOM candidates to evaluate

    class Config:
        env_file = ".env"


@lru_cache()
def get_settings():
    return Settings()

settings = get_settings()
