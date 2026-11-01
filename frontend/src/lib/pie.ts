import type { CategorySpend } from "../api/types";
import { toNumber } from "./format";

/** The id of the slice that folds the categories without a color of their own */
export const OTHER_ID = -1;

export interface Slice {
  id: number;
  name: string;
  value: number;
  /** "--cat-1" to "--cat-7", or "--cat-other" */
  color: string;
  /** Share of the month's total, 0-1 */
  share: number;
  categories: CategorySpend[];
}

/**
 * One slice per category with a color slot, plus one "other" slice for the rest. Slices go
 * round the ring in color-slot order, not by this month's amount, so neighbouring colors are
 * always the pairs the palette was checked for, and "other" (gray) sits between the last and
 * the first.
 */
export function buildSlices(categories: CategorySpend[]): Slice[] {
  const positive = categories.filter((c) => toNumber(c.total) > 0);
  const total = positive.reduce((sum, c) => sum + toNumber(c.total), 0);
  if (total <= 0) return [];
  const colored = positive
    .filter((c) => c.color_slot !== null)
    .sort((a, b) => a.color_slot! - b.color_slot!)
    .map<Slice>((c) => ({
      id: c.category_id,
      name: c.name,
      value: toNumber(c.total),
      color: `--cat-${c.color_slot! + 1}`,
      share: toNumber(c.total) / total,
      categories: [c],
    }));
  const rest = positive.filter((c) => c.color_slot === null);
  if (rest.length === 0) return colored;
  const restValue = rest.reduce((sum, c) => sum + toNumber(c.total), 0);
  // A single uncolored category keeps its own name
  const other: Slice = {
    id: rest.length === 1 ? rest[0].category_id : OTHER_ID,
    name: rest.length === 1 ? rest[0].name : "אחר",
    value: restValue,
    color: "--cat-other",
    share: restValue / total,
    categories: rest,
  };
  return [...colored, other];
}

/** The same slices for the list: largest first */
export function byAmount(slices: Slice[]): Slice[] {
  return [...slices].sort((a, b) => b.value - a.value || a.name.localeCompare(b.name));
}

/** "34%", or "<1%" for a sliver */
export function shareLabel(share: number): string {
  if (share > 0 && share < 0.005) return "<1%";
  return `${Math.round(share * 100)}%`;
}

const TAU = Math.PI * 2;

function point(cx: number, cy: number, r: number, angle: number): string {
  // 0 is twelve o'clock, going clockwise
  return `${(cx + r * Math.sin(angle)).toFixed(2)},${(cy - r * Math.cos(angle)).toFixed(2)}`;
}

/**
 * A donut segment from start to end (radians from twelve o'clock, clockwise). A gap of `gap`
 * pixels is cut along each straight edge, so neighbouring segments are parted by the surface.
 */
export function donutSegment(
  cx: number,
  cy: number,
  outer: number,
  inner: number,
  start: number,
  end: number,
  gap = 1,
): string {
  const sweep = end - start;
  if (sweep >= TAU - 1e-6) {
    // A whole ring: two half circles each way, the hole cut out by the even-odd rule
    return [
      `M${point(cx, cy, outer, 0)}`,
      `A${outer},${outer} 0 1 1 ${point(cx, cy, outer, Math.PI)}`,
      `A${outer},${outer} 0 1 1 ${point(cx, cy, outer, 0)}Z`,
      `M${point(cx, cy, inner, 0)}`,
      `A${inner},${inner} 0 1 0 ${point(cx, cy, inner, Math.PI)}`,
      `A${inner},${inner} 0 1 0 ${point(cx, cy, inner, 0)}Z`,
    ].join("");
  }
  const outerPad = Math.min(gap / outer, sweep / 4);
  const innerPad = Math.min(gap / inner, sweep / 4);
  const a0 = start + outerPad;
  const a1 = end - outerPad;
  const b0 = start + innerPad;
  const b1 = end - innerPad;
  const largeOuter = a1 - a0 > Math.PI ? 1 : 0;
  const largeInner = b1 - b0 > Math.PI ? 1 : 0;
  return [
    `M${point(cx, cy, outer, a0)}`,
    `A${outer},${outer} 0 ${largeOuter} 1 ${point(cx, cy, outer, a1)}`,
    `L${point(cx, cy, inner, b1)}`,
    `A${inner},${inner} 0 ${largeInner} 0 ${point(cx, cy, inner, b0)}Z`,
  ].join("");
}

/** Start and end angle of each slice, in order round the ring */
export function sliceAngles(slices: Slice[]): { start: number; end: number }[] {
  let at = 0;
  return slices.map((s) => {
    const start = at;
    at += s.share * TAU;
    return { start, end: at };
  });
}
