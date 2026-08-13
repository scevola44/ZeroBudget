from functools import lru_cache
from pathlib import Path

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

    # Enable Banking (PSD2) integration. Register an application in the
    # Enable Banking control panel to obtain the app id and RS256 key pair.
    # Empty defaults let the app boot and tests run; the BankingClient raises
    # on first use if credentials or encryption key are missing.
    enable_banking_app_id: str = ""
    # Private key: either a path to the PEM file (docker-secret friendly,
    # takes precedence) or the PEM content inline.
    enable_banking_private_key_path: str = ""
    enable_banking_private_key: str = ""
    enable_banking_api_base: str = "https://api.enablebanking.com"
    # Must match a redirect URL registered for the app in the EB control
    # panel, e.g. http://localhost:5173/banking/callback
    enable_banking_redirect_url: str = ""
    # ASPSP-list filter. EUR-zone defaults; FI included so the sandbox
    # "Mock ASPSP" shows up. GB intentionally excluded (GBP; EUR-only app).
    banking_countries: str = "IE,FR,DE,ES,NL,IT,BE,AT,PT,FI"
    # Fernet key (base64) for encrypting Enable Banking session ids at rest.
    # Generate with:
    #   python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
    bank_encryption_key: str = ""

    # Transaction sync. Enable Banking's free tier caps API usage, so sync
    # runs are globally quota'd: at most SYNC_MAX_PER_DAY runs per UTC day.
    # "auto" spaces runs evenly (every 24h / SYNC_MAX_PER_DAY) via the
    # in-process scheduler; "manual" leaves runs to the user, same daily cap.
    sync_mode: str = "manual"
    sync_max_per_day: int = 4
    # Re-fetch window in days for a non-first sync (EB has no delta API; we
    # re-fetch a window and dedup). A first sync instead fetches month-to-date
    # (see ``bank_sync.sync_connection``) so a newly linked account starts
    # clean at the current budget month rather than importing months of
    # already-elapsed history to categorize.
    sync_fetch_days: int = 14

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def banking_countries_list(self) -> list[str]:
        return [c.strip().upper() for c in self.banking_countries.split(",") if c.strip()]

    @property
    def enable_banking_private_key_pem(self) -> str:
        """PEM content, from path (preferred) or inline value. Empty if unset."""
        if self.enable_banking_private_key_path:
            return Path(self.enable_banking_private_key_path).read_text()
        return self.enable_banking_private_key


@lru_cache
def get_settings() -> Settings:
    return Settings()
