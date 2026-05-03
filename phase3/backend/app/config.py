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
    scraper_flipkart_deals_url: str = "https://www.flipkart.com/offers-store"
    scraper_nykaa_deals_url: str = "https://www.nykaa.com/sp/offer-zone"
    scraper_max_pages: int = 5
    scraper_page_timeout_ms: int = 30_000
    scraper_use_fixtures: bool = False
    scraper_schedule_hours: int = 6
    # Stagger Flipkart/Nykaa relative to Amazon so we don't hammer all three at once.
    scraper_flipkart_schedule_hours: int = 6
    scraper_nykaa_schedule_hours: int = 12
    # Window over which /health/scrapers computes per-platform success rate.
    health_window_days: int = 30

    api_cors_origins: list[str] = ["http://localhost:3000"]
    api_default_page_size: int = 24
    api_max_page_size: int = 100

    enable_scheduler: bool = True

    # --- Phase 2: semantic search ---
    # Provider for product + query embeddings.
    #   "hashing"               — deterministic, in-process, no external deps. Good for tests/dev.
    #   "sentence-transformers" — local model (all-MiniLM-L6-v2 by default). Production-grade quality.
    #   "openai"                — text-embedding-3-small. Requires OPENAI_API_KEY.
    embedding_provider: str = "hashing"
    embedding_model: str = "hashing-v1"
    embedding_dim: int = 256
    embedding_batch_size: int = 64
    openai_api_key: str | None = None
    openai_embedding_model: str = "text-embedding-3-small"

    # Indexer
    indexer_schedule_minutes: int = 30

    # Search defaults
    search_default_mode: str = "semantic"  # "keyword" | "semantic" | "hybrid"
    search_top_k: int = 200  # candidates pulled from vector DB before re-ranking
    rank_w_similarity: float = 0.6
    rank_w_discount: float = 0.2
    rank_w_rating: float = 0.2


@lru_cache
def get_settings() -> Settings:
    return Settings()
