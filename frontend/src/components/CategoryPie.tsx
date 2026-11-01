import { useState } from "react";
import { Link } from "react-router-dom";

import { useSpending } from "../api/queries";
import type { MonthSpending } from "../api/types";
import { formatMoney, monthName, toNumber } from "../lib/format";
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

function PieRow({
  slice,
  open,
  highlighted,
  onToggle,
  onHover,
}: {
  slice: Slice;
  open: boolean;
  highlighted: boolean;
  onToggle: () => void;
  onHover: (on: boolean) => void;
}) {
  // "Other" lists its categories; a category lists its subcategories
  const detail =
    slice.categories.length > 1
      ? slice.categories.map((c) => ({ id: c.category_id, name: c.name, total: c.total }))
      : slice.categories[0].subcategories.map((c) => ({ id: c.category_id, name: c.name, total: c.total }));
  const content = (
    <>
      <i className="swatch" style={{ background: `var(${slice.color})` }} aria-hidden="true" />
      <span className="pie-row-name">{slice.name}</span>
      <span className="muted pie-row-share">{shareLabel(slice.share)}</span>
      <Money value={slice.value} decimals={0} className="pie-row-amount" />
    </>
  );
  return (
    <li className={highlighted ? "pie-row is-highlighted" : "pie-row"}>
      {detail.length > 0 ? (
        <button
          type="button"
          className="pie-row-main"
          aria-expanded={open}
          onClick={onToggle}
          onPointerEnter={(e) => e.pointerType === "mouse" && onHover(true)}
          onPointerLeave={() => onHover(false)}
        >
          {content}
        </button>
      ) : (
        <div
          className="pie-row-main"
          onPointerEnter={(e) => e.pointerType === "mouse" && onHover(true)}
          onPointerLeave={() => onHover(false)}
        >
          {content}
        </div>
      )}
      {open && detail.length > 0 && (
        <ul className="pie-sublist">
          {detail.map((d) => (
            <li key={d.id}>
              <span>{d.name}</span>
              <Money value={d.total} decimals={0} />
            </li>
          ))}
        </ul>
      )}
    </li>
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
