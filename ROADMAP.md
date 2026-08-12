# ZeroBudget Roadmap

A phased plan to take ZeroBudget from its current state to feature-complete
zero-based budgeting, using **YNAB as the reference** and borrowing ideas from
similar open-source projects (Actual Budget, Firefly III) where they fit.

## Purpose & how to use this document

This document is written for a **coding agent** (or human contributor) picking
up work on the repository.

- Phases are ordered **most → least important**. Work them in order unless the
  owner says otherwise.
- Within a phase, work items are roughly ordered; backend before frontend
  before tests is the suggested implementation order per item, but each item
  should land **complete** (schema + API + UI + tests) before moving on.
- Each phase is sized to be independently shippable. Do not start a phase by
  refactoring for a later phase (YAGNI).
- When a work item forces a choice this document doesn't settle, it is marked
  **[owner decision]** — stop and ask instead of guessing.
- Keep this file updated: when a phase ships, mark it done with the version it
  shipped in.

## Non-negotiable invariants

These are deliberate design decisions — several diverge from YNAB **on
purpose**; they are the reason this app exists. Every new feature must respect
them. Do not "fix" them to match YNAB.

1. **Scopes** (`personal` / `shared`, labelled "Family" in the UI —
   `backend/app/models/scope.py`, `frontend/src/api/types.ts`): two
   independent budget pools with **separate Ready-to-Assign totals** for one
   user. This replaces YNAB's multi-budget concept. Every new feature must be
   scope-aware: accounts and category groups carry a scope, categorized
   spending must stay within one scope, and aggregates (RTA, reports, totals)
   are computed per scope.
2. **EUR-only, signed integer cents** (`amount_cents: BigInteger` everywhere;
   positive = inflow, negative = outflow). No currency columns, no floats, no
   milliunits. Multi-currency is an explicit non-goal (see bottom).
3. **Mandatory goals on every category** (`goal_kind` NOT NULL on
   `backend/app/models/category.py`; kinds: `monthly`, `yearly`,
   `target_date`). Goals are not optional targets as in YNAB. New goal kinds
   may be *added*, but goals must never become nullable.
4. **Derived balances**: account balances are always
   `SUM(transactions.amount_cents)` computed on read
   (`backend/app/routers/accounts.py`). Never store a balance column.
5. **Budget math stays pure and test-pinned**:
   `backend/app/services/budget_calc.py` is DB-free, takes plain sequences,
   and is exhaustively pinned by `backend/tests/test_budget_calc.py`. All
   changes to RTA/rollover/balance semantics go through this module and its
   tests. Current pinned behavior: category balances roll **both positive and
   negative** amounts forward; overspending never reduces Ready-to-Assign.
6. **Uncategorized inflow = Ready to Assign**: a transaction with
   `category_id IS NULL` and a positive amount is the sole source of RTA.
   There is no "Inflow: Ready to Assign" pseudo-category.
7. **Month convention**: months are `"YYYY-MM"` strings at API/UI boundaries
   and first-of-month `Date`s in the DB (`month_start`, `parse_month` in
   `budget_calc.py`; `frontend/src/lib/dates.ts`).
8. **Conventions to follow** (see CLAUDE.md for the full list):
   - One Alembic migration per schema change (`backend/alembic/versions/`,
     linear chain, currently `0001`–`0005`).
   - Frontend patterns: TanStack Query with array keys + broad prefix
     invalidation, inline-edit (click → input, Enter/blur commits, Escape
     cancels), Tailwind utility classes with `dark:` variants, money via
     `frontend/src/lib/money.ts` (`formatCents`, `parseAmountToCents`).
   - Tests assert behavior, not internals; backend tests use the in-memory
     SQLite fixtures in `backend/tests/conftest.py`.
   - Full typing: Python type hints everywhere, no implicit `any` in TS.

## Current state (v0.1.1-beta.3)

Implemented:

- **Auth**: JWT (HS256, 7-day expiry), register/login/me
  (`backend/app/routers/auth.py`). No refresh, no password reset.
