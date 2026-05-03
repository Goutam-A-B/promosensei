from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    database_url: str = "postgresql+psycopg2://promosensei:promosensei@localhost:5432/promosensei"

    scraper_user_agent: str = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/127.0.0.0 Safari/537.36"
    )
    scraper_amazon_deals_url: str = "https://www.amazon.in/deals"
    scraper_max_pages: int = 5
    scraper_page_timeout_ms: int = 30_000
    scraper_use_fixtures: bool = False
    scraper_schedule_hours: int = 6

    api_cors_origins: list[str] = ["http://localhost:3000"]
    api_default_page_size: int = 24
    api_max_page_size: int = 100

    enable_scheduler: bool = True


@lru_cache
def get_settings() -> Settings:
    return Settings()
