from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import Optional


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env")

    # Qdrant
    qdrant_url: str
    qdrant_api_key: str

    # Groq (for LLM in later phases)
    groq_api_key: Optional[str] = None

    # Vapi
    vapi_api_key: Optional[str] = None
    vapi_public_key: Optional[str] = None

    # App
    default_user_id: str = "demo_user"
    drift_threshold: float = 0.25
    recent_window_days: int = 7
    baseline_window_days: int = 30

    # Embedding (all-MiniLM-L6-v2 via sentence-transformers)
    embedding_dim: int = 384
    collection_name: str = "mood_entries"


settings = Settings()
