// Mirrors the backend's response models. Money is a decimal string.
export type Money = string;

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
  status: "paid" | "partial" | "expected";
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

export interface Alert {
  id: number;
  type: "overspend" | "low_balance" | "unusual_transaction" | "scrape_failure";
  triggered_at: string;
  message: string;
  acknowledged: boolean;
  sent_at: string | null;
}
