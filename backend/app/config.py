"""Application configuration.

All runtime configuration is read from environment variables (see
.env.example for the full list and safe local defaults). This module is the
single place other code should read config from. There are no os.getenv()
calls scattered around the codebase.
"""
from enum import Enum
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class ScannerMode(str, Enum):
    MOCK = "mock"
    REAL = "real"


class LLMMode(str, Enum):
    MOCK = "mock"
    SELF_HOSTED = "self_hosted"
    CLAUDE = "claude"


class NotificationMode(str, Enum):
    DEV_CONSOLE = "dev_console"
    SMTP = "smtp"
    SMS_PUSH = "sms_push"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=True,
    )

    # ---- General ----
    ENVIRONMENT: str = "development"
    DEBUG: bool = True
    PROJECT_NAME: str = "SentinelX"

    # ---- Database ----
    DATABASE_URL: str

    # ---- pgcrypto ----
    PGCRYPTO_KEY: str

    # ---- Redis / Celery ----
    REDIS_URL: str = "redis://redis:6379/0"
    CELERY_BROKER_URL: str = "redis://redis:6379/0"
    CELERY_RESULT_BACKEND: str = "redis://redis:6379/1"

    # ---- Auth / JWT ----
    JWT_SECRET_KEY: str
    JWT_ALGORITHM: str = "HS256"
    JWT_ACCESS_TOKEN_EXPIRE_MINUTES: int = 60
    JWT_REFRESH_TOKEN_EXPIRE_MINUTES: int = 1440

    # ---- CORS ----
    CORS_ALLOWED_ORIGINS: str = "http://localhost:5173,http://localhost:3000"

    @property
    def cors_origins_list(self) -> list[str]:
        return [origin.strip() for origin in self.CORS_ALLOWED_ORIGINS.split(",") if origin.strip()]

    # ---- Scanner Adapters ----
    SCANNER_MODE: ScannerMode = ScannerMode.MOCK
    NUCLEI_BINARY_PATH: str = "/usr/local/bin/nuclei"
    ZAP_API_URL: str = "http://zap:8080"
    ZAP_API_KEY: str = "changeme"
    NMAP_BINARY_PATH: str = "/usr/bin/nmap"
    SCANNER_TIMEOUT_SECONDS: int = 120
    SCANNER_MAX_RETRIES: int = 2

    # Mock scanner only. How many "Mark as fixed" submissions a ticket needs
    # before the mock scanner stops reporting its endpoint. 1 means the first
    # fix passes verification. 2 means the first fix fails and the second passes.
    MOCK_FIXES_REQUIRED: int = 1

    # ---- LLM Providers ----
    # Early agents (Recon, Mapping, Assessment, Validation) operate on raw
    # live-target data and must never be set to `claude`. This is enforced
    # in app/llm/__init__.py's provider factory, not just documented here.
    EARLY_AGENT_LLM_MODE: LLMMode = LLMMode.MOCK
    LATE_AGENT_LLM_MODE: LLMMode = LLMMode.MOCK

    SELF_HOSTED_LLM_BASE_URL: str = "http://vllm:8000/v1"
    SELF_HOSTED_LLM_MODEL_NAME: str = "Qwen2.5-7B-Instruct"
    SELF_HOSTED_LLM_API_KEY: str = "not_required_locally"

    ANTHROPIC_API_KEY: str = ""
    ANTHROPIC_MODEL_NAME: str = "claude-sonnet-4-6"

    LLM_REQUEST_TIMEOUT_SECONDS: int = 60

    # ---- Notifications ----
    NOTIFICATION_MODE: NotificationMode = NotificationMode.DEV_CONSOLE

    SMTP_HOST: str = ""
    SMTP_PORT: int = 587
    SMTP_USERNAME: str = ""
    SMTP_PASSWORD: str = ""
    SMTP_FROM_ADDRESS: str = "alerts@sentinelx.local"
    SMTP_USE_TLS: bool = True

    SMS_PUSH_PROVIDER_API_URL: str = ""
    SMS_PUSH_PROVIDER_API_KEY: str = ""

    # ---- SLA Defaults (days), used only to seed the department SLA config ----
    SLA_CRITICAL_DAYS: int = 3
    SLA_HIGH_DAYS: int = 7
    SLA_MEDIUM_DAYS: int = 15
    SLA_LOW_DAYS: int = 30

    # ---- Target Safety ----
    RESTRICTED_DOMAIN_SUFFIXES: str = ".gov.in"

    @property
    def restricted_domain_suffixes_list(self) -> list[str]:
        return [s.strip() for s in self.RESTRICTED_DOMAIN_SUFFIXES.split(",") if s.strip()]

    # ---- Frontend (read here too so backend tests can check consistency) ----
    VITE_API_BASE_URL: str = "http://localhost:8000/api/v1"


@lru_cache
def get_settings() -> Settings:
    """Cached settings singleton. The environment is read once per process."""
    return Settings()


settings = get_settings()