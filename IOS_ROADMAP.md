# ZeroBudget iOS Roadmap

> **Status: ON HOLD.** Mobile development is proceeding with React Native —
> see [`MOBILE_ROADMAP.md`](./MOBILE_ROADMAP.md), which is the live mobile
> roadmap. This document is kept, not deleted, so the native-SwiftUI path stays
> documented as a fallback if React Native disappoints. It is **not** being
> updated; treat everything below as a snapshot of the decision as it stood
> before the reversal described under "Decisions already made".

A phased plan to build a **native SwiftUI iOS client** for ZeroBudget, able to
connect to any self-hosted ZeroBudget instance via a user-entered server URL,
targeting feature parity with the web app.

## Purpose & how to use this document

This document is written for a **coding agent** (or human contributor)
picking up iOS work on this repository. It lives separately from
[`ROADMAP.md`](./ROADMAP.md): that file tracks the backend/web app and stays
agnostic of iOS-specific progress; this file tracks the iOS client only.

- Phases are ordered **most → least important**. Work them in order unless
  the owner says otherwise.
- Each phase is sized to be independently demoable on TestFlight. Do not
  start a phase by building ahead for a later one (YAGNI).
- This document intentionally stops at the "what, why, and roughly how big"
  level — it is a roadmap *of* roadmaps. When a phase is about to start,
  write it a real implementation plan (screen list, API/schema changes,
  acceptance criteria) the way `ROADMAP.md` does for backend phases.
- Items marked **[owner decision]** are open questions this document
  deliberately does not settle — raise them explicitly rather than guess.
- Keep this file updated: when a phase ships, mark it done, the way
  `ROADMAP.md` does.

## Decisions already made

| Decision | Choice | Why |
|---|---|---|
| Client architecture | **SwiftUI native** (not React Native/Capacitor) | Best native performance/feel; the backend API is a small, clean REST/JSON surface, so React Native's main edge — TS code-sharing with `frontend/` — matters less than it looks, and there is no Android target to justify cross-platform. Traded off knowingly: no Swift code exists in this repo yet — this is a cold start into a second language/platform, not a port. |
| Distribution | **TestFlight / personal use** for v1 | No public App Store review overhead; fits a self-hosted personal-finance tool. Revisit only on explicit request for public distribution. |
| Parity target | **Today's shipped web feature set**, not `ROADMAP.md`'s full end-state | Budget/RTA, categories+goals, accounts, transactions (incl. transfers), Enable Banking sync, YNAB CSV import, Insights. Backend phases 2–9 are still moving; iOS tracks them as they ship rather than racing ahead. |
| Auth model | **Add refresh-token support** on the backend, early | Today's JWT is a single 7-day token with no refresh and no password reset (`backend/app/security.py`). Unmodified, iOS would force a full re-login every week with no viable Face ID/persistent-session story. |

> **Reversed — the client-architecture row above no longer holds.** Before any
> Swift was written, the SwiftUI-over-React-Native choice was revisited and
> reversed. Its deciding argument was that the backend is a small, clean
> REST/JSON surface, "so React Native's main edge — TS code-sharing with
> `frontend/` — matters less than it looks". That understated what is actually
> shareable: beyond types, the web app holds platform-free TypeScript for the
> money/date/goal/insights-range domain helpers and their test suites, both YNAB
> CSV parsers, and the entire TanStack Query server-state layer, none of which
> is portable to Swift and all of which would have become a second source of
> truth. The secondary argument — "no Android target to justify
> cross-platform" — was circular: Android was a non-goal *because* SwiftUI made
> it impossible. See [`MOBILE_ROADMAP.md`](./MOBILE_ROADMAP.md) for the
> replacement plan. The other three rows in this table survived the reversal
> unchanged and were carried over.

## Non-goals (revisit only on explicit owner request)

- Android / cross-platform — SwiftUI native is iOS-only by construction.
- Racing ahead of `ROADMAP.md` phases 2–9 (payees, splits, scheduled
  transactions, settings page, generic CSV import, reconciliation,
  credit-card budgeting) — iOS follows the backend, doesn't lead it.
- Offline-first / full local persistence — the backend has no sync protocol
  for it; v1 assumes a live connection, with only incidental caching.
- Public App Store distribution, widgets, Siri/Shortcuts, watchOS — later
  candidates, not required for parity.

## Current state

Not started, and not planned to start. No Swift/Xcode project exists in this
repository, and none will be created while this document is on hold. Mobile work
is tracked in [`MOBILE_ROADMAP.md`](./MOBILE_ROADMAP.md).

