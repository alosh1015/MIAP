from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

REPO_ROOT = Path(__file__).resolve().parents[3]
BACKEND_DIR = REPO_ROOT / "backend"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="MIAP_",
        env_file=str(BACKEND_DIR / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    env: str = "development"
    secret_key: str = "dev-only-change-me"
    data_dir: Path = REPO_ROOT / "data"
    database_path: Path = REPO_ROOT / "data" / "miap.db"
    jwt_ttl_minutes: int = 480
    upload_max_bytes: int = 524_288_000
    model_backend: str = "stub"
    model_device: str = "cpu"
    model_dir: Path = REPO_ROOT / "ml" / "weights"
    registry_path: Path = REPO_ROOT / "ml" / "registry.json"
    migrations_dir: Path = REPO_ROOT / "migrations"
    cors_origins: str = "http://localhost:5173"
    pii_key: str = ""
    pii_index_key: str = ""
    pii_key_version: int = 1
    pii_keys: str = "{}"

    @model_validator(mode="after")
    def _resolve_relative_paths(self) -> "Settings":
        # Paths in backend/.env are written relative to the backend directory, so
        # resolve them there rather than against whatever directory launched the process.
        for name in ("data_dir", "database_path", "model_dir", "registry_path", "migrations_dir"):
            value: Path = getattr(self, name)
            if not value.is_absolute():
                setattr(self, name, (BACKEND_DIR / value).resolve())
        return self

    @property
    def blob_dir(self) -> Path:
        return self.data_dir / "blobs" / "sha256"

    @property
    def derived_dir(self) -> Path:
        return self.data_dir / "derived"

    @property
    def report_dir(self) -> Path:
        return self.data_dir / "reports"

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
