import { useState } from "react";
import { Link } from "react-router-dom";

import { errorMessage } from "../api/client";
import { useCashFlow, useSavePlan, useSetBudget } from "../api/queries";
import type { CashFlow, FixedItem } from "../api/types";
import { PencilIcon } from "../components/Icons";
import { Money } from "../components/Money";
import { MoneyInput, toAmount } from "../components/MoneyInput";
import { MonthSwitcher } from "../components/MonthSwitcher";
import { Sheet } from "../components/Sheet";
import { EmptyState, ErrorState, Loading } from "../components/States";
import { useToast } from "../components/Toast";
import { currentMonth, formatMoney, monthName, toNumber } from "../lib/format";

type Editing = { kind: "income" } | { kind: "savings" } | { kind: "fixed"; item: FixedItem } | null;

export function PlanScreen() {
  const [month, setMonth] = useState(currentMonth());
  const flow = useCashFlow(month);
  const [editing, setEditing] = useState<Editing>(null);

  return (
    <main className="screen">
      <header>
        <h1 className="screen-title">התוכנית של {monthName(month)}</h1>
        <p className="screen-subtitle">מה נכנס, מה יוצא בטוח, ומה נשאר לחיים</p>
      </header>
      <MonthSwitcher month={month} onChange={setMonth} />
      {flow.isPending && <Loading rows={4} />}
      {flow.isError && <ErrorState error={flow.error} onRetry={() => flow.refetch()} />}
      {flow.data && <PlanBody flow={flow.data} onEdit={setEditing} />}
      {editing && flow.data && <EditSheet editing={editing} flow={flow.data} onClose={() => setEditing(null)} />}
    </main>
  );
}

function PlanBody({ flow, onEdit }: { flow: CashFlow; onEdit: (e: Editing) => void }) {
  const variable = toNumber(flow.variable_budget);
  const perWeek = (Math.max(0, variable) * 7) / flow.days_in_month;
  return (
    <>
      <section className="card card--flush">
        <div className="card-row" style={{ padding: "16px 18px", alignItems: "center" }}>
          <span className="card-title" style={{ fontSize: 16 }}>הכנסות צפויות</span>
          <span style={{ display: "flex", alignItems: "center", gap: 10 }}>
            <span className="pos" style={{ fontSize: 18, fontWeight: 800 }}>
              <Money value={flow.expected_income} sign="always" decimals={0} />
            </span>
            <button type="button" className="icon-button icon-button--outline" aria-label="עריכת ההכנסות הצפויות" onClick={() => onEdit({ kind: "income" })}>
              <PencilIcon size={18} />
            </button>
          </span>
        </div>
        <div className="list-row" style={{ minHeight: 0, fontSize: 14 }}>
          <span className="muted">
            {flow.income_is_estimate ? "הערכה לפי ממוצע שלושת החודשים האחרונים" : "לפי מה שקבעת"}
          </span>
          <span className="muted">
            התקבל <Money value={flow.income_received} decimals={0} />
          </span>
        </div>
      </section>

      <section className="card card--flush">
        <div className="card-row" style={{ padding: "16px 18px" }}>
          <h2 className="card-title" style={{ fontSize: 16 }}>הוצאות קבועות</h2>
          <span style={{ fontSize: 18, fontWeight: 800 }}>
            <Money value={-toNumber(flow.fixed_expected)} decimals={0} />
          </span>
        </div>
        {flow.fixed_items.length === 0 ? (
          <p className="list-row muted" style={{ fontSize: 14 }}>
            עוד אין הוצאות קבועות. סמנו קטגוריות כקבועות (שכירות, ביטוחים, מנויים) בהגדרות.
          </p>
        ) : (
          <div className="list">
            {flow.fixed_items.map((item) => (
              <button key={item.category_id} type="button" className="list-row" onClick={() => onEdit({ kind: "fixed", item })}>
                <span className="list-row-main">
                  <span className="list-row-title">{item.name}</span>
                  <span className={`list-row-sub${item.status === "paid" ? " pos" : ""}`}>
                    {item.status === "paid" ? "שולם" : item.status === "partial" ? <>שולם חלקית · <Money value={item.paid} decimals={0} /></> : "צפוי"}
                  </span>
                </span>
                <span className="list-row-end">
                  <Money value={Math.max(toNumber(item.expected), toNumber(item.paid))} decimals={0} />
                </span>
              </button>
            ))}
          </div>
        )}
        <Link to="/settings/categories" className="list-row" style={{ minHeight: 48, fontSize: 14, fontWeight: 700 }}>
          איזה קטגוריות נחשבות קבועות?
        </Link>
      </section>

      <section className="card" style={{ flexDirection: "row", justifyContent: "space-between", alignItems: "center" }}>
        <span className="card-title" style={{ fontSize: 16 }}>חיסכון חודשי</span>
        <span style={{ display: "flex", alignItems: "center", gap: 10 }}>
          <span style={{ fontSize: 18, fontWeight: 800 }}>
            <Money value={-toNumber(flow.savings_goal)} decimals={0} />
          </span>
          <button type="button" className="icon-button icon-button--outline" aria-label="עריכת החיסכון החודשי" onClick={() => onEdit({ kind: "savings" })}>
            <PencilIcon size={18} />
          </button>
        </span>
      </section>

      {variable >= 0 ? (
        <section className="hero" style={{ gap: 6 }}>
          <h2 className="hero-label" style={{ fontWeight: 400 }}>נשאר להוצאות משתנות</h2>
          <div style={{ display: "flex", alignItems: "baseline", gap: 10, flexWrap: "wrap" }}>
            <span className="hero-value hero-value--m">
              <Money value={variable} decimals={0} />
            </span>
            <span className="hero-label">
              ≈ <Money value={perWeek} decimals={0} /> לשבוע
            </span>
          </div>
        </section>
      ) : (
        <EmptyState
          title={`התוכנית בגירעון של ${formatMoney(-variable, { decimals: 0 })}`}
          body="ההוצאות הקבועות והחיסכון גבוהים מההכנסות הצפויות. אפשר להקטין את החיסכון או לבדוק את ההוצאות הקבועות."
        />
      )}
    </>
  );
}

