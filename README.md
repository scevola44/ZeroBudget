# ZeroBudget

A small, self-hostable **zero-based budgeting** web app inspired by YNAB.
Every euro gets a job: you assign incoming money to categories for each month,
and the app tells you how much is still waiting to be assigned.

> **Status:** beta. The zero-based core is in place and usable day-to-day.
> Transfers, payees, split transactions, scheduled transactions, and reports
> are not built yet — see [ROADMAP.md](ROADMAP.md) for the phased plan.

## Features

- **Independent budget pools per user** — every account and category group
  belongs to a *scope*, and each scope has its own Ready to Assign total. This
  replaces YNAB's multi-budget concept and is the reason this app exists:
  budgeting a joint account alongside your own money in one view. A new account
  starts with **Personal** and **Family**; add, rename and delete your own on
  the Settings page.
- **Zero-based budget page** — a Ready to Assign pill per scope, month
  navigation, collapsible category groups with Assigned/Available summaries
  and per-scope totals, inline assignment editing.
- **Goals on every category** (they're mandatory, not optional): monthly,
  yearly, or target-date, each showing a "Need X this month" hint computed
  from the goal and current balance.
- **Accounts** — manual (checking / savings / cash) or connected via
  **Enable Banking (PSD2, EUR-only)**; balances are always derived from
  transactions.
- **Transactions** — entry and inline category edits on the account page; a
  Transactions page with date/category/account filters across all accounts.
- **YNAB CSV import** — bring over your category tree and transaction history
  from a YNAB export.
- **Category management** — drag-and-drop reordering (touch included), inline
  rename, group edit/delete.
- **Responsive UI with dark mode** — usable from a phone browser; follows the
  OS theme.

## Stack

- **Backend:** FastAPI, SQLAlchemy 2 (async), Alembic, Pydantic v2, JWT auth
- **Frontend:** React + TypeScript (Vite), React Router, TanStack Query, Tailwind
- **Mobile (in progress):** Expo / React Native, Expo Router, NativeWind — see
  [`MOBILE_ROADMAP.md`](./MOBILE_ROADMAP.md)
- **DB:** PostgreSQL in prod, SQLite for local dev without Docker
- **Prod packaging:** single multi-stage Dockerfile — FastAPI serves the built
  SPA and the `/api/*` routes from one process (easy free-tier deploy).

## Repository layout

```
backend/       FastAPI app, models, migrations, tests
frontend/      React + TS Vite app
mobile/        Expo (React Native) app that connects to any ZeroBudget server
packages/core/ @zerobudget/core — API client, generated API types, domain logic
               and YNAB CSV parsers shared by every TypeScript client
package.json   npm workspaces root (frontend + mobile + packages/core)
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

The JavaScript side is an npm workspace: install once from the repo root.
React is pinned once for every workspace, by the root `package.json`
`overrides`, to the exact version the mobile app's Expo SDK requires — two
React copies in one bundle break hooks. Bump it only together with an Expo SDK
upgrade.

```bash
npm install
npm run dev -w frontend
```

### Mobile app

The Expo app lives in `mobile/` and shares `@zerobudget/core` with the web app.
On first launch it asks for your server's address (e.g. `budget.example.com`)
and checks it via `/api/health` before showing sign-in.

```bash
npm install
npm run start -w zerobudget-mobile   # scan the QR code with Expo Go, or press i for the iOS Simulator
```

A phone can't reach `localhost`: point it at your machine's LAN address
(e.g. `http://192.168.1.20:8000`, with **Allow insecure local server** switched
on, since a local backend has no TLS) and start uvicorn with `--host 0.0.0.0`.

## Running tests

```bash
cd backend
pip install -e ".[dev]"
pytest
```

```bash
npm test                                # Vitest (web, core) and Jest (mobile)
npm run typecheck -w @zerobudget/core
npm run typecheck -w zerobudget-mobile
```

