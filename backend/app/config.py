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

    # Plaid integration. Sandbox-only in MVP; set real credentials in .env.
    # Empty defaults let the app boot and tests run; the PlaidClient raises
    # on first use if credentials or encryption key are missing.
    plaid_client_id: str = ""
    plaid_secret: str = ""
    plaid_env: str = "sandbox"
    plaid_products: str = "transactions"
    # EUR-zone defaults. GB is intentionally excluded (uses GBP, and
    # ZeroBudget is EUR-only for now).
    plaid_country_codes: str = "IE,FR,DE,ES,NL,IT,BE,AT,PT"
    # Fernet key (base64). Generate with:
    #   python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
    plaid_encryption_key: str = ""

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def plaid_products_list(self) -> list[str]:
        return [p.strip() for p in self.plaid_products.split(",") if p.strip()]

    @property
    def plaid_country_codes_list(self) -> list[str]:
        return [c.strip() for c in self.plaid_country_codes.split(",") if c.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
