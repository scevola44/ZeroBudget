# ZeroBudget Mobile Roadmap (React Native)

A phased plan to build a **React Native mobile client** for ZeroBudget, able to
connect to any self-hosted instance via a user-entered server URL, targeting
feature parity with the web app — and, along the way, to extract the shared
TypeScript core that makes that parity cheap to maintain.

## Purpose & how to use this document

This document is written for a **coding agent** (or human contributor) picking
up mobile work on this repository. It lives alongside
[`ROADMAP.md`](./ROADMAP.md), which tracks the backend/web app and stays
agnostic of mobile progress.

- Phases are ordered **most → least important**. Work them in order unless the
  owner says otherwise.
- Each phase is sized to be independently demoable. Do not start a phase by
  building ahead for a later one (YAGNI).
- This document intentionally stops at the "what, why, and roughly how big"
  level — it is a roadmap *of* roadmaps. When a phase is about to start, write
  it a real implementation plan (screen list, API/schema changes, acceptance
  criteria) the way `ROADMAP.md` does for backend phases.
- Items marked **[owner decision]** are open questions this document
  deliberately does not settle — raise them explicitly rather than guess.
- Keep this file updated: when a phase ships, mark it done with the version it
  shipped in, the way `ROADMAP.md` does.

## Relationship to `IOS_ROADMAP.md`

[`IOS_ROADMAP.md`](./IOS_ROADMAP.md) planned a **native SwiftUI** client and
explicitly rejected React Native. That decision was revisited before any Swift
code was written and **reversed**; the SwiftUI path is now on hold, kept as a
documented fallback rather than deleted.

What changed the answer: the deciding factor in `IOS_ROADMAP.md` was that the
backend is "a small, clean REST/JSON surface, so React Native's main edge — TS
code-sharing with `frontend/` — matters less than it looks". That understated
what is actually shareable. Beyond types, the web app already contains a
sizeable body of **platform-free TypeScript**: the money/date/goal/insights-range
domain helpers with their Vitest suites, both YNAB CSV parsers, and the entire
TanStack Query server-state layer — which runs unmodified on React Native. None
of that is portable to Swift; all of it would have been reimplemented, and every
reimplementation is a second source of truth that drifts.

The rest of `IOS_ROADMAP.md` survives the framework change intact and was
carried over here: the parity target, the phase ordering, the refresh-token
blocker, the Enable Banking redirect risk, and most of the open decisions.

## Decisions already made

| Decision | Choice | Why |
|---|---|---|
| Client architecture | **React Native via Expo** (superseding SwiftUI) | One language across every client. API types, domain logic and server-state hooks become *shared code* rather than a third hand-maintained copy. Android stops being structurally impossible. |
| Relationship to the web app | **Add alongside; extract a shared core.** Do not rewrite `frontend/` | The web SPA is shipped and used day-to-day. Rewriting ~10.4k lines into react-native-web would pause web feature work to regress a working app for an unvalidated platform. Growing `mobile/` screen-by-screen against a shared core risks nothing and keeps convergence available later. |
| Android | **iOS-first; Android kept configured and compiling in CI** | Cheap insurance that iOS-only APIs don't quietly leak in, without doubling device QA. Not tested on real hardware or released until iOS reaches parity. |
| Styling | **NativeWind v4** | The web app is 100% Tailwind utility classes with `dark:` variants, so `className` strings port near-verbatim and the design language stays one thing. Also the only option that keeps *component* sharing plausible later. Traded off knowingly: a Babel/Metro transform and a third-party layer with a history of version churn. |
| Toolchain | **Expo (managed, with dev builds) + Expo Router** | EAS Build removes the need for a local Xcode/macOS in CI. `expo-secure-store`, `expo-web-browser` and `expo-document-picker` each retire a specific blocker below. Expo Router's file-based routes mirror the existing React Router structure. |
| Monorepo | **npm workspaces + TypeScript project references** | Already npm; no new tool to learn or pin. Turborepo/Nx is YAGNI for three packages. |
| Distribution | **TestFlight / personal use** for v1 | Carried over from `IOS_ROADMAP.md` — unchanged by the framework choice. |
| Parity target | **Today's shipped web feature set**, not `ROADMAP.md`'s end-state | Carried over. Mobile follows the backend, never leads it. |

## Non-goals (revisit only on explicit owner request)

- **Rewriting `frontend/` as react-native-web.** Not now, and not implied by
  anything here. The shared-core split makes it *possible* later; that is the
  entire commitment.
- Racing ahead of `ROADMAP.md` phases — mobile follows, doesn't lead.
- Offline-first / full local persistence — the backend has no sync protocol for
  it; v1 assumes a live connection with only TanStack Query's in-memory caching.
