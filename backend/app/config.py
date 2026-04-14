from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime configuration, populated from environment variables / .env."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # SQLAlchemy URL. Defaults to local SQLite so a fresh clone runs zero-config.
    database_url: str = "sqlite+aiosqlite:///./zerobudget.db"

    # JWT signing. Override in prod via env var.
    jwt_secret: str = "dev-secret-change-me"
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 60 * 24 * 7  # one week

    # Where the built SPA lives when running the production image.
    # Unset/empty in dev: the frontend is served by Vite instead.
    static_dir: str = ""

    # CORS origins for local dev (Vite runs on 5173).
    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173"

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
