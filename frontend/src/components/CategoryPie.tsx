import { useState } from "react";
import { Link } from "react-router-dom";

import { useSpending, useTransactions } from "../api/queries";
import type { MonthSpending } from "../api/types";
import { formatMoney, formatShortDay, israelToday, monthName, toNumber } from "../lib/format";
import { buildSlices, byAmount, donutSegment, shareLabel, sliceAngles, type Slice } from "../lib/pie";
import { ChevronEnd } from "./Icons";
import { Money } from "./Money";
import { ErrorState, Loading } from "./States";

const SIZE = 200;
const C = SIZE / 2;
const OUTER = 96;
const INNER = 62;

/** The month's spending by category: a donut, and the same figures as a list beside it. */
export function CategorySpending({ month }: { month: string }) {
  const spending = useSpending(month);
  return (
    <section className="card" aria-labelledby="by-category-title">
      <div className="card-row">
        <h2 id="by-category-title" className="card-title">
          לאן הלך הכסף
        </h2>
        <span className="muted" style={{ fontSize: 13 }}>
          {monthName(month)}
        </span>
      </div>
      {spending.isPending && <Loading rows={1} />}
      {spending.isError && <ErrorState error={spending.error} onRetry={() => spending.refetch()} />}
      {/* Keyed by month, so a new month starts with nothing selected */}
      {spending.data && <PieBody key={month} data={spending.data} />}
    </section>
  );
}

function PieBody({ data }: { data: MonthSpending }) {
  const slices = buildSlices(data.categories);
  const angles = sliceAngles(slices);
  const [active, setActive] = useState<number | null>(null);
  const [hover, setHover] = useState<number | null>(null);
  const focus = hover ?? active;
  const focused = slices.find((s) => s.id === focus) ?? null;
  const uncategorized = toNumber(data.uncategorized);

  if (slices.length === 0) {
    return (
      <>
        <p className="muted">אין החודש הוצאות מסווגות.</p>
        {uncategorized > 0 && <UncategorizedNote amount={data.uncategorized} />}
      </>
    );
  }

  const toggle = (id: number) => setActive(active === id ? null : id);

  return (
    <>
      <div className="pie-layout">
        <svg
          className="pie"
          viewBox={`0 0 ${SIZE} ${SIZE}`}
          role="img"
          aria-label={`הוצאות ${data.month} לפי קטגוריה`}
          onPointerLeave={() => setHover(null)}
        >
          {slices.map((s, i) => (
            <path
              key={s.id}
              d={donutSegment(C, C, OUTER, INNER, angles[i].start, angles[i].end)}
              fill={`var(${s.color})`}
              fillRule="evenodd"
              className={focus !== null && focus !== s.id ? "pie-slice is-dimmed" : "pie-slice"}
              onPointerEnter={(e) => e.pointerType === "mouse" && setHover(s.id)}
              onClick={() => toggle(s.id)}
            >
              <title>{`${s.name}: ${shareLabel(s.share)}`}</title>
            </path>
          ))}
          <text x={C} y={C - 8} textAnchor="middle" className="pie-center-label">
            {focused ? focused.name : "סה״כ"}
          </text>
          <text x={C} y={C + 16} textAnchor="middle" className="pie-center-value">
            {focused ? shareLabel(focused.share) : formatMoney(data.total, { decimals: 0 })}
          </text>
        </svg>

        <ul className="pie-list">
          {byAmount(slices).map((s) => (
            <PieRow
              key={s.id}
              month={data.month}
              slice={s}
              open={active === s.id}
              highlighted={focus === s.id}
              onToggle={() => toggle(s.id)}
              onHover={(on) => setHover(on ? s.id : null)}
            />
          ))}
        </ul>
      </div>
      {uncategorized > 0 && <UncategorizedNote amount={data.uncategorized} />}
    </>
  );
}

/** A line under an open category: a subcategory, a category inside "other", or the money filed
 * on the category itself. Tapping it lists its transactions. */
interface Detail {
  id: number;
  name: string;
  total: string | number;
  /** Only transactions filed on this category, not on its subcategories */
  exact: boolean;
}

