import { describe, expect, it } from "vitest";

import { clampEnd, niceScale, shortAmount } from "./chart";

describe("niceScale", () => {
  it("rounds up to a readable maximum", () => {
    expect(niceScale(21000)).toEqual({ max: 25000, ticks: [0, 5000, 10000, 15000, 20000, 25000] });
    expect(niceScale(14200).max).toBe(15000);
    expect(niceScale(0).max).toBe(1000);
  });
});

describe("shortAmount", () => {
  it("abbreviates thousands", () => {
    expect(shortAmount(20000)).toBe("20K");
    expect(shortAmount(2500)).toBe("2.5K");
    expect(shortAmount(800)).toBe("800");
    expect(shortAmount(-5000)).toBe("−5K");
  });
});

describe("clampEnd", () => {
  it("keeps a full window inside the data", () => {
    expect(clampEnd(17, 18, 6)).toBe(17);
    expect(clampEnd(30, 18, 6)).toBe(17);
    expect(clampEnd(2, 18, 6)).toBe(5);
    expect(clampEnd(0, 3, 6)).toBe(2);
  });
});
