import os
from pydantic_settings import BaseSettings
from functools import lru_cache
from typing import List


class Settings(BaseSettings):
    ENVIRONMENT: str = "development"
    LOG_LEVEL: str = "debug"

    DATABASE_URL: str = os.getenv("DATABASE_URL", "postgresql+asyncpg://jarviis:changeme@postgres:5432/jarviisdb")
    REDIS_URL: str = os.getenv("REDIS_URL", "redis://:changeme@redis:6379/8")
    JWT_SECRET: str = ""
    JWT_ALGORITHM: str = "HS256"

    PROJECTS_SERVICE_URL: str = "http://projects:8002"
    AUTH_SERVICE_URL: str = "http://auth-service:8001"

    # Docker registry
    REGISTRY_URL: str = "ghcr.io"
    REGISTRY_USERNAME: str = ""
    REGISTRY_TOKEN: str = ""

    # SSH key (base64-encoded PEM for target server connections)
    DEPLOY_SSH_PRIVATE_KEY: str = ""
    DEPLOY_SSH_USER: str = "deploy"

    # Deploy limits
    MAX_CONCURRENT_DEPLOYS: int = 5
    DEPLOY_TIMEOUT_SECONDS: int = 600   # 10 minutes
    ROLLBACK_HISTORY_COUNT: int = 10

    # Container registry pull secret encryption key
    SECRET_KEY: str = os.getenv("SECRET_KEY", "")

    ALLOWED_ORIGINS: List[str] = ["http://localhost:3000"]

    class Config:
        env_file = ".env"


@lru_cache()
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
