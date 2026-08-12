// Shapes that mirror the FastAPI Pydantic responses. These are hand-written
// for the skeleton; later we can codegen from the OpenAPI schema.

export type User = { id: number; email: string };

export type AccountType = "checking" | "savings" | "cash" | "credit" | "loan" | string;

export const MANUAL_ACCOUNT_TYPES: { value: string; label: string }[] = [
  { value: "checking", label: "Checking" },
  { value: "savings", label: "Savings" },
  { value: "cash", label: "Cash" },
  { value: "credit", label: "Credit" },
  { value: "loan", label: "Loan" },
];

export type Scope = "personal" | "shared";

export const SCOPES: Scope[] = ["personal", "shared"];

export function scopeLabel(scope: Scope): string {
  return scope === "shared" ? "Family" : "Personal";
}

export type Account = {
  id: number;
  name: string;
  type: AccountType;
  scope: Scope;
  balance_cents: number;
  closed: boolean;
  bank_connection_id: number | null;
  bank_account_mask: string | null;
  institution_name: string | null;
};

export type GoalKind = "monthly" | "yearly" | "target_date";

export type Category = {
  id: number;
  group_id: number;
  name: string;
  sort_order: number;
  goal_kind: GoalKind;
  goal_amount_cents: number;
  goal_target_month: string | null; // ISO "YYYY-MM-DD", first-of-month
};

export type CategoryGroup = {
  id: number;
  name: string;
  sort_order: number;
  scope: Scope;
  categories: Category[];
};

export type Transaction = {
  id: number;
  account_id: number;
  category_id: number | null;
  // Deliberately uncategorized: its purpose is only to move Ready to Assign
  // (a balance reconcile, a paycheck), not to await a category. Never true
  // together with a non-null category_id.
  is_ready_to_assign: boolean;
  date: string;
  payee: string;
  memo: string;
  amount_cents: number;
  // Set on both legs of a transfer, each pointing at the other.
  transfer_peer_id: number | null;
  // The account holding the other leg, for labelling transfer rows.
  transfer_peer_account_id: number | null;
};

export type Transfer = {
  from_transaction: Transaction;
  to_transaction: Transaction;
};

// A transaction that could be the other leg of one being linked.
export type TransferCandidate = {
  transaction: Transaction;
  // Signed, relative to the transaction being linked: -2 means two days earlier.
  date_offset_days: number;
};

// Two imported rows that look like the two halves of one transfer. Always a
// suggestion — the user confirms before anything is linked.
export type TransferSuggestion = {
  outflow: Transaction;
  inflow: Transaction;
};

// A row whose payee names another (unsynced) account of the user's. Always a
// suggestion — confirming it creates the missing leg there.
export type PayeeTransferSuggestion = {
  transaction: Transaction;
  to_account_id: number;
  to_account_name: string;
};

export type BudgetCategoryRow = {
  id: number;
  name: string;
  assigned_cents: number;
  activity_cents: number;
  balance_cents: number;
  goal_kind: GoalKind;
  goal_amount_cents: number;
  goal_target_month: string | null;
  needed_this_month_cents: number | null;
};

export type BudgetGroupRow = {
  id: number;
  name: string;
  scope: Scope;
  categories: BudgetCategoryRow[];
};

export type BudgetMonth = {
  month: string;
  personal_ready_to_assign_cents: number;
  shared_ready_to_assign_cents: number;
  groups: BudgetGroupRow[];
};

export type InsightsPeriod = {
  start_month: string;
  end_month: string;
  month_count: number;
  baseline_start_month: string;
  baseline_end_month: string;
};

export type CategorySpendingRow = {
  category_id: number;
  name: string;
  group_id: number;
  group_name: string;
  spent_cents: number;
  refund_cents: number;
  activity_cents: number;
};

export type GroupSpendingRow = {
  group_id: number;
  name: string;
  spent_cents: number;
  sort_index: number;
};

export type ScopeBreakdown = {
  scope: Scope;
  total_spent_cents: number;
  uncategorized_spent_cents: number;
  groups: GroupSpendingRow[];
  categories: CategorySpendingRow[];
};

export type ScopeSplit = {
  personal_spent_cents: number;
  shared_spent_cents: number;
  total_spent_cents: number;
};

export type SpendingBreakdown = {
  scope_split: ScopeSplit;
  personal: ScopeBreakdown;
  shared: ScopeBreakdown;
};

export type MonthFlowRow = {
  month: string;
  income_cents: number;
  spent_cents: number;
  refund_cents: number;
  net_cents: number;
};

export type ScopeFlow = {
  scope: Scope;
  income_cents: number;
  spent_cents: number;
  refund_cents: number;
  net_cents: number;
  months: MonthFlowRow[];
};

export type OverspendFlag =
  | "spent_above_usual"
  | "assigned_above_usual"
  | "new_spending"
  | "available_negative";

export type CategoryTrendRow = {
  category_id: number;
  name: string;
  group_name: string;
  assigned_cents: number;
  expected_assigned_cents: number | null;
  assigned_delta_cents: number | null;
  assigned_delta_pct: number | null;
  spent_cents: number;
  expected_spent_cents: number | null;
  spent_delta_cents: number | null;
  spent_delta_pct: number | null;
  baseline_month_count: number;
  has_baseline: boolean;
  worst_balance_cents: number;
  worst_balance_month: string | null;
  flags: OverspendFlag[];
};

export type ScopeOverspending = {
  scope: Scope;
  categories: CategoryTrendRow[];
  on_track_count: number;
};

export type Insights = {
  period: InsightsPeriod;
  breakdown: SpendingBreakdown;
  income_vs_spending: { personal: ScopeFlow; shared: ScopeFlow };
  overspending: Overspending;
};

export type Overspending = {
  threshold_pct: number;
  min_notable_cents: number;
  min_baseline_months: number;
  personal: ScopeOverspending;
  shared: ScopeOverspending;
};

export type YnabImportRow = { group: string; category: string };
export type YnabImportResponse = { groups_created: number; categories_created: number };
