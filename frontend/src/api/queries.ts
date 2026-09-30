import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useRef } from "react";

import { api } from "./client";
import type {
  Account,
  Alert,
  CashFlow,
  Category,
  CategoryKind,
  Connection,
  Connections,
  MonthHistory,
  Rule,
  SyncStatus,
  Transaction,
  TransactionUpdated,
} from "./types";

export const keys = {
  me: ["me"] as const,
  authStatus: ["auth-status"] as const,
  cashflow: (month: string) => ["cashflow", month] as const,
  history: ["history"] as const,
  categories: ["categories"] as const,
  rules: ["rules"] as const,
  accounts: ["accounts"] as const,
  syncStatus: ["sync-status"] as const,
  connections: ["connections"] as const,
  alerts: ["alerts"] as const,
  transactions: (params: TransactionQuery) => ["transactions", params] as const,
};

/** The whole to-categorize queue; drives the tab badge and the home screen prompt */
export const UNCATEGORIZED_QUERY = { uncategorized: true, limit: 500 } as const;

export interface TransactionQuery {
  month?: string;
  uncategorized?: boolean;
  date_from?: string;
  date_to?: string;
  q?: string;
  category_id?: number;
  limit?: number;
}

function query(params: object): string {
  const search = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value !== undefined && value !== "" && value !== false) search.set(key, String(value));
  }
  const s = search.toString();
  return s ? `?${s}` : "";
}

export interface Me {
  authenticated: boolean;
  username: string | null;
}

export const useMe = () => useQuery({ queryKey: keys.me, queryFn: () => api<Me>("/api/auth/me"), retry: false });

/** Before the first sign-up there is no login yet: the login screen offers to create one */
export const useAuthStatus = () =>
  useQuery({ queryKey: keys.authStatus, queryFn: () => api<{ setup_required: boolean }>("/api/auth/status") });

export const useCashFlow = (month: string) =>
  useQuery({ queryKey: keys.cashflow(month), queryFn: () => api<CashFlow>(`/api/cashflow${query({ month })}`) });

export const useHistory = () =>
  useQuery({ queryKey: keys.history, queryFn: () => api<MonthHistory[]>("/api/history") });

export const useCategories = () =>
  useQuery({
    queryKey: keys.categories,
    queryFn: () => api<Category[]>("/api/categories"),
    staleTime: 5 * 60_000,
  });

export const useRules = () => useQuery({ queryKey: keys.rules, queryFn: () => api<Rule[]>("/api/rules") });

export const useAccounts = () =>
  useQuery({ queryKey: keys.accounts, queryFn: () => api<Account[]>("/api/accounts") });

export const useSyncStatus = () =>
  useQuery({ queryKey: keys.syncStatus, queryFn: () => api<SyncStatus[]>("/api/sync-status") });

/** Polls while a sync is waiting or running; when one ends, what it fetched shows everywhere */
export function useConnections() {
  const client = useQueryClient();
  const wasSyncing = useRef(false);
  const query = useQuery({
    queryKey: keys.connections,
    queryFn: () => api<Connections>("/api/connections"),
    refetchInterval: (q) => (q.state.data?.connections.some((c) => c.sync) ? 3000 : false),
  });
  const syncing = query.data?.connections.some((c) => c.sync) ?? false;
  useEffect(() => {
    if (wasSyncing.current && !syncing) {
      // New transactions and balances: refresh everything but the connections themselves
      client.invalidateQueries({ predicate: (q) => q.queryKey[0] !== keys.connections[0] && q.queryKey[0] !== keys.me[0] });
    }
    wasSyncing.current = syncing;
  }, [syncing, client]);
  return query;
}

export function useConnectionMutations() {
  const client = useQueryClient();
  const onSuccess = () => client.invalidateQueries({ queryKey: keys.connections });
  return {
    add: useMutation({
      mutationFn: (body: { company: string; credentials: Record<string, string> }) =>
        api<Connection>("/api/connections", { method: "POST", body }),
      onSuccess,
    }),
    update: useMutation({
      mutationFn: ({ id, credentials }: { id: string; credentials: Record<string, string> }) =>
        api<Connection>(`/api/connections/${id}`, { method: "PUT", body: { credentials } }),
      onSuccess,
    }),
    remove: useMutation({
      mutationFn: (id: string) => api(`/api/connections/${id}`, { method: "DELETE" }),
      onSuccess,
    }),
    syncAll: useMutation({
      mutationFn: () => api<Connection[]>("/api/connections/sync", { method: "POST" }),
      onSuccess,
    }),
  };
}

export const useAlerts = () =>
  useQuery({ queryKey: keys.alerts, queryFn: () => api<Alert[]>("/api/alerts?limit=200") });

