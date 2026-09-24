import { Link } from "react-router-dom";

import { UNCATEGORIZED_QUERY, useAlerts, useCashFlow, useSyncStatus, useTransactions } from "../api/queries";
import type { CashFlow } from "../api/types";
import { BellIcon, ChevronEnd, GearIcon, WarningIcon } from "../components/Icons";
import { Money } from "../components/Money";
import { ProgressBar } from "../components/ProgressBar";
import { ErrorState, Loading } from "../components/States";
import { currentMonth, dayRange, greeting, monthName, toNumber } from "../lib/format";

export function HomeScreen() {
  const month = currentMonth();
  const flow = useCashFlow(month);
  const alerts = useAlerts();
  const sync = useSyncStatus();
  const uncategorized = useTransactions(UNCATEGORIZED_QUERY);

  const unread = alerts.data?.filter((a) => !a.acknowledged).length ?? 0;
  const failed = sync.data?.filter((s) => s.status === "failed") ?? [];
  const neverSynced = sync.isSuccess && sync.data.length === 0;

  return (
    <main className="screen">
      <header className="screen-header">
        <div>
          <p className="muted">{greeting()}</p>
          {flow.data && (
            <p className="muted" style={{ fontSize: 14 }}>
              {monthName(month)} · {flow.data.days_left === 0 ? "היום האחרון בחודש" : `נשארו ${flow.data.days_left} ימים`}
            </p>
          )}
        </div>
        <div className="header-actions">
          <Link to="/alerts" className="icon-button" aria-label={unread ? `התראות, ${unread} חדשות` : "התראות"}>
            <BellIcon size={20} />
            {unread > 0 && <span className="badge" aria-hidden="true">{unread}</span>}
          </Link>
          <Link to="/settings" className="icon-button" aria-label="הגדרות">
            <GearIcon size={20} />
          </Link>
        </div>
      </header>

      {failed.map((s) => (
        <Link key={s.institution} to="/settings/accounts" className="banner">
          <WarningIcon size={20} />
          <span style={{ flexGrow: 1 }}>
            הסנכרון של {s.institution_label} נכשל. התנועות ממנו לא מעודכנות.
          </span>
          <ChevronEnd size={18} />
        </Link>
      ))}

      {flow.isPending && <Loading />}
      {flow.isError && <ErrorState error={flow.error} onRetry={() => flow.refetch()} />}
      {flow.data && (
        <>
          {neverSynced && toNumber(flow.data.expected_income) === 0 && flow.data.uncategorized_count === 0 ? (
            <Welcome />
          ) : (
            <>
              <Forecast flow={flow.data} />
              <ThisWeek flow={flow.data} />
              <MonthFlow flow={flow.data} />
            </>
          )}
          {(uncategorized.data?.length ?? 0) > 0 && (
            <Link to="/transactions" className="cta">
              <span>
                {uncategorized.data!.length === 1
                  ? "תנועה אחת מחכה לסיווג"
                  : `${uncategorized.data!.length} תנועות מחכות לסיווג`}
                {flow.data.uncategorized_count > 0 && (
                  <small>
                    החישובים לא כוללים עדיין <Money value={-toNumber(flow.data.uncategorized_net)} /> מהחודש
                  </small>
                )}
              </span>
              <ChevronEnd size={18} />
            </Link>
          )}
        </>
      )}
    </main>
  );
}

function Welcome() {
  return (
    <section className="card">
      <h1 className="card-title">ברוכים הבאים ל־SmartFin</h1>
      <p className="muted">
        עדיין אין כאן נתונים. אחרי הסנכרון הראשון עם הבנק וחברות האשראי תראו כאן את התזרים שלכם: כמה נשאר לשבוע,
        ומה הצפי לסוף החודש.
      </p>
      <Link to="/settings/accounts" className="button button--secondary">
        לחשבונות ולסנכרון
      </Link>
    </section>
  );
}