---

## Phase 0 — Foundations: decisions, backend prep

**Goal**: settle the decisions every later phase depends on, and make the
backend changes iOS needs, before any Xcode project exists.

**Why first**: getting the auth model and API contract right up front avoids
rework across every later screen.

### Work items

1. **Backend: refresh-token flow.** Extend `backend/app/security.py` /
   `backend/app/routers/auth.py` with a refresh token (rotate on use,
   reasonable TTL) so iOS can keep a session alive via Face ID re-auth
   instead of a hard weekly logout.
2. **Backend: OpenAPI as a contract.** Confirm `/openapi.json` (FastAPI's
   live-generated spec) is complete and stable enough to drive Swift codegen
   (e.g. `swift-openapi-generator`) instead of hand-writing a second copy of
   every model that will drift from `backend/app/schemas/`.
   **[owner decision]** codegen vs. hand-written `Codable` structs —
   recommend codegen given the API will keep changing under `ROADMAP.md`
   phases 2–9.
3. **[owner decision]** iOS/device baseline: minimum iOS version (recommend
   iOS 17+ for modern SwiftUI/Swift Charts/Observation), iPhone-only vs.
   iPhone+iPad.
4. **[owner decision]** App architecture pattern for the new codebase (plain
   MVVM with `@Observable`, or something heavier like TCA) — pick once,
   before Phase 1 scaffolding, since retrofitting later touches every screen.

### Acceptance criteria

- Refresh tokens issued and rotated; existing `pytest` auth tests extended
  to cover the new flow.
- Codegen approach, iOS baseline, and architecture pattern are all decided
  and recorded in this file.

---

## Phase 1 — Project scaffolding, connectivity, auth

**Goal**: an empty-feeling but real app: launch → enter server URL → log in
→ land on a home screen, backed by real network calls.

### Work items

1. New Xcode project, folder/module structure per the Phase 0 architecture
   decision.
2. **Server URL onboarding**: first-launch screen to enter/select a
   self-hosted instance URL, validate reachability, persist it. This is new
   surface area — no equivalent exists in the web app, which assumes
   same-origin deployment.
3. **[owner decision]** HTTP / self-signed-certificate policy. Some
   self-hosted deployments (e.g. a Proxmox LXC on a home LAN) may not sit
   behind valid TLS, and iOS's App Transport Security blocks
   non-HTTPS/invalid-cert connections by default. Recommend requiring HTTPS
   by default, with an explicit, clearly-labeled "allow insecure/local
   server" opt-in.
4. Login/Register screens wired to real endpoints; Keychain-backed token
   storage; refresh-token rotation and 401→refresh→retry handling in the
   networking layer.
5. Baseline XCTest scaffold and a repeatable process for regenerating the
   OpenAPI-derived client as the backend evolves.

### Acceptance criteria

- A fresh install can point at any reachable ZeroBudget instance, register
  or log in, and land on an authenticated screen.
- Killing and relaunching the app preserves the session via the refresh
  token, without a full re-login.

---

## Phase 2 — Core ledger: Accounts & Transactions

**Goal**: the app functions as a real ledger — the first "would I trust this
with my money" milestone, mirroring why `ROADMAP.md` put ledger completeness
first for the web app.

### Work items

1. Accounts list/detail: manual + Enable-Banking-connected accounts, scope
   chip, derived balances, closed-account handling.
2. Transactions: filtered list, add/edit (date/payee/memo/amount/category),
   transfer entry mode, transfer-link UI (candidates/suggestions surfaced by
   `backend/app/services/transfer_match.py`).

This is the largest phase in this roadmap by scope — expect it to be split
into several implementation-plan-sized chunks when detailed later.

### Acceptance criteria

- Every account and transaction field visible/editable on web is
  visible/editable on iOS, including transfers.

---

## Phase 3 — Budget & Categories

**Goal**: the actual zero-based-budgeting workflow — assigning money,
managing goals — works end to end.

### Work items

1. Budget screen: per-scope Ready-to-Assign pills, collapsible category
   groups with aggregates, inline assignment editing, "Need X" indicators.
2. Categories screen: two-level group/category tree, native drag-to-reorder
   (SwiftUI `List` `onMove` — no third-party dependency needed), inline
   rename, mandatory goal editing (monthly/yearly/target-date),
   delete-with-reassignment prompt.

### Acceptance criteria

