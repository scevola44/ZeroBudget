# Phase 0 implementation plan — Backend prep & shared core extraction

The detailed plan for [`MOBILE_ROADMAP.md`](./MOBILE_ROADMAP.md) Phase 0.
`MOBILE_ROADMAP.md` deliberately stops at "what, why, and roughly how big";
this file is the screen-list-and-acceptance-criteria level, in the shape
[`ROADMAP.md`](./ROADMAP.md) uses for backend phases.

**Goal**: settle the auth contract and the API contract, and carve out
`packages/core`, before any mobile code exists.

**Why first**: getting auth and the API contract right up front avoids rework
across every later screen. This is also the *only* phase that touches the web
app, so it should land cleanly and early rather than trickling in alongside
mobile work.

**Nothing in this phase creates `mobile/`.** At the end of Phase 0 the
repository is a monorepo with a shared core and a hardened auth flow, and the
web app behaves exactly as it does today.

---

## Current state, verified against `a8854ca`

The roadmap's Phase 0 was written at the roadmap level; these are the numbers
the plan below is actually sized against.

| Area | Today |
|---|---|
| `backend/app/security.py` | 52 lines. One `create_access_token`; TTL is `settings.jwt_expire_minutes` = `60 * 24 * 7`. No refresh, no rotation, no revocation, no token type claim. |
| `backend/app/routers/auth.py` | `register`, `login`, `me`. Both token-issuing routes return `TokenResponse{access_token, token_type}`. |
| OpenAPI coverage | 44 of 54 routes declare a `response_model`. The other 10 are all `204 No Content` — so the schema already covers the entire response surface, and codegen has nothing to guess at. |
| `frontend/src/api/types.ts` | 285 hand-written lines, imported by **31 files**. Its own header says "later we can codegen from the OpenAPI schema". |
| `frontend/src/api/banking.ts` | 8 *more* hand-written response types (`Aspsp`, `BankConnection`, `SyncStatus`, …) mirroring `backend/app/schemas/banking.py`. The roadmap counts 285 lines of hand-maintained mirror; the real number is higher. |
| `frontend/src/api/client.ts` | 60 lines. Relative `fetch(path)`, `localStorage` under `zerobudget.token`, drops the token on any 401. Imported by **19 files**. |
| `frontend/src/lib/` | 9 portable domain modules (~245 lines) with 4 Vitest suites, plus `chartColors.ts`/`scopeColors.ts` (+2 suites) which stay. ~37 import sites. |
| YNAB parsers | `parseCsvLine` is defined **twice**, byte-identical (30 lines each), in `YnabImportModal.tsx` and `YnabTransactionImportModal.tsx`. |
| Browser globals below the UI | Exactly three, all in `client.ts` (`localStorage`). Nothing in `lib/` or the other `api/` modules touches `window`, `document` or `import.meta`. The "platform-free today" claim holds. |

### ❗️Where the roadmap overstates the win

`MOBILE_ROADMAP.md` lists "**TanStack Query keys and hooks** — … the whole
server-state layer is shared, not reimplemented" as a Phase 0 deliverable and
calls it "the single largest win". **There is no server-state layer to move.**

- 36 raw `api<T>()` calls sit inline in 13 page and component files.
- Query keys are string literals (`["budget"]`, `["accounts"]`,
  `["category-groups"]`, `["transactions"]`, `["insights"]`) repeated across
  files, invalidated by hand at ~25 call sites.
- `useScopes.ts` is the only extracted hook in the repository.

Extracting "the layer" therefore means *writing* it and refactoring the five
largest files in the app — `AccountsPage.tsx`, `CategoriesPage.tsx`,
`AccountDetailPage.tsx`, `TransactionsPage.tsx`, `SettingsPage.tsx`, ~2.5k
lines between them. That is a semantic rewrite of the working web app, which
contradicts both "land cleanly and early" and the phase's own acceptance
criterion that the web app be **unchanged in behavior**.

