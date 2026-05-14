import os
from contextlib import asynccontextmanager
from importlib.metadata import version as pkg_version, PackageNotFoundError
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.config import get_settings
from app.db import Base, engine
from app.models import *  # noqa: F401,F403 — register models on Base.metadata
from app.routers import accounts, auth, budget, categories, plaid, transactions

settings = get_settings()


def get_app_version() -> str:
    try:
        return pkg_version("zerobudget-backend")
    except PackageNotFoundError:
        # Fallback for development when package isn't installed in editable mode
        # Read from pyproject.toml
        pyproject_path = Path(__file__).parent.parent.parent / "backend" / "pyproject.toml"
        if pyproject_path.exists():
            with open(pyproject_path) as f:
                for line in f:
                    if line.startswith("version ="):
                        return line.split('"')[1]
        return "0.0.0"


@asynccontextmanager
async def lifespan(app: FastAPI):
    # In dev / tests we create tables directly. Alembic owns the schema in prod,
    # but create_all is a no-op when every table already exists, so running it
    # unconditionally is safe and keeps first-run UX painless.
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield


app = FastAPI(title="ZeroBudget", version=get_app_version(), lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(accounts.router)
app.include_router(categories.router)
app.include_router(transactions.router)
app.include_router(budget.router)
app.include_router(plaid.router)


@app.get("/api/health", tags=["health"])
async def health() -> dict[str, str]:
    return {"status": "ok"}


# ---------------------------------------------------------------------------
# SPA static mount (production only).
#
# In prod the multi-stage Dockerfile drops the built Vite bundle into
# ``STATIC_DIR`` and sets the env var. In dev we skip this entirely and let
# Vite serve the frontend on :5173.
# ---------------------------------------------------------------------------
_static_dir = settings.static_dir or os.environ.get("STATIC_DIR", "")
if _static_dir and Path(_static_dir).is_dir():
    static_path = Path(_static_dir)
    assets_dir = static_path / "assets"
    if assets_dir.is_dir():
        app.mount("/assets", StaticFiles(directory=assets_dir), name="assets")

    @app.get("/{full_path:path}", include_in_schema=False)
    async def spa_fallback(full_path: str) -> FileResponse:
        # Anything not under /api and not a static asset falls back to index.html
        # so client-side routing (React Router) keeps working on hard refresh.
        index_file = static_path / "index.html"
        candidate = static_path / full_path
        if full_path and candidate.is_file():
            return FileResponse(candidate)
        return FileResponse(index_file)
