"""Test Executor service configuration — replaces scattered os.getenv() calls."""

from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    ENVIRONMENT: str = "development"
    LOG_LEVEL: str = "info"

    REDIS_URL: str = "redis://:redis_secret@redis:6379/5"
    PROJECTS_SERVICE_URL: str = "http://projects:8002"
    INTERNAL_SERVICE_SECRET: str = "jarviis-internal-secret"

    # Execution limits
    MAX_PARALLEL_WORKERS: int = 4
    TEST_TIMEOUT_MS: int = 30000          # 30 seconds per test
    RUN_TIMEOUT_MINUTES: int = 30         # 30 minutes per full run
    MAX_TESTS_PER_RUN: int = 200

    # Artifact storage (optional S3)
    S3_BUCKET: str = ""
    AWS_REGION: str = "us-east-1"

    class Config:
        env_file = ".env"


@lru_cache()
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
