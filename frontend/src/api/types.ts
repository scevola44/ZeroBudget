// Shapes that mirror the FastAPI Pydantic responses. These are hand-written
// for the skeleton; later we can codegen from the OpenAPI schema.

export type User = { id: number; email: string };

export type AccountType = "checking" | "savings" | "cash" | string;

export type Account = {
  id: number;
  name: string;
  type: AccountType;
  balance_cents: number;
  plaid_item_id: number | null;
  plaid_mask: string | null;
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
  categories: Category[];
};

export type Transaction = {
  id: number;
  account_id: number;
  category_id: number | null;
  date: string;
  payee: string;
  memo: string;
  amount_cents: number;
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
  categories: BudgetCategoryRow[];
};

export type BudgetMonth = {
  month: string;
  ready_to_assign_cents: number;
  groups: BudgetGroupRow[];
};