- Public App Store / Play Store distribution, widgets, Siri/Shortcuts, watchOS
  — later candidates, not required for parity.

## Current state

Not started. No `mobile/` directory, no `packages/` directory, and no monorepo
wiring exists yet — `frontend/package.json` is still the only `package.json` in
the repository.

---

## Target repository layout

```
packages/core/   @zerobudget/core — generated API types, API client,
                 domain logic, YNAB parsers, TanStack Query keys + hooks
frontend/        existing web SPA (path deliberately unchanged)
mobile/          new Expo app
package.json     root — npm workspaces
```

`frontend/` keeps its current path on purpose, so `Dockerfile`, `fly.toml` and
the CI `working-directory` don't have to move.

### What belongs in `packages/core`

Everything here is platform-free today, or trivially made so:

- **Generated API types** — replacing the hand-written
  `frontend/src/api/types.ts`, whose own header already says "these are
  hand-written for the skeleton; later we can codegen from the OpenAPI schema".
- **API client** — `frontend/src/api/client.ts` plus `budget.ts`, `banking.ts`,
  `payees.ts`, `scopes.ts`. Needs exactly two injected seams: the base URL
  (hard-coded same-origin `/api` today) and token storage (`localStorage`
  today).
- **Domain logic** — all of `frontend/src/lib/` except the Tailwind palettes:
  `money.ts`, `dates.ts`, `goal.ts`, `insightsRange.ts`, `budgetAvailability.ts`,
  `splitRemaining.ts`, `categorySuggestions.ts`, `transferOption.ts`,
  `readyToAssignOption.ts`. Their existing Vitest suites move with them and
  become the shared regression net.
- **YNAB CSV parsers** — `parseYnabCsv`/`buildPreview` in
  `frontend/src/pages/YnabImportModal.tsx` and
  `parseYnabTransactionCsv`/`parseCurrencyToCents`/`parseYnabDate` in
  `frontend/src/pages/YnabTransactionImportModal.tsx`. All pure functions over a
  string.
- **TanStack Query keys and hooks** — v5 runs identically under React Native.
  This is the single largest win: the whole server-state layer is shared, not
  reimplemented.

**Stays platform-specific:** all UI and routing, plus
`frontend/src/lib/chartColors.ts` and `scopeColors.ts` — they hold Tailwind
class-pair strings validated against the web's white/`stone-900` surfaces, and
that validation does not transfer unexamined.

---

## Phase 0 — Backend prep & shared core extraction

**Goal**: settle the contract and carve out `packages/core`, before any mobile
code exists.

**Why first**: getting auth and the API contract right up front avoids rework
across every later screen. This is also the *only* phase that touches the web
app, so it should land cleanly and early rather than trickling in alongside
mobile work.

### Work items

1. **Backend: refresh-token flow.** `backend/app/security.py` issues a single
   7-day HS256 JWT with no refresh and no rotation, and
   `frontend/src/api/client.ts` simply drops the token on any 401. A native app
   cannot ship on a hard weekly logout with no Face-ID-style resume. Rotate on
   use, pick a reasonable TTL, extend the existing `pytest` auth tests.
2. **Backend: OpenAPI as the contract.** Generate `packages/core`'s types from
   FastAPI's live `/openapi.json` (e.g. `openapi-typescript`) and add a CI drift
   check. This deletes a 285-line hand-maintained mirror and benefits the web
   app immediately, independent of mobile.
3. **Monorepo conversion and core extraction** — root `package.json` with npm
   workspaces, `packages/core`, and `frontend/` rewired to import from it. See
   *Migration hazards* below; three committed files break here and must be
   fixed in the same change.
4. **Configurable API base URL** in the extracted client. Note for whoever
   picks this up: React Native's `fetch` does **not** enforce CORS, so
   `settings.cors_origin_list` in `backend/app/main.py` is *not* the blocker
   people expect it to be. The real work is that `frontend/` assumes
   same-origin `/api` and mobile cannot.

### Acceptance criteria

- Refresh tokens issued and rotated, covered by `pytest`.
- The web app builds, tests, and deploys **unchanged in behavior** while
  importing types, client, and domain logic from `@zerobudget/core`.
- `docker compose up --build` and the GHCR image build both still succeed.

---

## Phase 1 — Expo scaffolding, connectivity, auth

**Goal**: an empty-feeling but real app: launch → enter server URL → log in →
land on a home screen, backed by real network calls.

### Work items

1. New Expo app in `mobile/`, Expo Router + NativeWind configured, Metro wired
   for the workspace.
