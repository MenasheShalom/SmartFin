import { useQueryClient } from "@tanstack/react-query";
import { useEffect } from "react";
import { Navigate, Route, Routes, useLocation } from "react-router-dom";

import { ApiError, UNAUTHORIZED_EVENT } from "./api/client";
import { keys, UNCATEGORIZED_QUERY, useMe, useTransactions } from "./api/queries";
import { Loading } from "./components/States";
import { TabBar } from "./components/TabBar";
import { AlertsScreen } from "./screens/Alerts";
import { HistoryScreen } from "./screens/History";
import { HomeScreen } from "./screens/Home";
import { LoginScreen } from "./screens/Login";
import { PlanScreen } from "./screens/Plan";
import { AccountsScreen, CategoriesScreen, RulesScreen, SettingsScreen } from "./screens/Settings";
import { TransactionsScreen } from "./screens/Transactions";
import { WeeklyScreen } from "./screens/Weekly";

const TITLES: Record<string, string> = {
  "/": "תזרים",
  "/weekly": "שבועי",
  "/history": "היסטוריה",
  "/transactions": "תנועות",
  "/plan": "תוכנית",
  "/alerts": "התראות",
  "/settings": "הגדרות",
  "/settings/categories": "קטגוריות",
  "/settings/rules": "כללי סיווג",
  "/settings/accounts": "חשבונות וסנכרון",
};

/** New screen: start at the top, and name it for the tab and screen readers */
function useScreenChange() {
  const { pathname } = useLocation();
  useEffect(() => {
    window.scrollTo(0, 0);
    document.title = TITLES[pathname] ? `${TITLES[pathname]} · SmartFin` : "SmartFin";
  }, [pathname]);
}

export function App() {
  const client = useQueryClient();
  const me = useMe();

  useEffect(() => {
    const onUnauthorized = () => client.setQueryData(keys.me, null);
    window.addEventListener(UNAUTHORIZED_EVENT, onUnauthorized);
    return () => window.removeEventListener(UNAUTHORIZED_EVENT, onUnauthorized);
  }, [client]);

  if (me.isPending) {
    return (
      <main className="screen screen--bare">
        <Loading />
      </main>
    );
  }
  const loggedOut = me.data === null || (me.error instanceof ApiError && me.error.status === 401);
  if (loggedOut || !me.data) return <LoginScreen serverError={loggedOut ? undefined : me.error} />;
  return <AuthedApp />;
}

function AuthedApp() {
  useScreenChange();
  const uncategorized = useTransactions(UNCATEGORIZED_QUERY);
  return (
    <>
      <Routes>
        <Route path="/" element={<HomeScreen />} />
        <Route path="/weekly" element={<WeeklyScreen />} />
        <Route path="/history" element={<HistoryScreen />} />
        <Route path="/transactions" element={<TransactionsScreen />} />
        <Route path="/plan" element={<PlanScreen />} />
        <Route path="/alerts" element={<AlertsScreen />} />
        <Route path="/settings" element={<SettingsScreen />} />
        <Route path="/settings/categories" element={<CategoriesScreen />} />
        <Route path="/settings/rules" element={<RulesScreen />} />
        <Route path="/settings/accounts" element={<AccountsScreen />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
      <TabBar uncategorized={uncategorized.data?.length ?? 0} />
    </>
  );
}
