from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    ENVIRONMENT: str = "development"
    LOG_LEVEL: str = "debug"
    ANTHROPIC_API_KEY: str = ""
    OPENAI_API_KEY: str = ""
    REDIS_URL: str = "redis://:redis_secret@redis:6379/4"
    PROJECTS_SERVICE_URL: str = "http://projects:8002"
    TEST_EXECUTOR_URL: str = "http://test-executor:8005"

    # AI Models — always use the latest Sonnet for best quality/speed balance
    PRIMARY_MODEL: str = "claude-sonnet-4-20250514"
    FALLBACK_MODEL: str = "gpt-4o"
    MAX_TOKENS: int = 8192
    PROMPT_VERSION: str = "v1"

    # Generation limits
    MAX_TESTS_PER_RUN: int = 50
    MAX_PAGES_IN_CONTEXT: int = 15
    MAX_ELEMENTS_PER_PAGE: int = 30

    class Config:
        env_file = ".env"


@lru_cache()
def get_settings():
    return Settings()


settings = get_settings()
