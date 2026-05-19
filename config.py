"""Application configuration loaded from environment variables."""

from __future__ import annotations

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

XAI_API_BASE_URL = "https://api.x.ai/v1"
XAI_MISSING_KEY_MESSAGE = (
    "XAI_API_KEY is not configured. Set XAI_API_KEY in your .env file "
    "or enable USE_MOCK_LLM=true for local development without xAI."
)


class Settings(BaseSettings):
    """Centralized settings for backend and AI services."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    xai_api_key: str | None = Field(default=None, alias="XAI_API_KEY")
    xai_model: str = Field(default="grok-4.3", alias="XAI_MODEL")
    xai_base_url: str = Field(default=XAI_API_BASE_URL, alias="XAI_BASE_URL")
    max_retries: int = Field(default=3, alias="LLM_MAX_RETRIES")
    api_base_url: str = Field(
        default="http://127.0.0.1:8000",
        alias="API_BASE_URL",
    )
    use_mock_llm: bool = Field(default=False, alias="USE_MOCK_LLM")

    @property
    def has_xai_credentials(self) -> bool:
        """Return True when an xAI API key is configured."""
        return bool(self.xai_api_key and self.xai_api_key.strip())

    def require_xai_api_key(self) -> str:
        """
        Return the xAI API key or raise a clear configuration error.

        Skips validation when mock mode is enabled.
        """
        if self.use_mock_llm:
            return ""
        if not self.has_xai_credentials:
            raise ValueError(XAI_MISSING_KEY_MESSAGE)
        return self.xai_api_key.strip()  # type: ignore[union-attr]


@lru_cache
def get_settings() -> Settings:
    """Cached settings singleton."""
    return Settings()