export const useTransactions = (params: TransactionQuery, enabled = true) =>
  useQuery({
    queryKey: keys.transactions(params),
    queryFn: () => api<Transaction[]>(`/api/transactions${query(params)}`),
    enabled,
  });

/** Everything that depends on how transactions are categorized */
function useRefreshMoney() {
  const client = useQueryClient();
  return () =>
    Promise.all(
      ["transactions", "cashflow", "history"].map((key) => client.invalidateQueries({ queryKey: [key] })),
    );
}

export function useUpdateTransaction() {
  const refresh = useRefreshMoney();
  const client = useQueryClient();
  return useMutation({
    mutationFn: ({ id, category_id, create_rule }: { id: number; category_id: number | null; create_rule: boolean }) =>
      api<TransactionUpdated>(`/api/transactions/${id}`, { method: "PATCH", body: { category_id, create_rule } }),
    onSuccess: (result) => {
      if (result.rule) client.invalidateQueries({ queryKey: keys.rules });
      return refresh();
    },
  });
}

export function useSavePlan() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: ({ month, expected_income, savings_goal }: { month: string; expected_income: string | null; savings_goal: string }) =>
      api(`/api/plans/${month}`, { method: "PUT", body: { expected_income, savings_goal } }),
    onSuccess: () => client.invalidateQueries({ queryKey: ["cashflow"] }),
  });
}

export function useSetBudget() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: ({ month, category_id, limit_amount }: { month: string; category_id: number; limit_amount: string }) =>
      api(`/api/budgets/${month}/${category_id}`, { method: "PUT", body: { limit_amount } }),
    onSuccess: () => client.invalidateQueries({ queryKey: ["cashflow"] }),
  });
}

export interface CategoryInput {
  name?: string;
  parent_id?: number | null;
  kind?: CategoryKind;
  is_fixed?: boolean;
}

export function useCategoryMutations() {
  const client = useQueryClient();
  const refresh = useRefreshMoney();
  const done = () => {
    client.invalidateQueries({ queryKey: keys.categories });
    return refresh();
  };
  return {
    create: useMutation({
      mutationFn: (body: CategoryInput) => api<Category>("/api/categories", { method: "POST", body }),
      onSuccess: done,
    }),
    update: useMutation({
      mutationFn: ({ id, ...body }: CategoryInput & { id: number }) =>
        api<Category>(`/api/categories/${id}`, { method: "PATCH", body }),
      onSuccess: done,
    }),
    remove: useMutation({
      mutationFn: (id: number) => api<void>(`/api/categories/${id}`, { method: "DELETE" }),
      onSuccess: done,
    }),
  };
}

export interface RuleInput {
  match_pattern: string;
  category_id: number;
  priority: number;
  is_regex: boolean;
}

export function useRuleMutations() {
  const client = useQueryClient();
  const refresh = useRefreshMoney();
  const done = () => {
    client.invalidateQueries({ queryKey: keys.rules });
    return refresh();
  };
  return {
    create: useMutation({
      mutationFn: (body: RuleInput) => api<Rule & { recategorized: number }>("/api/rules", { method: "POST", body }),
      onSuccess: done,
    }),
    update: useMutation({
      mutationFn: ({ id, ...body }: RuleInput & { id: number }) =>
        api<Rule & { recategorized: number }>(`/api/rules/${id}`, { method: "PATCH", body }),
      onSuccess: done,
    }),
    remove: useMutation({
      mutationFn: (id: number) => api<{ recategorized: number }>(`/api/rules/${id}`, { method: "DELETE" }),
      onSuccess: done,
    }),
  };
}

export function useAcknowledgeAlert() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (id: number) => api<Alert>(`/api/alerts/${id}/acknowledge`, { method: "POST" }),
    onSuccess: () => client.invalidateQueries({ queryKey: keys.alerts }),
  });
}

interface Credentials {
  username: string;
  password: string;
}

export function useLogin() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (body: Credentials) => api("/api/auth/login", { method: "POST", body }),
    onSuccess: () => client.resetQueries(),
  });
}

export function useSetup() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (body: Credentials) => api("/api/auth/setup", { method: "POST", body }),
    onSuccess: () => client.resetQueries(),
  });
}

export function useUpdateAccount() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (body: { current_password: string; username: string; new_password?: string }) =>
      api<Me>("/api/auth/account", { method: "PUT", body }),
    onSuccess: (me) => client.setQueryData(keys.me, me),
  });
}

export function useLogout() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: () => api("/api/auth/logout", { method: "POST" }),
    onSettled: () => {
      // null means logged out: the app shows the login screen
      client.setQueryData(keys.me, null);
      client.removeQueries({ predicate: (q) => q.queryKey[0] !== keys.me[0] });
    },
  });
}