function Forecast({ flow }: { flow: CashFlow }) {
  const forecast = toNumber(flow.forecast);
  return (
    <section className="hero" aria-labelledby="forecast-label">
      <h1 id="forecast-label" className="hero-label" style={{ fontWeight: 400 }}>
        צפי לסוף החודש
      </h1>
      <div className="hero-value">
        <Money value={flow.forecast} sign="always" decimals={0} />
      </div>
      {toNumber(flow.savings_goal) > 0 && (
        <p className="hero-label">
          אחרי חיסכון של <Money value={flow.savings_goal} decimals={0} /> שכבר בתוכנית
        </p>
      )}
      <span className={forecast >= 0 ? "pill" : "pill pill--warn"}>{forecast >= 0 ? "בדרך הנכונה" : "צפי לגירעון"}</span>
    </section>
  );
}

function ThisWeek({ flow }: { flow: CashFlow }) {
  const week = flow.weeks.find((w) => w.is_current);
  if (!week) return null;
  if (toNumber(flow.variable_budget) <= 0) {
    return (
      <section className="card">
        <h2 className="card-title">השבוע</h2>
        <p className="muted">
          לפי התוכנית לא נשאר החודש כסף להוצאות משתנות.{" "}
          <Link to="/plan">לעדכון התוכנית</Link>
        </p>
      </section>
    );
  }
  const remaining = toNumber(week.remaining);
  const endsSaturday = new Date(`${week.end}T12:00:00Z`).getUTCDay() === 6;
  return (
    <Link to="/weekly" className="card" style={{ textDecoration: "none" }}>
      <div className="card-row">
        <h2 className="card-title">{remaining >= 0 ? "נשאר לך השבוע" : "חרגת השבוע"}</h2>
        <span className="muted" style={{ fontSize: 13 }}>
          {dayRange(week.start, week.end)} ב{monthName(flow.month)}
        </span>
      </div>
      <div style={{ display: "flex", alignItems: "baseline", gap: 8, flexWrap: "wrap" }}>
        <span className={`big-number ${remaining >= 0 ? "pos" : "neg"}`}>
          <Money value={Math.abs(remaining)} decimals={0} />
        </span>
        <span className="muted" style={{ fontSize: 15 }}>
          מתוך <Money value={week.budget} decimals={0} /> להוצאות משתנות
        </span>
      </div>
      <ProgressBar value={week.spent} max={week.budget} size="thick" label="הוצאות השבוע מתוך התקציב" />
      {remaining > 0 && flow.current_week_per_day && (
        <p className="muted" style={{ fontSize: 14 }}>
          כ־<Money value={flow.current_week_per_day} decimals={0} /> ליום {endsSaturday ? "עד מוצאי שבת" : "עד סוף החודש"}
        </p>
      )}
    </Link>
  );
}

function MonthFlow({ flow }: { flow: CashFlow }) {
  return (
    <Link to="/plan" className="card card--tight" style={{ textDecoration: "none", gap: 12 }}>
      <h2 className="card-title">התזרים של {monthName(flow.month)}</h2>
      <div className="flow-line">
        <div className="card-row">
          <span>הכנסות{flow.income_is_estimate && <span className="muted" style={{ fontSize: 13 }}> · צפי משוער</span>}</span>
          <span style={{ fontWeight: 500 }}>
            <Money value={flow.income_received} decimals={0} /> / <Money value={flow.expected_income} decimals={0} />
          </span>
        </div>
        <ProgressBar value={flow.income_received} max={flow.expected_income} size="thin" tone="income" label="הכנסות שהתקבלו" />
      </div>
      <div className="flow-line">
        <div className="card-row">
          <span>הוצאות קבועות</span>
          <span style={{ fontWeight: 500 }}>
            <Money value={flow.fixed_paid} decimals={0} /> / <Money value={flow.fixed_expected} decimals={0} />
          </span>
        </div>
        <ProgressBar value={flow.fixed_paid} max={flow.fixed_expected} size="thin" tone="muted" label="הוצאות קבועות ששולמו" />
      </div>
      <div className="flow-line">
        <div className="card-row">
          <span>הוצאות משתנות</span>
          <span style={{ fontWeight: 500 }}>
            <Money value={flow.variable_spent} decimals={0} /> / <Money value={Math.max(0, toNumber(flow.variable_budget))} decimals={0} />
          </span>
        </div>
        <ProgressBar value={flow.variable_spent} max={Math.max(0, toNumber(flow.variable_budget))} size="thin" label="הוצאות משתנות מתוך התקציב" />
      </div>
    </Link>
  );
}