2. **Server URL onboarding**: first-launch screen to enter and validate a
   self-hosted instance URL, then persist it. Genuinely new surface area — the
   web app has no equivalent because it assumes same-origin deployment.
3. **[owner decision]** HTTP / self-signed-certificate policy. Some self-hosted
   deployments (e.g. a Proxmox LXC on a home LAN) sit behind no valid TLS, and
   both iOS App Transport Security and Android's cleartext policy block that by
   default. Recommend requiring HTTPS, with an explicit, clearly-labeled "allow
   insecure local server" opt-in.
4. Login/Register screens on the real endpoints; `expo-secure-store` for tokens;
   401 → refresh → retry handled once, in the shared client.
5. Android target configured and compiling in CI — not tested, not released.
6. Baseline test scaffold, and a repeatable command for regenerating the
   OpenAPI-derived types as the backend evolves.

### Acceptance criteria

- A fresh install can point at any reachable ZeroBudget instance, register or
  log in, and land on an authenticated screen.
- Killing and relaunching preserves the session via the refresh token.
- `npm run build`-equivalent typecheck passes for `mobile/` on both platforms in
  CI.

---

## Phase 2 — Core ledger: Accounts & Transactions

**Goal**: the app functions as a real ledger — the first "would I trust this
with my money" milestone, mirroring why `ROADMAP.md` put ledger completeness
first for the web app.

### Work items

1. Accounts list/detail: manual + Enable-Banking-connected accounts, scope chip,
   derived balances, closed-account handling.
2. Transactions: filtered list, add/edit (date/payee/memo/amount/category/split),
   transfer entry mode, transfer-link UI fed by
   `backend/app/services/transfer_match.py`.

This is the largest phase by scope — the web equivalents are
`AccountsPage.tsx`, `AccountDetailPage.tsx` and `TransactionsPage.tsx` plus
their modals, around 2,000 lines of UI. Expect it to split into several
implementation-plan-sized chunks when detailed later.

### Acceptance criteria

- Every account and transaction field visible/editable on web is
  visible/editable on mobile, including transfers and splits.

---

## Phase 3 — Budget & Categories

**Goal**: the actual zero-based-budgeting workflow — assigning money, managing
goals — works end to end.

### Work items

1. Budget screen: per-scope Ready-to-Assign pills, collapsible category groups
   with aggregates, inline assignment editing, "Need X" indicators.
2. Categories screen: two-level group/category tree, inline rename, mandatory
   goal editing, delete-with-reassignment prompt.
3. **Drag-to-reorder needs a replacement.** `@dnd-kit` is DOM-only and has no
   React Native equivalent — this is one of the few places where the port is
   not a translation. Expect `react-native-draggable-flatlist` on top of
   `reanimated` + `gesture-handler`, which are native dependencies and
   therefore require a dev build rather than Expo Go.

### Acceptance criteria

- Assigning money, editing goals, and reordering categories on mobile produces
  the same Ready-to-Assign/budget-page state as the equivalent web action.

---

## Phase 4 — Insights

**Goal**: read-only parity for the "where did the money go" screen.

**Cheaper than it looks.** `InsightsPage.tsx` does not use a charting library —
its bars are plain elements sized by percentage width/height. Those map directly
to React Native `View`s with percentage dimensions, so **no chart dependency is
needed**, and the `1M|3M|6M|YTD|1Y` range logic comes free from the shared
`insightsRange.ts`.

### Work items

1. Spending by category/group/scope, income vs. spending per month,
   overspending-vs-recent-norm report, range presets with month-stepping.
2. Port the validated categorical palette from
   `frontend/src/lib/chartColors.ts`. Re-validate contrast against the mobile
   surfaces in light and dark rather than assuming it transfers — the palette's
   own header documents that two light-mode entries already sit just under 3:1.

### Acceptance criteria

- Insights numbers on mobile reconcile with the web Insights page for the same
  month/range, the way `test_insights_api.py` pins that reconciliation
  server-side.

---

## Phase 5 — Banking sync & YNAB import

**Goal**: parity for the two "get data in" paths — flagged separately because
one of them carries real platform-specific risk.

### Work items

1. **Enable Banking connection flow.** On web this is a browser redirect landing
   on `/banking/callback`. On mobile it needs
   `expo-web-browser`'s `openAuthSessionAsync` (which wraps
   `ASWebAuthenticationSession` on iOS) plus a deep link to catch the callback.
   The complication: `ENABLE_BANKING_REDIRECT_URL` is a *single* server-side env
   var that must match a URL registered in the Enable Banking control panel, so
   a mobile deep link needs either a second registered redirect or a server-side
   bounce page. **Worth a short research spike before this phase's real plan is
   written.**
