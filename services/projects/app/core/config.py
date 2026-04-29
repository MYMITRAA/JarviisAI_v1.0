from typing import List
from pydantic_settings import BaseSettings
from pydantic import field_validator
from functools import lru_cache


class Settings(BaseSettings):
    ENVIRONMENT: str = "development"
    LOG_LEVEL: str = "debug"

    DATABASE_URL: str
    REDIS_URL: str
    JWT_SECRET: str
    JWT_ALGORITHM: str = "HS256"

    ALLOWED_ORIGINS: List[str] = ["http://localhost:3000"]

    @field_validator("ALLOWED_ORIGINS", mode="before")
    @classmethod
    def parse_origins(cls, v):
        if isinstance(v, str):
            return [o.strip() for o in v.split(",")]
        return v

    # Service URLs
    AUTH_SERVICE_URL: str = "http://auth-service:8001"
    CRAWLER_SERVICE_URL: str = "http://crawler:8003"
    AI_ORCHESTRATOR_URL: str = "http://ai-orchestrator:8004"
    TEST_EXECUTOR_URL: str = "http://test-executor:8005"
    RESULTS_SERVICE_URL: str = "http://results:8006"

    # New SaaS platform services
    USAGE_SERVICE_URL: str = "http://usage:8018"
    EVENTS_SERVICE_URL: str = "http://events:8017"

    # GitHub App
    GITHUB_APP_ID: str = ""
    GITHUB_APP_PRIVATE_KEY: str = ""
    GITHUB_WEBHOOK_SECRET: str = ""

    class Config:
        env_file = ".env"
        case_sensitive = True


@lru_cache()
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