- **Accounts**: manual (checking/savings/cash) + Enable Banking-connected;
  scope chip; derived balances (`routers/accounts.py`,
  `frontend/src/pages/AccountsPage.tsx`).
- **Categories**: two-level tree with drag-and-drop reordering, inline rename,
  mandatory goals, YNAB CSV import (`routers/categories.py`,
  `frontend/src/pages/CategoriesPage.tsx`).
- **Transactions**: CRUD via API; UI creation/edit on the account detail page
  only (category is the only editable field post-creation); read-only filtered
  list + YNAB CSV import on `/transactions`
  (`routers/transactions.py`, `frontend/src/pages/AccountDetailPage.tsx`,
  `frontend/src/pages/TransactionsPage.tsx`).
- **Budget page**: per-scope RTA pills, collapsible groups with aggregates,
  inline assignment editing, "Need X" pills from `needed_this_month_cents`
  (`routers/budget.py`, `services/budget_calc.py`,
  `frontend/src/pages/BudgetPage.tsx`).
- **Enable Banking** (PSD2, EUR-only): redirect-based consent flow, manual
  or automatic sync behind a global daily quota (`SYNC_MODE`,
  `SYNC_MAX_PER_DAY`; DB-backed `sync_runs` ledger, in-process scheduler in
  auto mode); Fernet-encrypted session ids; windowed re-fetch with dedup by
  `external_transaction_id`; pending and non-EUR transactions skipped; user
  edits preserved on updated transactions (`routers/banking.py`,
  `services/banking_client.py`, `services/bank_sync.py`,
  `services/sync_scheduler.py`). No deletion detection (no delta API).
- **Insights page**: spending breakdown by category/group/scope, income vs
  spending per month, and an overspending report comparing each category
  against its recent norm; `1M | 3M | 6M | YTD | 1Y` range presets with
  month-stepping arrows (`routers/insights.py`, `services/insights_calc.py`,
  `frontend/src/pages/InsightsPage.tsx`). See Phase 5.
- Responsive layout with dark mode (`darkMode: "media"`), mobile off-canvas nav.

Not implemented (the gap this roadmap closes): payees, splits,
search/bulk edit, move-money/auto-assign, scheduled transactions, net worth
over time, generic CSV import, import matching, settings/auth hardening,
cleared/reconciliation, credit-card budgeting.

Phase 1 closed the rest: transfers are linked transaction pairs
(`transfer_peer_id`, `POST /api/transactions/transfer`), every transaction
field is editable from both transaction surfaces, accounts can be renamed,
retyped, rescoped and closed, and categories can be deleted with optional
reassignment of their transactions.

---

## Phase 1 — Ledger completeness: transfers, full transaction editing, entity management ✅ **Done**

> Shipped in the release cut from the PR that closed this phase. Two
> decisions were settled during implementation and are recorded under
> "Decisions taken" below.

**Goal**: everything a user records in real life can be recorded correctly,
and every entity the API can mutate is manageable from the UI.

**Why first**: transfers are the biggest correctness hole — today moving money
between own accounts either double-counts as spending or requires a hack with
two uncategorized transactions. The code already earmarks this
(`backend/app/routers/transactions.py` — "Cross-scope movement must go through
transfers (Phase 2)"). Locked-down transaction editing (delete + re-add to fix
a typo) is the most painful daily friction.

### Work items

1. **Transfer model (backend)**
   - Linked transaction pair: add nullable self-referential
     `transfer_peer_id` FK on `transactions` (Alembic migration `0007`).
     Each leg lives in its own account; amounts are equal and opposite; both
     legs have `category_id = NULL` and are excluded from RTA inflow math.
   - New `budget_calc.py` rule: transactions that are transfer legs never
     count as inflow, regardless of sign. Extend
     `backend/tests/test_budget_calc.py` (the existing `test_transfer_pair_*`
     tests pin the current workaround — update them to the first-class
     model).
   - **Same-scope transfer**: RTA-neutral by construction.
   - **Cross-scope transfer** (personal ↔ shared): also category-free; the
     outflow leg reduces the source scope's RTA (money left the pool), the
     inflow leg raises the destination scope's RTA. This matches the current
     two-uncategorized-transactions behavior, now atomic and linked.
   - API: `POST /api/transactions/transfer` creating both legs atomically;
     `PATCH`/`DELETE` on either leg keeps the pair consistent (edit
     amount/date mirrors to the peer; delete removes both). Category edits on
     a transfer leg are rejected.
