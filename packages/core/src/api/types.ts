import type { components } from "../generated/schema";

// Aliases over the types generated from the backend's OpenAPI schema
// (`npm run gen:types -w @zerobudget/core`), so call sites keep short names.
// Do not hand-write response shapes here: change the backend and regenerate.
type Schemas = components["schemas"];

export type User = Schemas["UserResponse"];

// The backend accepts any string; these are just the values the UI offers.
export type AccountType = "checking" | "savings" | "cash" | "credit" | "loan" | string;

export const MANUAL_ACCOUNT_TYPES: { value: string; label: string }[] = [
  { value: "checking", label: "Checking" },
  { value: "savings", label: "Savings" },
  { value: "cash", label: "Cash" },
  { value: "credit", label: "Credit" },
  { value: "loan", label: "Loan" },
];

// A budget pool. Users create, rename and delete their own; the two a new
// account starts with ("Personal", "Family") are seeds, not fixed values.
// `sort_order` is both the display order and the palette slot.
export type Scope = Schemas["ScopeResponse"];

export type Account = Schemas["AccountResponse"];

export type GoalKind = Schemas["CategoryResponse"]["goal_kind"];
export type Category = Schemas["CategoryResponse"];
export type CategoryGroup = Schemas["CategoryGroupResponse"];

export type TransactionSplit = Schemas["TransactionSplitResponse"];
export type Transaction = Schemas["TransactionResponse"];

/** GET /api/transactions' response envelope: a page of rows plus a cursor to
 * fetch the next one, when there is one. */
export type TransactionPage = Schemas["TransactionPage"];

export type Payee = Schemas["PayeeResponse"];
export type PayeeCategoryRule = Schemas["PayeeCategoryRuleResponse"];

export type Transfer = Schemas["TransferResponse"];
export type TransferCandidate = Schemas["TransferCandidate"];
export type TransferSuggestion = Schemas["TransferSuggestion"];
export type PayeeTransferSuggestion = Schemas["PayeeTransferSuggestion"];

export type BudgetCategoryRow = Schemas["BudgetCategoryRow"];
export type BudgetGroupRow = Schemas["BudgetGroupRow"];
export type ScopeReadyToAssign = Schemas["ScopeReadyToAssign"];
export type BudgetMonth = Schemas["BudgetMonthResponse"];
export type FundGoalsEntry = Schemas["FundGoalsEntryResponse"];
export type FundGoalsPreview = Schemas["FundGoalsPreviewResponse"];

export type InsightsPeriod = Schemas["InsightsPeriod"];
export type CategorySpendingRow = Schemas["CategorySpendingRow"];
export type GroupSpendingRow = Schemas["GroupSpendingRow"];
export type ScopeBreakdown = Schemas["ScopeBreakdown"];
export type ScopeSplitRow = Schemas["ScopeSplitRow"];
export type ScopeSplit = Schemas["ScopeSplit"];
export type SpendingBreakdown = Schemas["SpendingBreakdown"];
export type MonthFlowRow = Schemas["MonthFlowRow"];
export type ScopeFlow = Schemas["ScopeFlow"];
export type CategoryTrendRow = Schemas["CategoryTrendRow"];
export type OverspendFlag = CategoryTrendRow["flags"][number];
export type ScopeOverspending = Schemas["ScopeOverspending"];
export type Overspending = Schemas["Overspending"];
export type Insights = Schemas["InsightsResponse"];

export type YnabImportRow = Schemas["YnabImportRow"];
export type YnabImportResponse = Schemas["YnabImportResponse"];
