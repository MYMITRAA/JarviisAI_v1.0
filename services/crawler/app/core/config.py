from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    ENVIRONMENT: str = "development"
    LOG_LEVEL: str = "debug"
    REDIS_URL: str = "redis://:redis_secret@redis:6379/3"
    PROJECTS_SERVICE_URL: str = "http://projects:8002"
    AI_ORCHESTRATOR_URL: str = "http://ai-orchestrator:8004"
    JWT_SECRET: str = ""
    JWT_ALGORITHM: str = "HS256"

    MAX_CRAWL_DEPTH: int = 3
    MAX_PAGES_PER_CRAWL: int = 50
    CRAWL_TIMEOUT_SECONDS: int = 120
    PAGE_LOAD_TIMEOUT_MS: int = 15000
    SCREENSHOT_BUCKET: str = "jarviis-screenshots"

    class Config:
        env_file = ".env"


@lru_cache()
def get_settings():
    return Settings()


settings = get_settings()