function EditSheet({ editing, flow, onClose }: { editing: NonNullable<Editing>; flow: CashFlow; onClose: () => void }) {
  const savePlan = useSavePlan();
  const setBudget = useSetBudget();
  const toast = useToast();
  const initial =
    editing.kind === "income"
      ? flow.income_is_estimate
        ? ""
        : String(toNumber(flow.expected_income))
      : editing.kind === "savings"
        ? toNumber(flow.savings_goal) > 0
          ? String(toNumber(flow.savings_goal))
          : ""
        : String(toNumber(editing.item.expected));
  const [value, setValue] = useState(initial);
  const pending = savePlan.isPending || setBudget.isPending;
  const done = { onSuccess: () => { toast("התוכנית עודכנה."); onClose(); }, onError: (e: unknown) => toast(errorMessage(e)) };
  const currentIncome = flow.income_is_estimate ? null : flow.expected_income;

  const submit = () => {
    if (editing.kind === "income") {
      savePlan.mutate({ month: flow.month, expected_income: toAmount(value), savings_goal: flow.savings_goal }, done);
    } else if (editing.kind === "savings") {
      savePlan.mutate({ month: flow.month, expected_income: currentIncome, savings_goal: toAmount(value) ?? "0.00" }, done);
    } else {
      setBudget.mutate({ month: flow.month, category_id: editing.item.category_id, limit_amount: toAmount(value) ?? "0.00" }, done);
    }
  };

  const title = editing.kind === "income" ? "הכנסות צפויות" : editing.kind === "savings" ? "חיסכון חודשי" : editing.item.name;
  const hint =
    editing.kind === "income"
      ? `השאירו ריק כדי לחשב אוטומטית (כרגע ${formatMoney(flow.expected_income, { decimals: 0 })}).`
      : editing.kind === "savings"
        ? "הסכום נשמר בצד לפני שמחשבים את התקציב השבועי."
        : "הסכום הצפוי לחודש הזה. ברירת המחדל היא מה ששולם בחודש הקודם.";

  return (
    <Sheet title={title} onClose={onClose}>
      <form
        style={{ display: "flex", flexDirection: "column", gap: 14 }}
        onSubmit={(e) => {
          e.preventDefault();
          submit();
        }}
      >
        <MoneyInput label={`סכום ל${monthName(flow.month)} (₪)`} value={value} onChange={setValue} hint={hint} />
        <button type="submit" className="button" disabled={pending}>
          {pending ? "שומר…" : "שמירה"}
        </button>
      </form>
    </Sheet>
  );
}
