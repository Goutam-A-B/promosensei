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
    scraper_flipkart_schedule_hours: int = 6
    scraper_nykaa_schedule_hours: int = 12
    health_window_days: int = 30

    api_cors_origins: list[str] = ["http://localhost:3000"]
    api_default_page_size: int = 24
    api_max_page_size: int = 100

    enable_scheduler: bool = True

    embedding_provider: str = "hashing"
    embedding_model: str = "hashing-v1"
    embedding_dim: int = 256
    embedding_batch_size: int = 64
    openai_api_key: str | None = None
    openai_embedding_model: str = "text-embedding-3-small"

    indexer_schedule_minutes: int = 30

    search_default_mode: str = "semantic"
    search_top_k: int = 200
    rank_w_similarity: float = 0.6
    rank_w_discount: float = 0.2
    rank_w_rating: float = 0.2

    # --- Phase 4: caching, freshness, resilience, observability ---

    # Cache backend.
    #   "memory" — in-process TTL+LRU. Default. Zero ops cost.
    #   "redis"  — shared cache across processes. Requires redis-py + a reachable server.
    #   "none"   — disable caching entirely (useful for tests that assert DB calls).
    cache_provider: str = "memory"
    cache_ttl_seconds: int = 300  # 5 min, matches architecture.md
    cache_max_entries: int = 1024  # in-memory LRU cap
    cache_redis_url: str = "redis://localhost:6379/0"

    # Lightweight price-only refresher. Touches existing listings without
    # rerunning the matcher — much cheaper than a full scrape so we can run
    # it more often. Architecture.md target: 30 min.
    price_refresh_minutes: int = 30
    price_refresh_max_age_hours: int = 6  # only refresh listings staler than this
    price_refresh_batch_size: int = 200

    # Resilience around scraper calls.
    scraper_retry_attempts: int = 3
    scraper_retry_base_delay_seconds: float = 1.0
    scraper_retry_max_delay_seconds: float = 30.0
    # Circuit breaker — after N consecutive failures we pause the scraper
    # for `cooldown` seconds. Other platforms keep running.
    breaker_failure_threshold: int = 3
    breaker_cooldown_seconds: int = 600

    # Observability.
    log_level: str = "INFO"
    log_format: str = "json"  # "json" | "text"
    metrics_enabled: bool = True

    # Eval harness regression thresholds — used by tests/test_eval_regression.py.
    # Calibrated against the hashing embedder baseline on the seeded fixtures.
    # When swapping to `sentence-transformers`, bump both upwards.
    eval_min_ndcg_at_5: float = 0.8
    eval_min_precision_at_3: float = 0.4


@lru_cache
def get_settings() -> Settings:
    return Settings()
