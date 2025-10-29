"""
Configuration management for RCA API
"""
from pydantic_settings import BaseSettings
from typing import Optional


class Settings(BaseSettings):
    """Application settings from environment variables"""

    # Neo4j
    neo4j_uri: str = "bolt://localhost:7687"
    neo4j_user: str = "neo4j"
    neo4j_password: str

    # OpenAI (GPT-5)
    openai_api_key: str
    openai_model: str = "gpt-5"
    openai_reasoning_effort: str = "medium"  # minimal, low, medium, high
    openai_verbosity: str = "medium"  # low, medium, high

    # Embeddings
    embedding_model: str = "all-MiniLM-L6-v2"
    embedding_cache_dir: str = "./embeddings_cache"
    embedding_dimension: int = 384  # for all-MiniLM-L6-v2

    # Redis
    redis_url: Optional[str] = "redis://localhost:6379/0"

    # Slack
    slack_bot_token: Optional[str] = None
    slack_signing_secret: Optional[str] = None
    slack_channel_alerts: str = "#alerts"

    # API
    api_host: str = "0.0.0.0"
    api_port: int = 8083
    api_workers: int = 4
    debug: bool = False

    # Multi-tenancy
    default_client_id: str = "ab-01"
    enable_client_isolation: bool = True

    # Rate limiting
    rate_limit_per_minute: int = 60

    class Config:
        env_file = ".env"
        case_sensitive = False


# Global settings instance
settings = Settings()