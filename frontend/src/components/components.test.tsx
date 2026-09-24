import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useState } from "react";
import { describe, expect, it, vi } from "vitest";

import type { Category } from "../api/types";
import { CategoryPicker, selectableCategories } from "./CategoryPicker";
import { MoneyInput, toAmount } from "./MoneyInput";
import { ProgressBar } from "./ProgressBar";

const categories: Category[] = [
  { id: 1, name: "מזון", parent_id: null, kind: "expense", is_fixed: false },
  { id: 2, name: "סופר", parent_id: 1, kind: "expense", is_fixed: false },
  { id: 3, name: "קניות", parent_id: null, kind: "expense", is_fixed: false },
  { id: 4, name: "שכירות", parent_id: null, kind: "expense", is_fixed: true },
  { id: 5, name: "משכורת", parent_id: null, kind: "income", is_fixed: false },
];

describe("MoneyInput", () => {
  function Harness() {
    const [value, setValue] = useState("");
    return <MoneyInput label="סכום" value={value} onChange={setValue} />;
  }

  it("keeps digits and at most two decimals", async () => {
    render(<Harness />);
    const input = screen.getByLabelText("סכום");
    await userEvent.type(input, "1a2,3.456.7");
    expect(input).toHaveValue("123.45");
  });

  it("converts to an API amount", () => {
    expect(toAmount("1500")).toBe("1500.00");
    expect(toAmount("")).toBeNull();
    expect(toAmount("12.5")).toBe("12.50");
  });
});

describe("CategoryPicker", () => {
  it("offers subcategories, not their parents", () => {
    expect(selectableCategories(categories).map((c) => c.id)).toEqual([2, 3, 4, 5]);
  });

  it("filters by type and reports the pick", async () => {
    const onChange = vi.fn();
    render(<CategoryPicker categories={categories} value={null} onChange={onChange} />);
    expect(screen.getByRole("button", { name: "סופר" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "שכירות" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "מזון" })).not.toBeInTheDocument();

    await userEvent.click(screen.getByRole("button", { name: "קבועה" }));
    await userEvent.click(screen.getByRole("button", { name: "שכירות" }));
    expect(onChange).toHaveBeenCalledWith(4);

    await userEvent.click(screen.getByRole("button", { name: "אחר" }));
    expect(screen.getByRole("button", { name: "משכורת" })).toBeInTheDocument();
  });

  it("marks the selected category", () => {
    render(<CategoryPicker categories={categories} value={3} onChange={() => {}} />);
    expect(screen.getByRole("button", { name: "קניות" })).toHaveAttribute("aria-pressed", "true");
  });
});

describe("ProgressBar", () => {
  it("reports its level and turns over-budget when exceeded", () => {
    const { container, rerender } = render(<ProgressBar value={50} max={200} label="השבוע" />);
    expect(screen.getByRole("progressbar", { name: "השבוע" })).toHaveAttribute("aria-valuenow", "25");
    rerender(<ProgressBar value={250} max={200} label="השבוע" />);
    expect(container.querySelector(".bar-fill--over")).not.toBeNull();
  });
});