The web app's API types are generated from the backend's OpenAPI schema. After
changing a route or response schema, refresh the snapshot and the types (CI
fails if either is stale):

```bash
cd backend && python -m scripts.dump_openapi
npm run gen:types -w @zerobudget/core
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

## Data model

- `User` — email + hashed password (JWT auth)
- `Scope` — an independent budget pool, named by the user. Seeded as
  `Personal` and `Family` at registration; a scope still referenced by an
  account or category group cannot be deleted
- `Account` — checking / savings / cash; belongs to a `Scope` via `scope_id`;
  balance is derived from transactions, never stored
- `CategoryGroup` + `Category` — two-level budget tree; groups carry the
  `scope_id` and categories inherit it; every category has a mandatory goal
  (`monthly`, `yearly`, or `target_date` + amount)
- `Transaction` — signed integer cents; `category_id` may be NULL for
  unassigned inflow (the source of "Ready to Assign"); carries an external
  dedup id when synced from a bank
- `MonthlyAssignment` — money assigned to a category for a given month
  (unique per user/category/month)
- `BankConnection` — an authorized bank (Enable Banking session):
  Fernet-encrypted session id, consent expiry, last-sync status
- `SyncRun` — one global sync run; the ledger behind the daily sync quota
  and the auto-sync scheduler

All amounts are stored as signed integer **cents** in EUR. Multi-currency is
deliberately deferred.

## What's next

See [ROADMAP.md](ROADMAP.md) — a phased, YNAB-referenced plan covering
transfers, payees, split transactions, auto-assign, scheduled transactions,
reports, import/bank-sync robustness, and more, ordered by priority and
written to be picked up by a coding agent one phase at a time.

For the mobile client, see [MOBILE_ROADMAP.md](MOBILE_ROADMAP.md) — a phased
plan for a React Native (Expo) app sharing a TypeScript core with the web app.
It supersedes the on-hold native-SwiftUI plan in [IOS_ROADMAP.md](IOS_ROADMAP.md).

## Enable Banking bank sync (PSD2)

Bank connections are wired up in the Accounts page via **Enable Banking**.
The flow is redirect-based PSD2 consent: pick your bank, authorize at the
bank's own site, land back on `/banking/callback`. Only EUR-denominated
accounts/transactions are imported — non-EUR data is rejected at the
boundary (ZeroBudget is EUR-only).

Set these environment variables to enable it:

| Variable | Notes |
|---|---|
| `ENABLE_BANKING_APP_ID` | application id from the [Enable Banking control panel](https://enablebanking.com/cp) |
| `ENABLE_BANKING_PRIVATE_KEY_PATH` | path to the app's RS256 private key PEM (wins over the inline var) |
| `ENABLE_BANKING_PRIVATE_KEY` | or the PEM content inline |
| `ENABLE_BANKING_REDIRECT_URL` | must match a redirect URL registered in the control panel, e.g. `http://localhost:5173/banking/callback` |
| `BANKING_COUNTRIES` | default `IE,FR,DE,ES,NL,IT,BE,AT,PT,FI` (EUR zone + FI for the sandbox Mock ASPSP) |
| `BANK_ENCRYPTION_KEY` | Fernet key — generate via `python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"` |
| `SYNC_MODE` | `manual` (default): user-triggered syncs · `auto`: in-process scheduler syncs every `24h / SYNC_MAX_PER_DAY` |
| `SYNC_MAX_PER_DAY` | default `4` — global daily cap on sync runs (Enable Banking's free tier meters API calls); one run syncs all connected banks |

Without credentials set, the `Connect bank` button returns a 503. The rest of
the app works unchanged.

The daily quota is tracked in the database (`sync_runs`), so it survives
restarts; manual syncs beyond the cap get a 429 until midnight UTC. PSD2
consents expire after up to 180 days — the Accounts page shows a Reconnect
banner when a connection needs re-authorization.
