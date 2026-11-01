import { describe, expect, it } from "vitest";

import type { CategorySpend } from "../api/types";
import { OTHER_ID, buildSlices, byAmount, donutSegment, shareLabel, sliceAngles } from "./pie";

const cat = (id: number, name: string, total: string, slot: number | null): CategorySpend => ({
  category_id: id,
  name,
  total,
  color_slot: slot,
  subcategories: [],
});

describe("buildSlices", () => {
  it("goes round the ring in color order and folds the rest into other", () => {
    const slices = buildSlices([
      cat(1, "מזון", "3000.00", 1),
      cat(2, "דיור", "1000.00", 0),
      cat(3, "קניות", "600.00", null),
      cat(4, "פנאי", "400.00", null),
    ]);
    expect(slices.map((s) => [s.name, s.color])).toEqual([
      ["דיור", "--cat-1"],
      ["מזון", "--cat-2"],
      ["אחר", "--cat-other"],
    ]);
    expect(slices[2].id).toBe(OTHER_ID);
    expect(slices[2].value).toBe(1000);
    expect(slices.map((s) => s.share)).toEqual([0.2, 0.6, 0.2]);
    expect(byAmount(slices).map((s) => s.name)).toEqual(["מזון", "אחר", "דיור"]);
  });

  it("keeps the name of a single uncolored category", () => {
    const slices = buildSlices([cat(1, "מזון", "100.00", 0), cat(5, "מתנות", "50.00", null)]);
    expect(slices[1]).toMatchObject({ id: 5, name: "מתנות", color: "--cat-other" });
  });

  it("is empty when nothing was spent", () => {
    expect(buildSlices([])).toEqual([]);
    expect(buildSlices([cat(1, "מזון", "0.00", 0)])).toEqual([]);
  });
});

describe("geometry", () => {
  it("splits the full circle", () => {
    const angles = sliceAngles(buildSlices([cat(1, "a", "1", 0), cat(2, "b", "3", 1)]));
    expect(angles[0].start).toBe(0);
    expect(angles[1].end).toBeCloseTo(Math.PI * 2);
    expect(angles[0].end).toBeCloseTo(Math.PI / 2);
  });

  it("draws a segment and a whole ring", () => {
    expect(donutSegment(100, 100, 96, 62, 0, Math.PI / 2)).toMatch(/^M.*A96,96 0 0 1 .*L.*A62,62 0 0 0 .*Z$/);
    expect(donutSegment(100, 100, 96, 62, 0, Math.PI * 2)).toContain("A62,62 0 1 0");
  });

  it("labels shares", () => {
    expect(shareLabel(0.344)).toBe("34%");
    expect(shareLabel(0.001)).toBe("<1%");
    expect(shareLabel(0)).toBe("0%");
  });
});