2. **Full transaction editing (frontend)** — the backend `PATCH` already
   accepts date/payee/memo/amount. Add row editing on
   `AccountDetailPage.tsx` (click row → inline edit or edit modal following
   the `EditGroupModal.tsx` pattern), and make rows on `TransactionsPage.tsx`
   editable the same way.
3. **Transfer UI**: in the add-transaction form on `AccountDetailPage.tsx`,
   add a "Transfer to/from account" mode (YNAB-style `Transfer: <Account>`
   entry in the category/payee position). Show the peer account on transfer
   rows; editing either leg round-trips through the pair-consistency API.
4. **Account management UI**: expose the existing
   `PATCH /api/accounts/{id}` (rename, type, scope — scope change already
   guarded server-side) and `DELETE` on `AccountsPage.tsx`. Add the missing
   `credit`/`loan` options to the manual account type picker
   (`frontend/src/api/types.ts` `AccountType`).
   **[owner decision]** whether deleting an account with transactions should
   be blocked, cascade, or offer a "closed/archived" state (YNAB closes
   rather than deletes; recommend a `closed` boolean + hidden-by-default).
5. **Category delete UI**: expose `DELETE /api/categories/{id}` on
   `CategoriesPage.tsx` (endpoint exists, unexposed). On delete, transactions
   keep `NULL` category (FK is `ON DELETE SET NULL`) — surface a
   YNAB-style "reassign transactions to another category first?" prompt.

### Decisions taken

1. **The RTA rule as originally written was self-contradictory.** Work item 1
   said transfer legs "never count as inflow, regardless of sign" while also
   requiring a cross-scope transfer to move RTA between pools — those cannot
   both hold. Settled: a leg feeds RTA **only when its peer is in a different
   scope**. Same-scope pairs are excluded outright; cross-scope pairs move
   money between pools as specified. `budget_calc.feeds_ready_to_assign` is
   the single definition, and `insights_calc._is_internal_transfer` applies
   the same split, so the pinned Insights/Budget reconciliation still holds.
   Both routers build their rows through `services/txn_rows.py` to keep the
   two from drifting.
2. **[owner decision] on account deletion: a `closed` flag.** Closing hides
   the account and keeps its transactions, so past months are untouched.
   `DELETE` is refused when an account has transactions.
3. The migrations landed as **`0007`** (transfer peer) and **`0008`**
   (account closed) — `0006` was already taken by `bank_auth_request_scope`.

### Acceptance criteria

- Creating a transfer creates two linked legs; deleting/editing one keeps the
  pair consistent; same-scope transfer legs never appear in RTA inflow
  (pinned in `test_budget_calc.py` + `test_transfers.py`).
- Same-scope transfer leaves both scopes' RTA unchanged; cross-scope transfer
  moves RTA between pools by exactly the amount.
- Every transaction field is editable from both transaction surfaces.
- Accounts can be renamed, retyped, rescoped (within guards), and
  deleted/closed; categories can be deleted — all from the UI.
- `pytest` green; new behavior covered.

---

## Phase 2 — Daily-entry ergonomics: payees, split transactions, search & bulk edit

**Goal**: entering and finding transactions is as fast as YNAB.

**Why here**: after correctness (Phase 1), entry speed is what makes or breaks
daily use of a budgeting app.

### Work items

1. **Payee model**: promote the free-text `payee` column to a `payees` table
   (`id`, `user_id`, `name`, unique per user) with `payee_id` FK on
   transactions (keep the string column during migration, backfill, then
   drop). API: list payees, rename (updates all transactions), merge.
   - Autocomplete in transaction forms (datalist or small combobox following
     existing hand-rolled select pattern).
   - **Last-used-category suggestion**: when a payee is picked, pre-select
     the category from that payee's most recent categorized transaction
     (YNAB behavior). Respect scope: only suggest categories whose group
     scope matches the account scope.
   - *Stretch (Actual Budget-inspired)*: simple auto-categorization rules
     (payee-contains → category), applied to bank-synced and imported
     transactions only, never overwriting a user-set category.
