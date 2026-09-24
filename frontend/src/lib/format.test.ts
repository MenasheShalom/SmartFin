import { describe, expect, it } from "vitest";

import {
  dayRange,
  formatDay,
  formatMoney,
  greeting,
  israelToday,
  monthLabel,
  percent,
  relativeDay,
  shiftMonth,
} from "./format";

describe("formatMoney", () => {
  it("shows whole shekels without agorot", () => {
    expect(formatMoney("1646.00")).toBe("₪1,646");
    expect(formatMoney(14200)).toBe("₪14,200");
  });
  it("shows agorot when there are any", () => {
    expect(formatMoney("-312.90")).toBe("−₪312.90");
    expect(formatMoney("0.5")).toBe("₪0.50");
  });
  it("can force decimals or signs", () => {
    expect(formatMoney("-38", { decimals: 2 })).toBe("−₪38.00");
    expect(formatMoney("1646", { sign: "always" })).toBe("+₪1,646");
    expect(formatMoney("-1646", { sign: "never" })).toBe("₪1,646");
  });
  it("never shows a signed zero", () => {
    expect(formatMoney("-0.00", { sign: "always" })).toBe("₪0");
    expect(formatMoney(null)).toBe("₪0");
  });
});

describe("months", () => {
  it("labels and shifts", () => {
    expect(monthLabel("2026-09")).toBe("ספטמבר 2026");
    expect(shiftMonth("2026-01", -1)).toBe("2025-12");
    expect(shiftMonth("2026-12", 1)).toBe("2027-01");
    expect(shiftMonth("2026-09", -18)).toBe("2025-03");
  });
});

describe("days", () => {
  it("formats Hebrew dates", () => {
    expect(formatDay("2026-09-21")).toContain("21 בספטמבר");
    expect(relativeDay("2026-09-24", "2026-09-24")).toBe("היום");
    expect(relativeDay("2026-09-23", "2026-09-24")).toBe("אתמול");
    expect(dayRange("2026-09-01", "2026-09-05")).toBe("\u20661–5\u2069");
  });
  it("uses Israel time for today", () => {
    // 22:30 UTC on Sept 24 is already Sept 25 in Israel
    expect(israelToday(new Date("2026-09-24T22:30:00Z"))).toBe("2026-09-25");
  });
  it("greets by Israel hour", () => {
    expect(greeting(new Date("2026-09-24T05:00:00Z"))).toBe("בוקר טוב"); // 08:00 IDT
    expect(greeting(new Date("2026-09-24T16:00:00Z"))).toBe("ערב טוב"); // 19:00 IDT
  });
});

describe("percent", () => {
  it("clamps", () => {
    expect(percent(50, 200)).toBe(25);
    expect(percent(300, 200)).toBe(100);
    expect(percent(10, 0)).toBe(100);
    expect(percent(0, 0)).toBe(0);
  });
});
