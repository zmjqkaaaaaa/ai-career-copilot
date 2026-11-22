from functools import lru_cache
from decimal import Decimal
from pathlib import Path
from typing import Literal
from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict, Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy import URL

class ModelPrice(BaseModel):
    model_config = ConfigDict(extra="forbid")
    input_per_million: Decimal = Field(ge=0, le=10000, max_digits=12, decimal_places=6)
    output_per_million: Decimal = Field(ge=0, le=10000, max_digits=12, decimal_places=6)
    currency: str = Field(pattern="^[A-Z]{3}$")


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=Path(__file__).resolve().parents[2] / ".env", extra="ignore", hide_input_in_errors=True,
    )

    app_env: Literal["development", "test", "production"] = "development"
    db_host: str = "127.0.0.1"
    db_port: int = 3308
    db_name: str = "career_copilot"
    db_user: str = "career_app"
    db_password: SecretStr
    db_pool_size: int = Field(default=5, ge=1, le=30)
    db_max_overflow: int = Field(default=10, ge=0, le=30)
    db_pool_recycle_seconds: int = Field(default=1800, ge=60, le=7200)
    jwt_secret: SecretStr
    jwt_minutes: int = Field(default=30, ge=1, le=60)
    cors_origins: list[str] = ["http://127.0.0.1:5173", "http://localhost:5173"]
    resume_storage_dir: Path = Path(__file__).resolve().parents[3] / "work" / "resumes"
    llm_base_url: str | None = None
    llm_model: str | None = Field(default=None, max_length=150)
    llm_api_key: SecretStr | None = None
    llm_json_mode: Literal["json_object", "json_schema"] = "json_object"
    llm_thinking: Literal["enabled", "disabled"] | None = None
    llm_thinking_format: Literal["enable_thinking", "thinking"] = "enable_thinking"
    tavily_api_key: SecretStr | None = None
    llm_timeout_seconds: int = Field(default=75, ge=5, le=120)
    llm_max_tokens: int = Field(default=5500, ge=500, le=10000)
    llm_max_input_chars: int = Field(default=36000, ge=5000, le=90000)
    worker_heartbeat_max_age: int = Field(default=300, ge=30, le=900)
    worker_concurrency: int = Field(default=2, ge=1, le=4)
    llm_prices: dict[str, ModelPrice] = Field(default_factory=dict)

    @field_validator("llm_thinking", mode="before")
    @classmethod
    def empty_thinking_is_unset(cls, value):
        return None if value == "" else value

    @field_validator("llm_prices", mode="before")
    @classmethod
    def null_prices_are_unset(cls, value):
        return {} if value is None else value

    @model_validator(mode="after")
    def validate_security(self):
        if not self.db_password.get_secret_value():
            raise ValueError("DB_PASSWORD is required")
        secret = self.jwt_secret.get_secret_value()
        if len(secret.encode()) < 32 or secret.lower().startswith(("dev-", "test-", "change", "replace")):
            raise ValueError("JWT_SECRET must be an independently generated secret of at least 32 bytes")
        if self.app_env == "production" and secret.lower().startswith("local-"):
            raise ValueError("Production requires a separate JWT secret")
        if self.llm_base_url:
            endpoint = urlsplit(self.llm_base_url)
            local_http = self.app_env != "production" and endpoint.scheme == "http" and endpoint.hostname in {"127.0.0.1", "localhost", "::1"}
            if (not endpoint.hostname or endpoint.username or endpoint.password
                    or endpoint.query or endpoint.fragment or not (endpoint.scheme == "https" or local_http)):
                raise ValueError("LLM_BASE_URL must be an HTTPS API base URL")
        for origin in self.cors_origins:
            url = urlsplit(origin)
            if (not url.hostname or "*" in origin or url.username or url.password
                    or url.path or url.query or url.fragment or url.scheme not in {"http", "https"}):
                raise ValueError("CORS_ORIGINS must contain exact HTTP(S) origins")
            if self.app_env == "production" and url.scheme != "https":
                raise ValueError("Production origins must use HTTPS")
        return self

    @property
    def database_url(self) -> URL:
        return URL.create("mysql+pymysql", username=self.db_user, password=self.db_password.get_secret_value(),
                          host=self.db_host, port=self.db_port, database=self.db_name,
                          query={"charset": "utf8mb4"})

@lru_cache
def get_settings() -> Settings:
    return Settings()