2. **Split transactions**: sub-line model — `transaction_splits` table
   (`transaction_id` FK, `category_id`, `amount_cents`, `memo`) where split
   amounts must sum to the parent amount (validate at the API boundary). A
   transaction with splits has `category_id = NULL` at the parent level;
   budget activity math (`compute_category_balances`) consumes split lines.
   Scope rule applies per line. UI: expandable split editor in the
   transaction form, following YNAB's remaining-amount pattern.
3. **Transactions page, full-capability**
   (`frontend/src/pages/TransactionsPage.tsx` + `routers/transactions.py`):
   - Server-side filtering for account/category (currently client-side) and
     **pagination** (`limit`/`offset` or cursor; default page size ~100).
   - Free-text search across payee/memo (`q` param, `ILIKE`).
   - Multi-select with bulk actions: set category, delete
     (bulk endpoints or sequential PATCH — prefer one bulk endpoint each).
   - Inline editing parity with `AccountDetailPage.tsx` (shipped in Phase 1).

### Acceptance criteria

- Typing a known payee autofills its last category; renaming/merging payees
  updates history.
- A split transaction budgets each line to its own category; parent amount
  integrity enforced (422 on mismatch); budget page activity reflects lines.
- `/transactions` can search, paginate, filter server-side, and bulk-edit.
- Migration backfills payees from existing strings without data loss.

---

## Phase 3 — Budgeting UX: money movement & auto-assign

**Goal**: managing the budget (not just recording it) matches YNAB's speed —
cover overspending, fund goals, move money without mental arithmetic.

### Work items

1. **Move money between categories**: UI affordance on the Available pill in
   `BudgetPage.tsx` (click → "Move to…" popover: amount + destination
   category in the same scope). Implementation is two `POST
   /api/budget/{month}/assign` upserts; add an atomic
   `POST /api/budget/{month}/move` endpoint so partial failure can't lose
   money.
2. **Cover overspending**: on a negative Available pill, offer "Cover from…"
   (same move mechanic, pre-filled with the shortfall).
