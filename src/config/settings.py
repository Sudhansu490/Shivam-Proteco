"""Environment-based settings. Loads .env when python-dotenv is available."""
from __future__ import annotations

import os
from dataclasses import dataclass, field

try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    pass  # .env loading is best-effort; plain env vars still work


def _getenv(name: str, default: str = "") -> str:
    return os.getenv(name, default)


@dataclass
class Settings:
    llm_provider: str = field(default_factory=lambda: _getenv("LLM_PROVIDER", "none").lower() or "none")
    groq_api_key: str = field(default_factory=lambda: _getenv("GROQ_API_KEY", ""))
    groq_model: str = field(default_factory=lambda: _getenv("GROQ_MODEL", "llama-3.1-8b-instant"))
    database_url: str = field(default_factory=lambda: _getenv("DATABASE_URL", "sqlite:///data/quality.db"))
    chroma_dir: str = field(default_factory=lambda: _getenv("CHROMA_DIR", "data/chroma"))
    api_host: str = field(default_factory=lambda: _getenv("API_HOST", "127.0.0.1"))
    api_port: int = field(default_factory=lambda: int(_getenv("API_PORT", "8000") or 8000))
    max_workflow_retries: int = field(default_factory=lambda: int(_getenv("MAX_WORKFLOW_RETRIES", "3") or 3))
    csv_path: str = field(default_factory=lambda: _getenv("CSV_PATH", "data/quality_batches.csv"))
    limits_path: str = field(default_factory=lambda: _getenv("LIMITS_PATH", "config/demo_quality_limits.yaml"))
    sops_dir: str = field(default_factory=lambda: _getenv("SOPS_DIR", "data/sops"))

    @property
    def has_database(self) -> bool:
        return bool(self.database_url)

    @property
    def has_llm(self) -> bool:
        return self.llm_provider == "groq" and bool(self.groq_api_key)


def get_settings() -> Settings:
    return Settings()