- Assigning money, editing goals, and reordering categories on iOS produces
  the same Ready-to-Assign/budget-page state as the equivalent web action.

---

## Phase 4 — Insights

**Goal**: read-only parity for the "where did the money go" screen.

### Work items

1. Spending by category/group/scope, income vs. spending per month,
   overspending-vs-recent-norm report, `1M|3M|6M|YTD|1Y` range presets with
   month-stepping.
2. Build with Swift Charts (first-class on iOS 16+, a good fit for this
   data).
3. Port the web app's validated categorical palette
   (`frontend/src/lib/chartColors.ts`) for visual consistency; re-validate
   contrast in iOS light/dark rather than assuming it transfers unchanged.

### Acceptance criteria

- Insights numbers on iOS reconcile with the web Insights page for the same
  month/range, the same way `test_insights_api.py` pins that reconciliation
  server-side.

---

## Phase 5 — Banking sync & YNAB import

**Goal**: parity for the two "get data in" paths — flagged separately from
Phase 2 because both carry real native-specific technical risk worth
surfacing now.

### Work items

1. **Enable Banking connection flow**: today this is a browser redirect to
   `/banking/callback`. On iOS this needs `ASWebAuthenticationSession` (or
   similar) plus a custom URL scheme or universal link to catch the
   callback — genuinely new mechanics, not a straight port. Worth a short
   research spike before this phase's real plan is written.
2. Manual sync trigger, sync status/quota display.
3. **YNAB CSV import**: needs an iOS file picker (`.fileImporter`) since
   there's no drag-a-file-onto-browser equivalent.
   **[owner decision]** whether to reimplement the client-side CSV parser
   in Swift (a second source of truth alongside the TS one) or move parsing
   server-side behind a new endpoint — the latter avoids the kind of
   parsing-logic drift the backend already guards against elsewhere (e.g.
   `backend/app/services/txn_rows.py` keeping budget/insights row-building
   in one place).

### Acceptance criteria

- A bank account can be connected and synced from iOS end-to-end.
- A YNAB export can be imported from iOS with the same de-duplication
  guarantees as the web import.

---

## Phase 6 — Settings & native polish

**Goal**: the account-management screen the web app doesn't have yet either
(see `ROADMAP.md` Phase 7), plus the platform-native touches that justify
having gone native.

### Work items

1. Settings screen: server URL management, profile, password change, data
   export, logout, delete account.
   **[owner decision]** single saved server vs. multiple saved instance
   profiles (useful if the owner ever runs more than one ZeroBudget
   deployment).
2. Theme: the web app currently follows system dark mode with no manual
   toggle; decide whether iOS matches that (parity) or adds one now, since
   SwiftUI makes it cheap.
3. Explicitly optional/stretch, called out so it doesn't silently expand
   scope: Face ID app-lock, home-screen widget for Ready-to-Assign, Shortcuts
   integration for quick entry, share-sheet CSV import.
4. Accessibility pass (VoiceOver, Dynamic Type) — cheap on native, worth
   doing for a finance app.

### Acceptance criteria

- Password change, data export, and account deletion work end-to-end from
  iOS.

---

## Phase 7 — TestFlight release & staying in sync

**Goal**: ship it, and define how it doesn't quietly fall behind the
backend.

### Work items

1. App Store Connect setup, TestFlight internal testing, required privacy
   metadata (needed even for TestFlight-only distribution).
2. **[owner decision]** whether the iOS app's versioning tracks the
   backend's `release-please`-driven versioning or runs independently.
3. Define a lightweight recurring check: whenever a `ROADMAP.md` backend
   phase ships (phase 2 payees/splits, phase 3 move-money, phase 4 scheduled
   transactions, etc.), schedule a corresponding "does iOS need to catch up"
   pass — this is what keeps parity true over time rather than true once at
   launch.

### Acceptance criteria

- A build is installable via TestFlight by the owner.
- This file has a documented process for tracking backend phases against
  iOS catch-up work.

---

## Open decisions to settle before Phase 0 starts

1. Codegen (`swift-openapi-generator`) vs. hand-written models.
2. Minimum iOS version + iPhone-only vs. iPhone+iPad.
3. App architecture pattern (MVVM/`@Observable` vs. something heavier).
4. HTTP/self-signed-certificate support policy for self-hosted instances.
5. Single vs. multiple saved server profiles.
6. CSV import parsing: Swift-side reimplementation vs. new server-side
   endpoint.
7. iOS app versioning relative to the backend's `release-please` releases.
