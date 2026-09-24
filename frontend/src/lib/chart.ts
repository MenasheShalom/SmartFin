import type { MonthHistory } from "../api/types";
import { toNumber } from "./format";

/** A "nice" axis: the smallest step of 1, 2, 2.5 or 5 times a power of ten that covers the
 * maximum in at most tickCount + 1 intervals */
export function niceScale(maxValue: number, tickCount = 4): { max: number; ticks: number[] } {
  if (maxValue <= 0) return { max: 1000, ticks: [0, 250, 500, 750, 1000] };
  let power = 10 ** Math.floor(Math.log10(maxValue / (tickCount + 1)));
  let step = power;
  for (;;) {
    const found = [1, 2, 2.5, 5].map((m) => m * power).find((s) => Math.ceil(maxValue / s) <= tickCount + 1);
    if (found) {
      step = found;
      break;
    }
    power *= 10;
  }
  const max = Math.ceil(maxValue / step) * step;
  const ticks = [];
  for (let i = 0; i * step <= max + step / 2; i++) ticks.push(i * step);
  return { max, ticks };
}

/** "20K", "2.5K", "800" */
export function shortAmount(value: number): string {
  const abs = Math.abs(value);
  const sign = value < 0 ? "−" : "";
  if (abs >= 1000) {
    const k = abs / 1000;
    return `${sign}${Number.isInteger(k) ? k : k.toFixed(1)}K`;
  }
  return `${sign}${abs}`;
}

/** Keep the window inside the data: its last index is between window-1 and length-1 */
export function clampEnd(end: number, length: number, size: number): number {
  return Math.max(Math.min(size, length) - 1, Math.min(length - 1, end));
}

/** One scale for the whole history, so heights mean the same in every window */
export function historyScales(months: MonthHistory[]) {
  const moneyMax = Math.max(0, ...months.flatMap((m) => [toNumber(m.income), toNumber(m.expenses)]));
  const balances = months.flatMap((m) => (m.balance === null ? [] : [toNumber(m.balance)]));
  const high = Math.max(0, ...balances);
  const low = Math.min(0, ...balances);
  return {
    bars: niceScale(moneyMax),
    balance: {
      min: low < 0 ? -niceScale(-low, 2).max : 0,
      max: high > 0 ? niceScale(high, 2).max : low < 0 ? 0 : 1000,
    },
  };
}

/** A bar with rounded top corners, anchored to the baseline */
export function barPath(x: number, width: number, height: number, base: number): string {
  const h = Math.max(height, 1);
  const r = Math.min(4, h, width / 2);
  const y = base - h;
  return `M${x},${base}V${y + r}Q${x},${y} ${x + r},${y}H${x + width - r}Q${x + width},${y} ${x + width},${y + r}V${base}Z`;
}
