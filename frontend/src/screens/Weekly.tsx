import { useState } from "react";

import { useCashFlow, useCategories, useTransactions } from "../api/queries";
import type { Week } from "../api/types";
import { Money } from "../components/Money";
import { MonthSwitcher } from "../components/MonthSwitcher";
import { ProgressBar } from "../components/ProgressBar";
import { EmptyState, ErrorState, Loading } from "../components/States";
import { TransactionRow } from "../components/TransactionRow";
import { byId, isVariable } from "../lib/categories";
import { currentMonth, dayRange, toNumber } from "../lib/format";

export function WeeklyScreen() {
  const [month, setMonth] = useState(currentMonth());
  const flow = useCashFlow(month);
  const [open, setOpen] = useState<string | null>(null);

  const weeks = flow.data?.weeks ?? [];
  const openWeek = open ?? weeks.find((w) => w.is_current)?.start ?? null;
  const days = flow.data?.days_in_month ?? 30;

  return (
    <main className="screen">
      <header>
        <h1 className="screen-title">הוצאות משתנות</h1>
        {flow.data && (
          <p className="screen-subtitle">
            <Money value={flow.data.variable_spent} decimals={0} /> מתוך{" "}
            <Money value={Math.max(0, toNumber(flow.data.variable_budget))} decimals={0} /> לחודש · כ־
            <Money value={(Math.max(0, toNumber(flow.data.variable_budget)) * 7) / days} decimals={0} /> לשבוע
          </p>
        )}
      </header>
      <MonthSwitcher month={month} onChange={(m) => { setMonth(m); setOpen(null); }} />

      {flow.isPending && <Loading rows={4} />}
      {flow.isError && <ErrorState error={flow.error} onRetry={() => flow.refetch()} />}
      {flow.data && toNumber(flow.data.variable_budget) <= 0 && (
        <EmptyState title="אין תקציב להוצאות משתנות" body="לפי התוכנית, ההכנסות החודש מכסות רק את ההוצאות הקבועות והחיסכון. אפשר לעדכן את התוכנית בלשונית ״תוכנית״." />
      )}
      {flow.data &&
        weeks.map((week, index) => (
          <WeekCard
            key={week.start}
            week={week}
            index={index + 1}
            open={openWeek === week.start}
            onToggle={() => setOpen(openWeek === week.start ? "" : week.start)}
          />
        ))}
    </main>
  );
}

function WeekCard({ week, index, open, onToggle }: { week: Week; index: number; open: boolean; onToggle: () => void }) {
  const future = !week.is_past && !week.is_current;
  const remaining = toNumber(week.remaining);
  const title = `${week.is_current ? "השבוע" : `שבוע ${index}`} · ${dayRange(week.start, week.end)}`;

  if (future) {
    return (
      <section className="card week week--future">
        <div className="card-row" style={{ fontSize: 15 }}>
          <span>{title}</span>
          <span className="muted">
            <Money value={week.budget} decimals={0} /> מתוכנן
          </span>
        </div>
      </section>
    );
  }

  return (
    <section className={`card week${week.is_current ? " week--current" : ""}`}>
      <button type="button" className="week-toggle" onClick={onToggle} aria-expanded={open}>
        <span className="card-row" style={{ width: "100%", fontSize: 15 }}>
          <span style={{ fontWeight: week.is_current ? 700 : 500 }}>{title}</span>
          {week.is_current ? (
            <span style={{ fontWeight: 700 }}>
              <Money value={Math.abs(remaining)} decimals={0} /> {remaining >= 0 ? "נשאר" : "חריגה"}
            </span>
          ) : (
            <span className={remaining >= 0 ? "pos" : "neg"} style={{ fontWeight: 700 }}>
              <Money value={remaining} sign="always" decimals={0} />
            </span>
          )}
        </span>
        <span style={{ width: "100%" }}>
          <ProgressBar value={week.spent} max={week.budget} tone={week.is_current ? "default" : "muted"} label={`הוצאות ${title}`} />
        </span>
        <span className={remaining < 0 ? "neg" : "muted"} style={{ fontSize: 13 }}>
          <Money value={week.spent} decimals={0} /> מתוך <Money value={week.budget} decimals={0} />
        </span>
      </button>
      {open && <WeekTransactions week={week} />}
    </section>
  );
}

function WeekTransactions({ week }: { week: Week }) {
  const categories = useCategories();
  const txns = useTransactions({ date_from: week.start, date_to: week.end, limit: 500 });
  const map = byId(categories.data);
  if (txns.isPending || categories.isPending) return <p className="muted">טוען…</p>;
  if (txns.isError) return <ErrorState error={txns.error} onRetry={() => txns.refetch()} />;
  const rows = txns.data.filter((t) => isVariable(t.category_id, map) || t.category_id === null);
  if (rows.length === 0) return <p className="muted" style={{ fontSize: 14 }}>אין הוצאות משתנות בשבוע הזה.</p>;
  return (
    <div className="list" style={{ margin: "0 -18px -18px" }}>
      {rows.map((t) => (
        <TransactionRow key={t.id} txn={t} categories={map} />
      ))}
    </div>
  );
}