2. Manual sync trigger, sync status and quota display.
3. **YNAB CSV import** via `expo-document-picker`. Because Phase 0 moved both
   parsers into `packages/core`, this is a file picker and a preview screen —
   the parsing logic is shared, not reimplemented. (This is what retires
   `IOS_ROADMAP.md`'s open decision about a Swift reimplementation versus moving
   parsing server-side: with a shared TS core, neither is necessary.)

### Acceptance criteria

- A bank account can be connected and synced from mobile end-to-end.
- A YNAB export imports from mobile with the same de-duplication guarantees as
  the web import, exercising the *same* parser code.

---

## Phase 6 — Settings & native polish

**Goal**: the account-management surface plus the platform-native touches that
justify shipping an app at all.

### Work items

1. Settings screen: server URL management, scopes, profile, password change,
   data export, logout, delete account.
   **[owner decision]** single saved server vs. multiple saved instance
   profiles.
2. Theme: the web app follows the OS theme with no manual toggle
   (`darkMode: "media"`). Decide whether mobile matches that for parity or adds
   a toggle.
3. Explicitly optional/stretch, listed so it doesn't silently expand scope:
   Face ID app-lock, a Ready-to-Assign home-screen widget, share-sheet CSV
   import.
4. Accessibility pass (screen reader, Dynamic Type) — worth doing for a finance
   app.

### Acceptance criteria

- Password change, data export, and account deletion work end-to-end from
  mobile.

---

## Phase 7 — TestFlight release & staying in sync

**Goal**: ship it, and define how it doesn't quietly fall behind the backend.

### Work items

1. App Store Connect setup, EAS Build/Submit, TestFlight internal testing,
   required privacy metadata (needed even for TestFlight-only distribution).
2. **[owner decision]** whether `mobile/` joins the repository's
   `release-please` version train alongside `frontend/` and `backend/`, or
   versions independently. Recommend joining it — one repo, one product version
   — with EAS build numbers tracked separately.
3. Decide whether Android graduates from "compiles in CI" to a tested, released
   target, now that iOS parity exists.
4. Define a lightweight recurring check: whenever a `ROADMAP.md` backend phase
   ships, schedule a "does mobile need to catch up" pass. This is what keeps
   parity true over time rather than true once at launch.

### Acceptance criteria

- A build is installable via TestFlight by the owner.
- This file documents the process for tracking backend phases against mobile
  catch-up work.

---

## Migration hazards

Converting to npm workspaces moves the lockfile to the repository root, which
breaks three committed files. Each is a one-time fix, but all three must land in
the same change as the conversion or CI and the image build go red.

1. **`Dockerfile`** — stage 1 copies only `frontend/package.json` and
   `frontend/package-lock.json`, then runs `npm install` inside `frontend/`.
   It will need the root manifest and lockfile plus `packages/core` in the build
   context.
2. **`.github/workflows/ci.yml`** — the frontend job runs with
   `working-directory: frontend` and
   `cache-dependency-path: frontend/package-lock.json`; `npm ci` fails once the
   lockfile moves. A `mobile` job (typecheck + Android build) is added here too.
3. **`release-please-config.json`** — `extra-files` points at
   `frontend/package-lock.json` with `$.version` and `$.packages[''].version`
   JSONPaths that will no longer resolve.

Two smaller ones, both worth confirming early rather than discovering in Phase 2:

4. **`Intl` on Hermes.** `frontend/src/lib/money.ts` formats every amount in the
   app through `Intl.NumberFormat("en-IE", { currency: "EUR" })`. Hermes' `Intl`
   coverage differs by platform; Android in particular may need
   `@formatjs/intl-numberformat`. Verify in Phase 1, not later — every screen
   depends on it.
5. **Metro and workspaces.** Metro needs explicit `watchFolders` and
   `nodeModulesPaths` to resolve a sibling workspace package. Known friction
   with a documented Expo setup, but it will not work by default.

---

## Open decisions to settle as they come up

1. HTTP/self-signed-certificate policy for self-hosted instances (Phase 1).
2. Single vs. multiple saved server profiles (Phase 6).
3. Theme parity vs. a manual toggle (Phase 6).
4. Mobile versioning relative to `release-please` (Phase 7).
5. Whether Android graduates to a tested, released target (Phase 7).

Settled here, and recorded so they are not reopened by accident: the framework
(React Native/Expo), the relationship to `frontend/` (add alongside, shared
core), the styling approach (NativeWind), the API contract (OpenAPI codegen, not
hand-written models), and CSV parsing (shared TS, neither reimplemented nor
moved server-side).
