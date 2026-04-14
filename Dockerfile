# syntax=docker/dockerfile:1.6
# ---------------------------------------------------------------------------
# Stage 1 — build the React SPA
# ---------------------------------------------------------------------------
FROM node:20-alpine AS frontend
WORKDIR /app/frontend
COPY frontend/package.json frontend/package-lock.json* ./
RUN npm install --no-audit --no-fund
COPY frontend/ ./
RUN npm run build

# ---------------------------------------------------------------------------
# Stage 2 — FastAPI backend, bundling the built SPA as static assets
# ---------------------------------------------------------------------------
FROM python:3.12-slim AS runtime
WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    STATIC_DIR=/app/static

# Backend dependencies first — cached layer.
COPY backend/pyproject.toml ./backend/
RUN pip install --upgrade pip && pip install ./backend

# Backend source.
COPY backend/ ./backend/

# Built SPA from stage 1.
COPY --from=frontend /app/frontend/dist /app/static

WORKDIR /app/backend

EXPOSE 8000

# Alembic + uvicorn. ``sh -c`` so $PORT expands on Fly.io / Render / Railway.
CMD ["sh", "-c", "alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