3. **Auto-assign / underfunded**: per-scope "Fund goals" button that assigns
   `needed_this_month_cents` (already computed in
   `backend/app/routers/budget.py::_needed_this_month`) to every underfunded
   category, capped by the scope's RTA; preview before commit
   (YNAB's Underfunded quick-assign).
4. **Goal progress indication**: progress bar or fill on the category row
   (assigned vs `needed_this_month_cents`), reusing the existing pill color
   logic (`availablePillClass`).
5. **Month navigation polish**: month in the URL
   (`/budget?month=YYYY-MM` or `/budget/YYYY-MM`) so reload/back keep the
   month; jump-to-month picker next to the arrows.
6. *Optional, additive*: new goal kinds — e.g. `target_balance` (no date) —
   extending `GOAL_KINDS` in `backend/app/models/category.py` and
   `frontend/src/lib/goal.ts`. Goals stay mandatory (invariant 3).

### Acceptance criteria

- Money can be moved between two categories in ≤3 clicks; RTA and both
  balances update; the move endpoint is atomic.
- "Fund goals" assigns exactly the underfunded sum per scope, never exceeding
  that scope's RTA, and shows what it will do before doing it.
- Month survives reload; deep links to a month work.

---

## Phase 4 — Scheduled & recurring transactions

**Goal**: rent, salary, subscriptions enter themselves.

### Work items

1. **Model**: `scheduled_transactions` table — account, payee, category (or
   transfer peer account), amount, memo, `frequency`
   (`weekly`/`monthly`/`yearly`/`every_n_days` **[owner decision]** on the
   exact set), `next_date`, `enabled`.
2. **Materialization**: server-side, on-request — when any authenticated
   request touches transactions/budget for the first time in a day (or via an
   explicit `POST /api/scheduled/materialize`), create due transactions and
   advance `next_date`. **No background worker** (self-hosted, single user —
   keep the deploy simple). Materialized transactions are ordinary
   transactions.
3. **Semantics**: skip-once, edit-this-occurrence (edit the materialized
   transaction), edit-series (edit the schedule). Deleting a schedule leaves
   past materialized transactions untouched.
4. **UI**: manage schedules (list/create/edit) — either a section on
   `/transactions` or a small dedicated page; show upcoming (next 30 days)
   items greyed-out at the top of `AccountDetailPage.tsx` (YNAB-style).

### Acceptance criteria

- A monthly schedule creates exactly one transaction per month, on/after the
  due date, idempotently (no duplicates on repeated materialization calls —
  pin with a test).
- Upcoming transactions are visible but excluded from balances and budget
  activity until materialized.

---

## Phase 5 — Insights (mostly shipped)

**Goal**: answer "where did the money go / how are we doing" — YNAB's
Reflect tab, scope-aware. Called **Insights**, not Reports: `/insights`,
`/api/insights`, `services/insights_calc.py`.

### Shipped

1. **`GET /api/insights?start_month=&end_month=`** — one endpoint serving all
   three sections, since they share the same row load. Explicit inclusive
   bounds match `/api/transactions`; range presets stay a frontend concern.
   Math lives in the pure, DB-free `backend/app/services/insights_calc.py`
   (mirroring `budget_calc.py`), pinned by `tests/test_insights_calc.py`:
   - Spending by category/group/scope over a span of whole months.
   - Income vs spending per month.
   - Per-category comparison against a recent norm.
2. **Insights page** (`/insights`, sidebar entry in
   `frontend/src/components/Layout.tsx`): Personal and Family rendered as two
   parallel columns throughout; `1M | 3M | 6M | YTD | 1Y` presets plus arrows
   that step the anchor month by one. Charts are hand-rolled Tailwind divs —
   no chart dependency was added. The categorical palette in
   `frontend/src/lib/chartColors.ts` was validated against both surfaces for
   contrast and colour-vision separation; re-validate before changing it.

**Definitions worth not re-deriving:**

- Spending is **gross**, with refunds reported alongside rather than netted
  in. A floored net does not sum across months when a refund lands in a
  different month from its purchase.
- Income stays uncategorized inflow only (invariant 6), so
  `income - spending` is the scope's net cash flow.
- "Usual" is the **median** per-month value over the six whole months before
  the period, counting only months at or after a category's first activity
  and requiring at least three. Median because one annual bill in the window
  would otherwise make every ordinary month read as far below usual.
- A flag needs **both** a proportion and an amount: strictly above 10% *and*
  at least `MIN_NOTABLE_CENTS` (€10) per month of the period. The percentage
  governs large categories, the floor governs small ones, where 10% of a €20
  habit is two euros. The same floor gates the negative-balance flag, so a few
  euros overdrawn and covered the next month doesn't bury the real problems.
  The rule is returned on the response so the page states it rather than
  hardcoding numbers that would drift.
- Available balances are walked month by month, so a category that dipped
  mid-period is still reported.

### Not shipped — follow-up

- **Net worth over time** (per-month cumulative transaction sums per account —
  derived, per invariant 4).
- **Age of Money** (YNAB's FIFO days-between-inflow-and-outflow).

### Resolved in Phase 1

Transfers used to be two untagged uncategorized transactions, so the receiving
leg read as income and the sending leg as uncategorized spending. Legs now
carry `transfer_peer_id`, and `insights_calc._is_internal_transfer` drops both
legs of a same-scope transfer from Ready to Assign and from income. Spending
goes further still: unassigned (`category_id IS NULL`) outgoing money never
counts as an expense on this page at all, transfer or not, same-scope or
cross-scope — there is no "Uncategorized" spending bucket. A cross-scope
transfer's *inflow* leg genuinely moves money into the receiving pool and
still counts as that scope's income, same as any other unassigned inflow.

### Acceptance criteria

- Insights numbers reconcile with the budget page for the same month — pinned
  by `test_insights_api.py::test_insights_reconciles_with_the_budget_page_for_the_same_month`
  and, at the pure level, by
  `test_insights_calc.py::test_month_end_balances_match_compute_category_balances`.
  The latter is load-bearing: `insights_calc` re-implements the rollover walk
  for speed, and that test is what stops it drifting from `budget_calc`.
- Personal and Family are computed and rendered separately. The only
  cross-scope figure is the explicitly labelled Personal-vs-Family split bar.

---

## Phase 6 — Import & bank-sync robustness

**Goal**: get data in from any bank, cleanly, without duplicates.

### Work items

1. **Generic CSV import with column mapping**: extend the import modal flow
   (`frontend/src/pages/YnabTransactionImportModal.tsx` parses client-side —
   keep that approach) with a mapping step (choose which columns are
   date/payee/amount/memo; amount sign or separate inflow/outflow columns;
   European number formats via `parseAmountToCents`). Reuse
   `POST /api/transactions/import-ynab` semantics via a generalized
   `POST /api/transactions/import`.
2. **Import matching / approval** — **transfer half done**: a sync fetches each
   account separately, so a real transfer arrived as two unlinked uncategorized
   rows that read as income *and* spending on Insights, and skewed Ready to
   Assign whenever the legs straddled a month boundary. Two existing rows can
   now be linked into a transfer pair
   (`POST /api/transactions/{id}/transfer-link`, `DELETE` to unlink without
   deleting either row), with candidates and suggested pairs offered by
   `services/transfer_match.py` (exact opposite amounts, different accounts,
   dates within `TRANSFER_MATCH_WINDOW_DAYS`). Suggestions are always confirmed
   by the user — a refund and an unrelated purchase of the same size look
   identical to a matcher.

   **[decision]** No `import_status` column and no staging table: a suggestion
   is derivable from the transactions table alone, so persisting it would create
   a second source of truth for `budget_calc.py` inputs to drift from. Nothing
   is written until the user confirms, which keeps unapproved rows out of the
   math by construction. No migration was needed.

   Still open: matching synced rows against *manual* entries the user typed
   ahead of the sync (the double-counting half of this item).
3. ~~Plaid webhooks~~ **Done differently**: Plaid was replaced by Enable
   Banking (PSD2, redirect consent), which has no webhook/delta API. Instead
   of webhooks, automatic sync is an in-process scheduler (`SYNC_MODE=auto`)
   spacing runs evenly under the daily quota (`SYNC_MAX_PER_DAY`).
4. ~~EU bank-sync provider evaluation~~ **Resolved [owner decision]**:
   **Enable Banking** was adopted as the PSD2 provider, replacing Plaid
   entirely (it was sandbox-only, so nothing was lost). The sync pipeline
   kept the provider-agnostic semantics (dedup key + user-field
   preservation) in `services/bank_sync.py`.

### Acceptance criteria

- A CSV from an arbitrary bank imports via mapping UI with correct EUR
  parsing; re-importing the same file creates no duplicates.
- Synced/imported rows that match a manual entry don't double-count; the
  approval queue is visible and clearable.
- Two imported rows that are really one transfer can be linked, drop out of
  income and spending, and leave Ready to Assign untouched in *both* months when
  their dates straddle a month boundary (pinned in `test_transfer_linking.py`
  and `test_insights_api.py`).
- With webhooks configured, a Sandbox transaction lands without pressing
  Sync; without webhook config, everything behaves as today.

---

## Phase 7 — Platform hardening & settings

**Goal**: the boring-but-necessary account and app management YNAB has and a
self-hosted app needs.

### Work items

1. **Settings page** (`/settings`, sidebar entry): profile (email display),
   password change, theme override (light/dark/system — currently
   `darkMode: "media"` only in `frontend/tailwind.config.js`; switch to
   `class` strategy with a stored preference), **data export** (all
   transactions/budget as CSV and JSON — self-hosting escape hatch), account
   deletion (full cascade, confirm-by-typing).
2. **Auth hardening**: password reset **[owner decision]** on mechanism —
   email requires SMTP config for self-hosters; a CLI/one-time-token reset
   script may fit better. Token refresh or sliding expiry to soften the hard
   7-day JWT logout (`backend/app/security.py`).
3. **API hygiene**: default pagination on all list endpoints (transactions
   done in Phase 2 — extend to the rest); consistent 422 error shapes.
4. **Frontend robustness**: toast system + error boundary (replace silent
   mutation failures and native `confirm()` dialogs — e.g. transaction
   delete, bank disconnect — with the existing modal pattern
   (`DeleteGroupConfirmModal.tsx`)).
5. **Cleanup**: delete or adopt dead code (`frontend/src/components/Select.tsx`
   unused); make `Account.type` a real enum
   at the API boundary (`backend/app/models/account.py` free-form string
   today); remove the stray `frontend/IMG_5730.png` if unused.

### Acceptance criteria

- Password change and export work end-to-end; deleting the account removes
  all user rows (pin with a test).
- No native `confirm()` left; failed mutations always surface feedback.

---

## Phase 8 — Cleared status & reconciliation *(owner-deprioritized)*

> The owner barely used reconciliation in YNAB — implement only when the
> phases above are done, or on explicit request.

### Work items

1. `cleared` enum (`uncleared`/`cleared`/`reconciled`) on transactions +
   migration; bank-synced transactions arrive `cleared` (they're posted,
   pending are skipped in `services/bank_sync.py`).
2. Cleared vs working balance on `AccountDetailPage.tsx`; per-row cleared
   toggle (YNAB's ⓒ column).
3. Reconcile flow: enter real-world balance → app computes difference →
   optional balance-adjustment transaction (uncategorized, or a dedicated
   adjustment payee) → mark cleared rows `reconciled` and lock them (edits
   require un-reconciling).
4. Wire the YNAB-import `Cleared` column (parsed and currently discarded in
   `YnabTransactionImportModal.tsx`).

### Acceptance criteria

- Reconciliation with a matching balance marks rows reconciled with no
  adjustment; a mismatch creates exactly the adjustment difference.
- Reconciled rows are immutable until explicitly unlocked.

---

## Phase 9 — Credit card budgeting *(owner-deprioritized)*

> Same caveat: barely used by the owner. Connected accounts currently import
> as checking accounts, which is fine for pay-in-full usage. Implement only
> on demand.

### Work items

1. Make `credit` accounts first-class: auto-created "Credit Card Payment"
   category per credit account (own group or per-scope group).
2. YNAB mechanic: categorized spending **on a credit account** moves the
   assigned money from the spending category to the card's payment category;
   a payment is a transfer (Phase 1) to the card that draws down the payment
   category.
3. **[owner decision]** — cash-vs-credit overspending distinction: YNAB
   reduces next month's RTA for cash overspending but turns credit
   overspending into card debt. ZeroBudget's current, test-pinned behavior
   (all overspending rolls forward as negative balance, RTA untouched) is
   documented as intentional in `budget_calc.py`. Options:
   a) keep pure rollover and add only the payment-category mechanic
      (simpler, recommended), or
   b) adopt YNAB semantics fully (bigger change to `budget_calc.py` +
      re-pinning `test_budget_calc.py`).
4. *Stretch*: debt payoff goal kind for card/loan accounts.

### Acceptance criteria

- Budgeted credit spending leaves the payment category holding exactly the
  spent amount; paying the card from checking zeroes it.
- Chosen overspending semantics pinned in `test_budget_calc.py`.

---

## Explicit non-goals

Listed so nobody drifts into them. Revisit only on explicit owner request.

- **Multi-currency** — ZeroBudget is EUR-only by design (hard gates at the
  bank-sync boundary; no currency columns).
- **Native mobile client scope creep on this backend** — a native iOS client
  is being planned separately in [`IOS_ROADMAP.md`](./IOS_ROADMAP.md); that
  document tracks its own phases and does not belong in this file.
- **Multi-user households / sharing** — the `shared` scope models the joint
  pool for a single login; real multi-login sharing is out of scope.
- **Loan planner / investment tracking** — `loan` accounts may exist as
  simple ledgers, nothing more.
- **YNAB API sync, rewind/undo history, month notes/flags** — nice-to-haves
  with no current demand.
