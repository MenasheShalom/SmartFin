import { useRef, type PointerEvent } from "react";

import type { MonthHistory } from "../api/types";
import { barPath, historyScales, shortAmount } from "../lib/chart";
import { monthLabel, parseMonth, shortMonthLabel, toNumber } from "../lib/format";

const W = 354;
const X0 = 38;
const PLOT_W = W - X0;
const BAR_TOP = 8;
const BAR_BASE = 190;
const BAL_TOP = 12;
const BAL_BASE = 92;

interface Props {
  all: MonthHistory[];
  start: number;
  end: number;
  selected: number;
  onSelect: (index: number) => void;
  onShift: (delta: number) => void;
}

/** Income and expense bars, and the end-of-month balance line below, on fixed scales. */
export function HistoryChart({ all, start, end, selected, onSelect, onShift }: Props) {
  const scales = historyScales(all);
  const visible = all.slice(start, end + 1);
  const slot = PLOT_W / visible.length;
  const barW = Math.min(16, slot / 2 - 4);
  const dragStart = useRef<number | null>(null);

  const barY = (v: number) => BAR_BASE - (v / scales.bars.max) * (BAR_BASE - BAR_TOP);
  const balRange = scales.balance.max - scales.balance.min || 1;
  const balY = (v: number) => BAL_BASE - ((v - scales.balance.min) / balRange) * (BAL_BASE - BAL_TOP);
  const cx = (i: number) => X0 + slot * i + slot / 2;

  // Swipe: dragging right shows older months (the chart reads left to right)
  const onPointerDown = (e: PointerEvent) => {
    dragStart.current = e.clientX;
  };
  const onPointerUp = (e: PointerEvent) => {
    if (dragStart.current === null) return;
    const dx = e.clientX - dragStart.current;
    dragStart.current = null;
    if (Math.abs(dx) > 40) onShift(dx > 0 ? -Math.max(1, Math.round(Math.abs(dx) / slot)) : Math.max(1, Math.round(Math.abs(dx) / slot)));
  };

  const points = visible
    .map((m, i) => (m.balance === null ? null : `${cx(i).toFixed(1)},${balY(toNumber(m.balance)).toFixed(1)}`))
    .reduce<string[][]>(
      (runs, p) => {
        if (p === null) runs.push([]);
        else runs[runs.length - 1].push(p);
        return runs;
      },
      [[]],
    )
    .filter((run) => run.length > 0);

  const column = (i: number, height: number) => (
    <rect
      className="col-hit"
      x={cx(i) - slot / 2 + 2}
      y={0}
      width={slot - 4}
      height={height}
      rx={10}
      onClick={() => onSelect(start + i)}
      aria-hidden="true"
    />
  );

  return (
    <div onPointerDown={onPointerDown} onPointerUp={onPointerUp} onPointerCancel={() => (dragStart.current = null)} dir="ltr">
      <svg className="chart" viewBox={`0 0 ${W} 228`} role="img" aria-label="הכנסות והוצאות לפי חודש">
        {scales.bars.ticks.map((t) => (
          <g key={t}>
            <line className="axis-line" x1={X0} x2={W} y1={barY(t)} y2={barY(t)} />
            <text x={0} y={barY(t) + 4} fontSize={11}>
              {shortAmount(t)}
            </text>
          </g>
        ))}
        {visible.map((m, i) => {
          const isSel = start + i === selected;
          const { month, year } = parseMonth(m.month);
          const showYear = i === 0 || month === 1;
          return (
            <g key={m.month}>
              {isSel && <rect x={cx(i) - slot / 2 + 2} y={2} width={slot - 4} height={BAR_BASE - 2} rx={10} fill="var(--selected-column)" />}
              <path d={barPath(cx(i) - barW - 1, barW, (toNumber(m.income) / scales.bars.max) * (BAR_BASE - BAR_TOP), BAR_BASE)} fill="var(--income)" />
              <path d={barPath(cx(i) + 1, barW, (toNumber(m.expenses) / scales.bars.max) * (BAR_BASE - BAR_TOP), BAR_BASE)} fill="var(--expense)" />
              <text x={cx(i)} y={207} fontSize={12} textAnchor="middle" style={{ fill: isSel ? "var(--ink)" : undefined, fontWeight: isSel ? 700 : 400 }}>
                {shortMonthLabel(m.month)}
              </text>
              {showYear && (
                <text x={cx(i)} y={222} fontSize={10} textAnchor="middle">
                  {year}
                </text>
              )}
              {column(i, 228)}
            </g>
          );
        })}
      </svg>

      <div className="card-row" style={{ fontSize: 14, margin: "10px 0 4px" }} dir="rtl">
        <span style={{ fontWeight: 700 }}>יתרה בסוף החודש</span>
        <span className="muted">חשבונות הבנק</span>
      </div>
      <svg className="chart" viewBox={`0 0 ${W} 104`} role="img" aria-label="יתרה בסוף כל חודש">
        {[scales.balance.min, (scales.balance.min + scales.balance.max) / 2, scales.balance.max].map((t) => (
          <g key={t}>
            <line className="axis-line" x1={X0} x2={W} y1={balY(t)} y2={balY(t)} />
            <text x={0} y={balY(t) + 4} fontSize={11}>
              {shortAmount(t)}
            </text>
          </g>
        ))}
        {points.map((run) => (
          <polyline key={run[0]} points={run.join(" ")} fill="none" stroke="var(--bar)" strokeWidth={2} strokeLinejoin="round" strokeLinecap="round" />
        ))}
        {visible.map((m, i) =>
          m.balance === null ? null : (
            <circle
              key={m.month}
              cx={cx(i)}
              cy={balY(toNumber(m.balance))}
              r={start + i === selected ? 6 : 4}
              fill="var(--bar)"
              stroke="var(--surface)"
              strokeWidth={2}
            />
          ),
        )}
        {visible.map((m, i) => (
          <g key={`hit-${m.month}`}>{column(i, 104)}</g>
        ))}
      </svg>
      <p className="visually-hidden">
        מוצגים {monthLabel(visible[0].month)} עד {monthLabel(visible[visible.length - 1].month)}
      </p>
    </div>
  );
}