**Settled** (see *Decisions settled for this phase*): Phase 0 ships a typed
query-**key factory** and moves the one hook that already exists. The
per-resource hooks are extracted lazily, one resource at a time, as Phases 2–5
actually need them, and swept up in the new
[Phase 5.5](./MOBILE_ROADMAP.md#phase-55--shared-server-state-layer-finish-the-extraction).

---

## Work item 1 — Backend: refresh-token flow

**Model: stateless rotating refresh JWTs.** No new table, no migration. A
second JWT, rotated on every use, distinguished from an access token by a
`typ` claim. Chosen for size; the cost is stated plainly below and closed by
[Phase 1.5](./MOBILE_ROADMAP.md#phase-15--refresh-token-hardening-stored-tokens-revocation).

### `backend/app/config.py`

```python
jwt_expire_minutes: int = 30          # was 60 * 24 * 7 — now the ACCESS TTL
jwt_refresh_expire_days: int = 60     # new
```

The setting keeps its name on purpose. It is env-driven (`JWT_EXPIRE_MINUTES`)
and there is a deployed instance; renaming it would silently fall back to the
default for anyone who had set it. Only the default value and the meaning
change, and both are documented in `README.md`.

### `backend/app/security.py`

- `create_access_token(user_id)` — adds `"typ": "access"`, TTL
  `jwt_expire_minutes`.
- `create_refresh_token(user_id)` — `"typ": "refresh"`, TTL
  `jwt_refresh_expire_days`, plus a `jti` (`uuid4`). The `jti` is unused by
  the stateless flow; it is there so Phase 1.5 can start storing hashes
  without re-issuing every live token.
- `decode_access_token(token)` — **must reject `typ != "access"`.** Without
  this the 60-day refresh token is also a 60-day bearer credential and the
  entire change is cosmetic. This is the one non-obvious correctness rule in
  the work item.
- `decode_refresh_token(token)` — the mirror: rejects anything whose `typ` is
  not `"refresh"`, so an access token cannot be spent at `/refresh`.

Both raise `jwt.InvalidTokenError` so `app/deps.py` needs no change beyond
what it already catches.

### `backend/app/schemas/auth.py`

`TokenResponse` gains `refresh_token: str`. The model name is unchanged and
`/refresh` returns the same model — one shape for all three routes. Adding a
field is backwards-compatible for today's web client, which lets PR 1 merge
and release on its own.

New `RefreshRequest{refresh_token: str}` — the token travels in the body, not
a header, so it is never confused with a bearer credential in logs or
middleware.

### `backend/app/routers/auth.py`

- `POST /api/auth/register` / `POST /api/auth/login` — return both tokens.
- `POST /api/auth/refresh` — decode, **load the user** (a deleted account must
  not keep minting tokens, matching `get_current_user`), return a *new* pair.
  401 on anything invalid.
- **No `POST /api/auth/logout`.** A stateless refresh token cannot be revoked,
  so an endpoint claiming to log you out would be a lie. The client discards
  its tokens; the server-side counterpart arrives in Phase 1.5.

### Accepted cost, stated up front

The presented refresh token stays cryptographically valid until its `exp`
even after rotation. Losing a phone means the credential is live for up to 60
days with no way to kill it, and a replayed old token is indistinguishable
from a legitimate one. This is the reason Phase 1.5 exists and the reason it
must not slip past Phase 7 (TestFlight).

**One-time forced logout on deploy.** Tokens issued before this change carry
no `typ` claim and will be rejected. Every logged-in web session logs out
once. Accepted rather than adding a grace period — one relog for a
single-user app is not worth the compatibility branch.

### Tests — `backend/tests/test_auth.py`

The file's own docstring says it pins the error paths; these follow that.

1. `login` and `register` each return a usable access token **and** a refresh
   token.
2. `refresh` returns a new pair; the new access token works on `/me`.
3. `refresh` returns a refresh token *different* from the one presented
   (rotation actually happens).
4. A refresh token presented as `Authorization: Bearer` on `/me` → 401.
5. An access token posted to `/refresh` → 401.
6. Garbage and structurally-valid-but-wrongly-signed tokens on `/refresh` → 401.
7. An expired refresh token → 401 (sign one directly with a past `exp`).
8. `refresh` for a user id that no longer exists → 401.
9. Claim shape: decode both tokens and assert `exp - iat` is 30 minutes and 60
   days respectively, and that `typ` is present. Pins the config change so a
   future edit to `jwt_expire_minutes` can't silently restore week-long access
   tokens.

---

## Work item 2 — Backend: OpenAPI as the contract

### Generation, offline

`backend/scripts/dump_openapi.py` imports `app.main:app` and writes
`app.openapi()` as JSON. **No running server** — `Settings` has a default for
every field, so a bare import boots. This matters because the CI drift job
must not depend on a live backend.

`openapi.json` is a build intermediate and is **not committed** (it would
churn on `info.version`, which differs between an editable install and CI).
Only the generated TypeScript is committed.

### The generated artifact

`packages/core/src/api/schema.ts`, produced by `openapi-typescript`, committed,
with a generated-file header.

### The alias layer — why the swap is not one-for-one

`openapi-typescript` emits `components["schemas"]["AccountResponse"]`. The app
imports `Account`, `Transaction`, `BudgetMonth` and ~25 other friendly names
across 31 files. Renaming all of them would bury the interesting part of the
diff.

So `packages/core/src/api/types.ts` is hand-written and thin:

```ts
import type { components } from "./schema";

export type Account = components["schemas"]["AccountResponse"];
export type Transaction = components["schemas"]["TransactionResponse"];
// …
```

Every call site keeps its import *names* and changes only the import *path*.
`banking.ts`'s 8 local response types are deleted and re-exported from here
the same way.

### Two things that do not survive codegen unchanged

1. **`AccountType`.** `types.ts` has
   `"checking" | "savings" | … | string`; `AccountResponse.type` is a plain
   `str` with `max_length=32`. ❗️Do **not** "fix" this by making the Pydantic
   field a `Literal` — the backend genuinely accepts any string today, and
   tightening it would reject account rows already stored with other values.
   Keep `AccountType` as a hand-written alias in `types.ts` alongside the
   generated ones, and leave the backend alone.
2. **`MANUAL_ACCOUNT_TYPES`.** A runtime array of `{value, label}` — picker
   label data, not a type. It moves to `frontend/src/lib/accountTypes.ts`
   (2 consumers: `AccountsPage.tsx`, `EditAccountModal.tsx`) and
   `frontend/src/api/types.ts` is deleted outright.

`GoalKind` and `OverspendFlag` are already `Literal` in
`backend/app/schemas/`, so their unions survive codegen intact. Verified.

### Drift check

Root script:

```
npm run codegen:api   # dump_openapi.py | openapi-typescript -o packages/core/src/api/schema.ts
```

New `contract` job in `.github/workflows/ci.yml`: setup-python + setup-node,
install the backend, regenerate, then `git diff --exit-code
packages/core/src/api/schema.ts`. **Verify the job actually fails** by editing
a Pydantic schema without regenerating — a drift check that can't go red is
worse than none.

The same job carries a one-line guard that is cheap and protects the whole
point of the package:

```
! grep -rn "localStorage\|sessionStorage\|window\.\|document\.\|import\.meta" packages/core/src
```

---

## Work item 3 — Monorepo conversion and core extraction

### Layout

```
package.json          root — private, npm workspaces ["frontend", "packages/*"]
package-lock.json     moved here from frontend/
packages/core/        @zerobudget/core
frontend/             unchanged path
```

### `packages/core` is source-only — no build step

```json
{
  "name": "@zerobudget/core",
  "private": true,
  "type": "module",
  "exports": { ".": "./src/index.ts" },
  "peerDependencies": {
    "@tanstack/react-query": "^5.59.0",
    "react": "^18.3.1"
  }
}
```

Vite, Vitest and Metro all transpile TypeScript from a workspace symlink. A
`dist/` would add build ordering to the Dockerfile and to CI for no benefit,
and would be one more thing to get stale. Type-checking still uses project
references as the roadmap decided: core is `composite: true` +
`emitDeclarationOnly: true` → `dist/types` (gitignored), and
`frontend/tsconfig.json` gains `"references": [{ "path": "../packages/core" }]`.
`composite` cannot be combined with `noEmit`, which is why it is
declaration-only rather than no-emit.

### What moves

| From | To |
|---|---|
| `frontend/src/api/client.ts` | `packages/core/src/api/client.ts` (+ seams, work item 4) |
| `frontend/src/api/{budget,banking,payees,scopes}.ts` | `packages/core/src/api/` |
| `frontend/src/api/types.ts` | deleted — see work item 2 |
| `frontend/src/lib/{money,dates,goal,insightsRange,budgetAvailability,splitRemaining,categorySuggestions,transferOption,readyToAssignOption}.ts` + their 4 `.test.ts` | `packages/core/src/domain/` |
| `parseYnabCsv` / `buildPreview` from `YnabImportModal.tsx` | `packages/core/src/import/ynab/categories.ts` |
| `parseYnabTransactionCsv` / `parseCurrencyToCents` / `parseYnabDate` from `YnabTransactionImportModal.tsx` | `packages/core/src/import/ynab/transactions.ts` |
| both copies of `parseCsvLine` | `packages/core/src/import/ynab/csv.ts` — **one** copy; they are byte-identical, so this is deduplication, not premature abstraction |
| `frontend/src/lib/useScopes.ts` | `packages/core/src/query/useScopes.ts` |

New in core: `packages/core/src/query/keys.ts` — a typed key factory replacing
the string literals, e.g.

```ts
export const queryKeys = {
  scopes: () => ["scopes"] as const,
  accounts: () => ["accounts"] as const,
  budget: (month?: string) => (month ? ["budget", month] : ["budget"]) as const,
  // …
};
```

The ~25 hand-written `invalidateQueries({ queryKey: [...] })` call sites switch
to it. This is the whole of the Phase 0 query work: **no `useQuery` call moves
out of a page.**

### What stays in `frontend/`

`chartColors.ts` and `scopeColors.ts` (+ their suites) — Tailwind class-pair
strings validated against the web's white/`stone-900` surfaces, per the
roadmap. `useDebouncedValue.ts` — portable, but nothing needs it yet (YAGNI).

### Scale of the diff

~50 files change import paths. The move itself is mechanical; the risk is
entirely in the five migration hazards below, not in the moved code.

### Test wiring

Core gets its own Vitest config. Root `npm test` runs both workspaces: 4
suites in core (money, dates, insightsRange, splitRemaining), 2 in frontend
(chartColors, scopeColors). The moved suites must pass **unmodified** — if one
needs editing to survive the move, something non-portable came with it.

---

## Work item 4 — Configurable base URL, injectable token storage, refresh retry

### The two seams

```ts
// packages/core/src/api/client.ts
export type StoredTokens = { accessToken: string; refreshToken: string };

export type TokenStorage = {
  load(): Promise<StoredTokens | null>;
  save(tokens: StoredTokens | null): Promise<void>;
};

export function configureApi(options: { baseUrl: string; storage: TokenStorage }): void;
export async function hydrateTokens(): Promise<void>;
```

**Tokens are cached in memory; the storage is only for persistence and
startup hydration.** Both platforms need this, for different reasons: web's
`AuthContext` initializes `loading` from a *synchronous* `getToken()` (line 18
of `AuthContext.tsx`), so an async-only read would change first-paint
behavior; and `expo-secure-store` is async, so mobile must not await storage
on every request. One in-memory cache satisfies both and keeps `getToken()`
synchronous.

`baseUrl` is a plain prefix. **Web passes `""`**, so paths stay exactly
`/api/auth/login` as they are today — the Vite dev proxy and the same-origin
production mount are untouched. Mobile passes `https://host`. The roadmap's
note holds: React Native's `fetch` doesn't enforce CORS, so
`settings.cors_origin_list` is not the blocker; the blocker was only that
`frontend/` assumed same-origin.

Web adapter: `frontend/src/api/storage.ts` over `localStorage`, keys
`zerobudget.token` (unchanged, so existing sessions survive the storage
refactor even though work item 1 invalidates the tokens themselves) and
`zerobudget.refresh_token`.

### 401 → refresh → retry

Pulled forward from `MOBILE_ROADMAP.md` **Phase 1, work item 4**, because
otherwise the refresh endpoint ships with no client exercising it and stays
untested until a mobile screen finds the bug. Including it here means Phase 1
gets it for free and the web app stops logging users out weekly — the same
user-visible payoff, one phase earlier.

- One in-flight refresh promise shared by all concurrent 401s (N parallel
  queries must not fire N rotations — with rotation, the losers' tokens would
  already be superseded).
- Retry the original request **once**. A 401 on the retry, or a failed
  refresh, clears both tokens and throws `ApiError(401)` — today's behavior,
  so `AuthContext`'s existing recovery path is unchanged.
- `/api/auth/refresh` itself is exempt from the interceptor.

---

## Work item 5 — Migration hazards

The roadmap lists three. All three are confirmed; **two more exist**, and one
of them is named in the phase's own acceptance criteria.

1. **`Dockerfile`** (roadmap #1, confirmed). Stage 1 copies only
   `frontend/package.json` + `frontend/package-lock.json` and runs
   `npm install` in `frontend/`. Becomes: copy the root manifest and lockfile
   plus both workspace manifests, `npm ci` at root, then sources, then
   `npm run build -w zerobudget-frontend`. Note the `npm install` → `npm ci`
   change — there is a root lockfile now, and the image should honor it.
2. **`.github/workflows/ci.yml`** (roadmap #2, confirmed). The `frontend` job
   uses `working-directory: frontend` and
   `cache-dependency-path: frontend/package-lock.json`; `npm ci` fails the
   moment the lockfile moves. Drop the working-directory, point the cache at
   the root lockfile, run `npm test` and `npm run build` at root. Add the
   `contract` job from work item 2. **No `mobile` job yet** — the roadmap
   folds one in here, but `mobile/` doesn't exist until Phase 1, so it lands
   there.
3. **`release-please-config.json`** (roadmap #3, confirmed). Two `extra-files`
   entries point at `frontend/package-lock.json` with `$.version` and
   `$.packages[''].version`, neither of which resolves after the move.
   Replace with the root `package-lock.json` and `$.packages['frontend']
   .version`, and add `packages/core/package.json` `$.version` +
   `$.packages['packages/core'].version`. ❗️Leave the **root** `package.json`
   without a `version` field and do not reference `$.packages[''].version` —
   release-please fails on a JSONPath that doesn't resolve. Inspect the
   generated lockfile before finalizing this file; the exact `packages` keys
   are npm's to decide, not ours to guess.
4. **`docker-compose.yml`** — *not in the roadmap's list.* The `frontend`
   service mounts `./frontend:/app` and runs `npm install && npm run dev`.
   After conversion that directory has no lockfile and `packages/core` is
   outside the mount, so dev compose breaks. The phase's acceptance criteria
   name `docker compose up --build` explicitly, so this is not optional. Fix:
   mount `.:/app`, keep `working_dir: /app`, run
   `npm install && npm run dev -w zerobudget-frontend -- --host 0.0.0.0`.
5. **`README.md`** — *not in the roadmap's list.* Lines 85–87 tell a
   contributor to `cd frontend && npm install && npm run dev`. Update to the
   root workspace commands, and document `npm run codegen:api` and the new
   auth env vars.

Plus `.gitignore`: add `packages/core/dist/`.

**All five must land in the same PR as the conversion.** Any one of them left
behind turns CI or the image build red.

### Deferred, correctly

The roadmap's hazards #4 (`Intl` on Hermes) and #5 (Metro `watchFolders` /
`nodeModulesPaths`) stay in Phase 1 — both are properties of the Expo app,
and neither can be verified before `mobile/` exists.

---

## Sequencing

Four PRs, all targeting `develop`, all Conventional Commit titles.

| # | Title | Contents |
|---|---|---|
| 1 | `feat(auth): issue and rotate refresh tokens` | Work item 1. Backend only. The web client ignores the new field, so this merges and releases on its own. |
| 2 | `refactor: convert to npm workspaces and extract @zerobudget/core` | Work items 3 and 5. Purely mechanical — **no semantic change**, so a bisect through it stays meaningful. The five hazards ride along. |
| 3 | `feat(core): generate API types from the OpenAPI schema` | Work item 2. Rides on top of 2 because the generated file lands in core; generating into `frontend/` first and then moving it doubles the churn. |
| 4 | `feat(core): configurable base URL and refresh-aware API client` | Work item 4. Needs both 1 and 2. |

PR 2 is the risky one and is deliberately the boring one.

---

## Acceptance criteria

Derived from `MOBILE_ROADMAP.md` Phase 0, made checkable.

**Auth**
- `pytest` green, including the 9 new cases in `test_auth.py`.
- A refresh token presented as a bearer credential is rejected — pinned by a
  test, not by inspection.
- Access-token TTL is 30 minutes and refresh-token TTL is 60 days, pinned by
  the claim-shape test.

**Shared core**
- The web app builds, tests and deploys **unchanged in behavior** while
  importing types, client and domain logic from `@zerobudget/core`.
  Verified by: `npm test` and `npm run build` green at root, plus a manual
  pass over login → budget → transactions → categories → insights → settings,
  and a hard refresh confirming the session resumes.
- The 4 moved Vitest suites pass **unmodified**.
- `grep -rn "localStorage\|window\.\|document\.\|import\.meta" packages/core/src`
  returns nothing.
- `frontend/src/api/types.ts` and the duplicate `parseCsvLine` are gone.

**Contract**
- `npm run codegen:api` is idempotent — running it on a clean tree produces no
  diff.
- The `contract` CI job goes **red** when a Pydantic schema changes without
  regeneration. Demonstrated once, deliberately, before the PR is called done.

**Build and release**
- `docker compose up --build` brings up db + backend + Vite dev server.
- The GHCR image builds from the repository-root context and serves the SPA.
- Every `release-please-config.json` `extra-files` JSONPath resolves against
  the post-conversion tree.

---

## Explicitly out of scope for Phase 0

- No `mobile/` directory, no Expo, no NativeWind, no Metro config — Phase 1.
- No per-resource query-hook extraction and no refactor of the five large
  pages — [Phase 5.5](./MOBILE_ROADMAP.md#phase-55--shared-server-state-layer-finish-the-extraction).
- No token storage, revocation, logout endpoint or per-device sessions —
  [Phase 1.5](./MOBILE_ROADMAP.md#phase-15--refresh-token-hardening-stored-tokens-revocation).
- No `Intl`/Hermes work, no Metro workspace resolution — Phase 1.
- No `react-native-web` rewrite of `frontend/` — a standing non-goal.
- No `mobile` CI job — nothing to build yet.

---

## Decisions settled for this phase

| Question | Choice | Consequence |
|---|---|---|
| How much of the query layer moves in Phase 0? | Types, client, `api/*` modules, all of portable `lib/`, both YNAB parsers, a typed key factory, and `useScopes` — the one hook that already exists. Inline `useQuery` calls stay put. | Keeps "web app unchanged in behavior" true. The rest becomes Phase 5.5, extracted lazily as Phases 2–5 need each resource. |
| Refresh-token model | Stateless rotating JWT with a `typ` claim. No table, no migration. | Smallest change that unblocks a native app. No revocation: a stolen refresh token lives until `exp`. Phase 1.5 closes it. |
| Where the refresh token lives on web | `localStorage`, alongside the access token. | One code path in the shared client; no CSRF or cross-origin cookie work. Honest cost: an XSS on the SPA yields a 60-day credential rather than a 30-minute one. |
| `packages/core` build strategy | Source-only (`exports` → `src/index.ts`); project references emit declarations only. | No build ordering in Docker or CI, no `dist/` to go stale. Requires every consumer to be a TS-capable bundler — Vite, Vitest and Metro all are. |
| Base URL seam | Plain prefix, `""` on web. | Zero change to the web app's request paths, the Vite proxy, or the production same-origin mount. |
| 401 → refresh → retry | Pulled forward from Phase 1 work item 4. | The refresh endpoint ships with a real client exercising it; Phase 1 inherits it working. |
