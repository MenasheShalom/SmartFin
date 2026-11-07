// Mirrors the backend's response models. Money is a decimal string.
export type Money = string;

/** "transfer" is no longer used: what stays out of the cash flow is marked on the transaction */
export type CategoryKind = "expense" | "income" | "transfer";

export interface Category {
  id: number;
  name: string;
  parent_id: number | null;
  kind: CategoryKind;
  is_fixed: boolean;
}

export interface Transaction {
  id: number;
  account_id: number;
  date: string;
  amount: Money;
  currency: string;
  description: string;
  memo: string | null;
  category_id: number | null;
  category_manual: boolean;
  /** Left out of the cash flow: a card bill, or marked by hand */
  out_of_cashflow: boolean;
  /** A bank payment of a credit card bill (out of the cash flow unless marked otherwise) */
  card_bill: boolean;
  /** The hand-set mark; null leaves it to card_bill */
  out_of_cashflow_manual: boolean | null;
}

export interface Rule {
  id: number;
  match_pattern: string;
  is_regex: boolean;
  category_id: number;
  priority: number;
}

export interface TransactionUpdated {
  transaction: Transaction;
  rule: Rule | null;
  recategorized: number;
}

export interface FixedItem {
  category_id: number;
  name: string;
  expected: Money;
  paid: Money;
  status: "paid" | "partial" | "expected" | "skipped";
}

export interface Week {
  start: string;
  end: string;
  budget: Money;
  spent: Money;
  remaining: Money;
  is_current: boolean;
  is_past: boolean;
}

export interface CashFlow {
  month: string;
  through: string | null;
  days_in_month: number;
  days_left: number;
  expected_income: Money;
  income_is_estimate: boolean;
  income_received: Money;
  fixed_expected: Money;
  fixed_paid: Money;
  fixed_items: FixedItem[];
  savings_goal: Money;
  variable_budget: Money;
  variable_spent: Money;
  variable_left: Money;
  projected_variable: Money;
  forecast: Money;
  weeks: Week[];
  current_week_per_day: Money | null;
  uncategorized_count: number;
  uncategorized_net: Money;
}

export interface MonthHistory {
  month: string;
  income: Money;
  expenses: Money;
  net: Money;
  balance: Money | null;
  partial: boolean;
}

export interface SubcategorySpend {
  category_id: number;
  name: string;
  total: Money;
}

export interface CategorySpend {
  category_id: number;
  name: string;
  total: Money;
  /** 0-6: a color that stays with the category from month to month; null: folded into "other" */
  color_slot: number | null;
  subcategories: SubcategorySpend[];
}

export interface MonthSpending {
  month: string;
  total: Money;
  uncategorized: Money;
  categories: CategorySpend[];
}

export interface Account {
  id: number;
  institution: string;
  institution_label: string;
  account_number: string;
  account_type: "bank" | "credit_card";
  balance: Money | null;
  last_synced_at: string | null;
}

export interface SyncStatus {
  institution: string;
  institution_label: string;
  status: "running" | "success" | "failed";
  finished_at: string | null;
  error_message: string | null;
  last_success_at: string | null;
}

export type ConnectionKind = "bank" | "card";

export interface Company {
  id: string;
  label: string;
  kind: ConnectionKind;
  login_fields: string[];
}

/** A bank or card login kept by the scraper; its credentials never come back to the app */
export interface Connection {
  id: string;
  company: string;
  label: string;
  kind: ConnectionKind;
  hint: string | null;
  added_at: string | null;
  sync: "running" | "queued" | null;
  last_sync: { ok: boolean; error_type: string | null; finished_at: string | null } | null;
  /** Set while the nightly sync waits to try a failed card again */
  retry?: { attempt: number; of: number; at: string } | null;
}

export interface Connections {
  connections: Connection[];
  companies: Company[];
}

export interface Alert {
  id: number;
  type: "overspend" | "low_balance" | "unusual_transaction" | "scrape_failure";
  triggered_at: string;
  message: string;
  acknowledged: boolean;
  sent_at: string | null;
}