function details(slice: Slice): Detail[] {
  // "Other" lists its categories
  if (slice.categories.length > 1) {
    return slice.categories.map((c) => ({ id: c.category_id, name: c.name, total: c.total, exact: false }));
  }
  const category = slice.categories[0];
  if (category.subcategories.length === 0) return [];
  const lines: Detail[] = category.subcategories.map((c) => ({ id: c.category_id, name: c.name, total: c.total, exact: false }));
  // Money filed on the category itself, so the lines add up to the category
  const direct = toNumber(category.total) - category.subcategories.reduce((sum, c) => sum + toNumber(c.total), 0);
  if (direct >= 0.5) lines.push({ id: category.category_id, name: `${category.name} (כללי)`, total: direct, exact: true });
  return lines;
}

function PieRow({
  slice,
  month,
  open,
  highlighted,
  onToggle,
  onHover,
}: {
  slice: Slice;
  month: string;
  open: boolean;
  highlighted: boolean;
  onToggle: () => void;
  onHover: (on: boolean) => void;
}) {
  const detail = details(slice);
  const [openDetail, setOpenDetail] = useState<string | null>(null);
  const keyOf = (d: Detail) => `${d.id}${d.exact ? "-exact" : ""}`;
  return (
    <li className={highlighted ? "pie-row is-highlighted" : "pie-row"}>
      <button
        type="button"
        className="pie-row-main"
        aria-expanded={open}
        onClick={onToggle}
        onPointerEnter={(e) => e.pointerType === "mouse" && onHover(true)}
        onPointerLeave={() => onHover(false)}
      >
        <i className="swatch" style={{ background: `var(${slice.color})` }} aria-hidden="true" />
        <span className="pie-row-name">{slice.name}</span>
        <span className="muted pie-row-share">{shareLabel(slice.share)}</span>
        <Money value={slice.value} decimals={0} className="pie-row-amount" />
      </button>
      {open &&
        (detail.length > 0 ? (
          <ul className="pie-sublist">
            {detail.map((d) => {
              const isOpen = openDetail === keyOf(d);
              return (
                <li key={keyOf(d)}>
                  <button
                    type="button"
                    className="pie-sub-main"
                    aria-expanded={isOpen}
                    onClick={() => setOpenDetail(isOpen ? null : keyOf(d))}
                  >
                    <span>{d.name}</span>
                    <Money value={d.total} decimals={0} />
                  </button>
                  {isOpen && <CategoryTransactions month={month} categoryId={d.id} exact={d.exact} />}
                </li>
              );
            })}
          </ul>
        ) : (
          // No subcategories: the category's own transactions
          <CategoryTransactions month={month} categoryId={slice.categories[0].category_id} exact={false} />
        ))}
    </li>
  );
}

/** The month's transactions in a category (and its subcategories unless exact), up to today,
 * as the pie counts them */
function CategoryTransactions({ month, categoryId, exact }: { month: string; categoryId: number; exact: boolean }) {
  const txns = useTransactions({ month, category_id: categoryId, limit: 500 });
  if (txns.isPending) return <p className="muted pie-txns-note">טוען…</p>;
  if (txns.isError) return <ErrorState error={txns.error} onRetry={() => txns.refetch()} />;
  const today = israelToday();
  const rows = txns.data.filter((t) => t.date <= today && (!exact || t.category_id === categoryId));
  if (rows.length === 0) return <p className="muted pie-txns-note">אין תנועות.</p>;
  return (
    <ul className="pie-txns" aria-label="תנועות">
      {rows.map((t) => {
        const amount = toNumber(t.amount);
        return (
          <li key={t.id}>
            <span className="pie-txn-main">
              <span className="pie-txn-title">{t.description}</span>
              <span className="pie-txn-date">{formatShortDay(t.date)}</span>
            </span>
            <Money value={t.amount} decimals={2} className={amount > 0 ? "pos" : undefined} sign={amount > 0 ? "always" : "auto"} />
          </li>
        );
      })}
    </ul>
  );
}

function UncategorizedNote({ amount }: { amount: string }) {
  return (
    <Link to="/transactions" className="pie-note">
      <span>
        עוד <Money value={amount} decimals={0} /> בתנועות שלא סווגו לא נכללים בגרף
      </span>
      <ChevronEnd size={16} />
    </Link>
  );
}
