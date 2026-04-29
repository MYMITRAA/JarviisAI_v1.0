from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    ENVIRONMENT: str = "development"
    LOG_LEVEL: str = "debug"
    DATABASE_URL: str = "postgresql+asyncpg://jarviis:jarviis_secret@postgres:5432/jarviisdb"
    REDIS_URL: str = "redis://:redis_secret@redis:6379/13"
    JWT_SECRET: str = ""
    JWT_ALGORITHM: str = "HS256"
    AUTH_SERVICE_URL: str = "http://auth-service:8001"
    APP_URL: str = "http://localhost:3000"
    SSO_BASE_URL: str = "http://localhost:8015"

    # SAML signing key (PEM)
    SAML_PRIVATE_KEY: str = ""
    SAML_CERTIFICATE: str = ""

    class Config:
        env_file = ".env"


@lru_cache()
def get_settings():
    return Settings()

settings = get_settings()
