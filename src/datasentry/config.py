"""从安全的本地默认值和环境变量加载应用配置。"""

from pathlib import Path
from typing import Literal

from pydantic import AnyHttpUrl, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """DataSentry 运行时配置。"""

    model_config = SettingsConfigDict(
        env_prefix="DATASENTRY_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    environment: Literal["development", "test", "production"] = "development"
    database_path: Path = Path("var/datasentry.db")
    targets_file: Path = Path("config/targets.toml")
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = "INFO"
    log_format: Literal["json", "console"] = "json"
    api_host: str = "127.0.0.1"
    api_port: int = 8000
    api_cors_origins: list[str] = Field(default_factory=lambda: ["http://localhost:5173"])
    grafana_url: AnyHttpUrl | None = None
    llm_provider: Literal["disabled", "mock", "openai_compatible"] = "disabled"
    llm_base_url: AnyHttpUrl | None = None
    llm_model: str | None = None
    llm_api_key: str | None = None
    llm_timeout_seconds: int = 20
