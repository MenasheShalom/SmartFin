import { useEffect, useState, type KeyboardEvent } from "react";

import { useHistory } from "../api/queries";
import type { MonthHistory } from "../api/types";
import { HistoryChart } from "../components/HistoryChart";
import { ChevronLeft, ChevronRight } from "../components/Icons";
import { Money } from "../components/Money";
import { EmptyState, ErrorState, Loading } from "../components/States";
import { clampEnd } from "../lib/chart";
import { monthLabel, toNumber } from "../lib/format";
import { useMediaQuery } from "../lib/useMediaQuery";

export function HistoryScreen() {
  const history = useHistory();
  const wide = useMediaQuery("(min-width: 900px)");
  const size = wide ? 12 : 6;
  const months = history.data ?? [];
  const last = months.length - 1;

  const [end, setEnd] = useState<number | null>(null);
  const [selected, setSelected] = useState<number | null>(null);
  const [asTable, setAsTable] = useState(false);

  useEffect(() => {
    if (months.length && end === null) {
      setEnd(last);
      setSelected(last);
    }
  }, [months.length, end, last]);

  const windowEnd = clampEnd(end ?? last, months.length, size);
  const windowStart = Math.max(0, windowEnd - size + 1);
  const sel = Math.min(Math.max(selected ?? last, windowStart), windowEnd);

  const shift = (delta: number) => {
    const next = clampEnd(windowEnd + delta, months.length, size);
    setEnd(next);
    const nextStart = Math.max(0, next - size + 1);
    setSelected(Math.min(Math.max(sel, nextStart), next));
  };

  const onKeyDown = (e: KeyboardEvent) => {
    // The chart reads left to right: left is older
    if (e.key === "ArrowLeft") {
      e.preventDefault();
      if (sel > 0) {
        setSelected(sel - 1);
        if (sel - 1 < windowStart) shift(-1);
      }
    } else if (e.key === "ArrowRight") {
      e.preventDefault();
      if (sel < last) {
        setSelected(sel + 1);
        if (sel + 1 > windowEnd) shift(1);
      }
    }
  };

  return (
    <main className="screen">
      <header>
        <h1 className="screen-title">היסטוריה</h1>
        <p className="screen-subtitle">הכנסות, הוצאות ויתרה חודש אחר חודש</p>
      </header>

      {history.isPending && <Loading rows={2} />}
      {history.isError && <ErrorState error={history.error} onRetry={() => history.refetch()} />}
      {history.data && months.length === 0 && (
        <EmptyState title="עוד אין היסטוריה" body="הגרף יתמלא אחרי הסנכרון הראשון. כדי לראות חודשים קודמים, אפשר להריץ סנכרון ראשון עם SCRAPER_DAYS_BACK גדול." />
      )}
      {months.length > 0 && (
        <>
          <section className="card" aria-label="גרף היסטוריה">
            <div className="month-switcher" dir="ltr">
              <button type="button" className="icon-button icon-button--outline" onClick={() => shift(-1)} disabled={windowStart === 0} aria-label="חודשים קודמים">
                <ChevronLeft size={20} />
              </button>
              <div className="month-switcher-label" dir="rtl" aria-live="polite">
                {monthLabel(months[windowStart].month)} – {monthLabel(months[windowEnd].month)}
              </div>
              <button type="button" className="icon-button icon-button--outline" onClick={() => shift(1)} disabled={windowEnd === last} aria-label="חודשים מאוחרים יותר">
                <ChevronRight size={20} />
              </button>
            </div>
            <div className="card-row" style={{ alignItems: "center" }}>
              <div className="legend">
                <span>
                  <i className="swatch" style={{ background: "var(--income)" }} />
                  הכנסות
                </span>
                <span>
                  <i className="swatch" style={{ background: "var(--expense)" }} />
                  הוצאות
                </span>
              </div>
              <button type="button" className="link-button" onClick={() => setAsTable(!asTable)} aria-pressed={asTable}>
                {asTable ? "הצג כגרף" : "הצג כטבלה"}
              </button>
            </div>
            {asTable ? (
              <HistoryTable months={months.slice(windowStart, windowEnd + 1)} />
            ) : (
              <div tabIndex={0} onKeyDown={onKeyDown} aria-label="חיצים ימינה ושמאלה לבחירת חודש" style={{ borderRadius: 12 }}>
                <HistoryChart all={months} start={windowStart} end={windowEnd} selected={sel} onSelect={setSelected} onShift={shift} />
              </div>
            )}
          </section>
          <MonthDetails month={months[sel]} />
        </>
      )}
    </main>
  );
}

function MonthDetails({ month }: { month: MonthHistory }) {
  const net = toNumber(month.net);
  return (
    <section className="details" aria-live="polite">
      <h2 className="details-title">
        <span>{monthLabel(month.month)}</span>
        {month.partial && <span style={{ fontSize: 13, fontWeight: 400, color: "var(--on-primary-muted)" }}>עד היום</span>}
      </h2>
      <dl style={{ display: "contents" }}>
        <div>
          <dt>הכנסות</dt>
          <dd>
            <Money value={month.income} decimals={0} />
          </dd>
        </div>
        <div>
          <dt>הוצאות</dt>
          <dd>
            <Money value={month.expenses} decimals={0} />
          </dd>
        </div>
        <div>
          <dt>{net >= 0 ? "נשאר בפלוס" : "גירעון"}</dt>
          <dd style={{ color: net >= 0 ? "#DDF3A5" : "#FFC4A8" }}>
            <Money value={month.net} sign="always" decimals={0} />
          </dd>
        </div>
        <div>
          <dt>יתרה בסוף החודש</dt>
          <dd>{month.balance === null ? "—" : <Money value={month.balance} decimals={0} />}</dd>
        </div>
      </dl>
    </section>
  );
}

function HistoryTable({ months }: { months: MonthHistory[] }) {
  return (
    <table className="table">
      <thead>
        <tr>
          <th scope="col">חודש</th>
          <th scope="col">הכנסות</th>
          <th scope="col">הוצאות</th>
          <th scope="col">יתרה</th>
        </tr>
      </thead>
      <tbody>
        {[...months].reverse().map((m) => (
          <tr key={m.month}>
            <th scope="row" style={{ fontWeight: 500, color: "var(--ink)" }}>
              {monthLabel(m.month)}
            </th>
            <td>
              <Money value={m.income} decimals={0} />
            </td>
            <td>
              <Money value={m.expenses} decimals={0} />
            </td>
            <td>{m.balance === null ? "—" : <Money value={m.balance} decimals={0} />}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}
