# ZeroBudget

A small, self-hostable **zero-based budgeting** web app inspired by YNAB.
Every euro gets a job: you assign incoming money to categories for each month,
and the app tells you how much is still waiting to be assigned.

> **Status:** skeleton. Accounts, categories, transactions, monthly assignments,
> the "Ready to Assign" zero-based view, and **Plaid bank linking (Sandbox,
> EUR-only)** are in place. Reports, goals, transfers, multi-currency, and the
> mobile client are intentionally out of scope for this first pass — they'll be
> added iteratively.

## Stack

- **Backend:** FastAPI, SQLAlchemy 2 (async), Alembic, Pydantic v2, JWT auth
- **Frontend:** React + TypeScript (Vite), React Router, TanStack Query, Tailwind
- **DB:** PostgreSQL in prod, SQLite for local dev without Docker
- **Prod packaging:** single multi-stage Dockerfile — FastAPI serves the built
  SPA and the `/api/*` routes from one process (easy free-tier deploy).

## Repository layout

```
backend/       FastAPI app, models, migrations, tests
frontend/      React + TS Vite app
Dockerfile     Prod image: build SPA, bundle it into the FastAPI image
docker-compose.yml   Local dev: postgres + backend (hot reload) + frontend (Vite)
fly.toml       Fly.io deployment config
```

## Quick start (Docker)

```bash
docker compose up --build
```

- Backend at http://localhost:8000 (OpenAPI docs at `/docs`)
- Frontend at http://localhost:5173 (proxies `/api` to the backend)

Register a new user on the login screen, create an account, log a positive
transaction as "inflow" (leave the category blank), and you'll see
**Ready to Assign** populated on the Budget page.

## Quick start (without Docker)

### Backend

```bash
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -e .
export DATABASE_URL="sqlite+aiosqlite:///./zerobudget.db"
export JWT_SECRET="dev-secret-change-me"
alembic upgrade head
uvicorn app.main:app --reload
```

### Frontend

```bash
cd frontend
npm install
npm run dev
```

## Running tests

```bash
cd backend
pip install -e ".[dev]"
pytest
```

The most important test is `tests/test_budget_calc.py`, which pins down the
zero-based math (Ready to Assign, category balances, month rollover).

## Deploying to Fly.io (recommended free target)

```bash
fly launch --no-deploy        # generates/uses fly.toml
fly pg create                 # create a tiny Postgres
fly pg attach <name>          # sets DATABASE_URL secret
fly secrets set JWT_SECRET="$(openssl rand -hex 32)"
fly deploy
```

Render and Railway work too — both just need `DATABASE_URL` and `JWT_SECRET`
set and the Dockerfile pointed at. Note that Render's free Postgres expires
after 30 days; Fly.io's free allowance is more durable for a personal app.

## Data model (skeleton)

- `User` — email + hashed password
- `Account` — checking / savings / cash; balance is derived from transactions
- `CategoryGroup` + `Category` — two-level budget tree
- `Transaction` — signed integer cents; `category_id` may be NULL for
  unassigned inflow (the source of "Ready to Assign")
- `MonthlyAssignment` — money assigned to a category for a given month

All amounts are stored as signed integer **cents** in EUR. Multi-currency is
deliberately deferred.

## What's next

See [ROADMAP.md](ROADMAP.md) — a phased, YNAB-referenced plan covering
transfers, payees, split transactions, auto-assign, scheduled transactions,
reports, import/bank-sync robustness, and more, ordered by priority and
written to be picked up by a coding agent one phase at a time.

## Plaid bank linking

Plaid Link is wired up in the Accounts page. It runs against **Plaid Sandbox**
and only imports EUR-denominated accounts/transactions — non-EUR data is
rejected at the boundary (ZeroBudget is EUR-only).

Set these environment variables to enable it:

| Variable | Notes |
|---|---|
| `PLAID_CLIENT_ID` | from dashboard.plaid.com |
| `PLAID_SECRET` | Sandbox secret |
| `PLAID_ENV` | `sandbox` (default) or `production` |
| `PLAID_PRODUCTS` | default `transactions` |
| `PLAID_COUNTRY_CODES` | default `IE,FR,DE,ES,NL,IT,BE,AT,PT` (EUR zone) |
| `PLAID_ENCRYPTION_KEY` | Fernet key — generate via `python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"` |

Without these set, the `Link bank account` button returns a 503. The rest of
the app works unchanged.
