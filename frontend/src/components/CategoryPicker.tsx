import { useMemo, useState } from "react";

import type { Category } from "../api/types";

export type Group = "variable" | "fixed" | "other";

export const GROUP_LABELS: Record<Group, string> = {
  variable: "משתנה",
  fixed: "קבועה",
  other: "אחר",
};

export function groupOf(category: Category): Group {
  if (category.kind !== "expense") return "other";
  return category.is_fixed ? "fixed" : "variable";
}

/** Categories a transaction can be filed under: subcategories, and parents without any */
export function selectableCategories(categories: Category[]): Category[] {
  const parents = new Set(categories.filter((c) => c.parent_id !== null).map((c) => c.parent_id));
  return categories.filter((c) => c.parent_id !== null || !parents.has(c.id));
}

interface Props {
  categories: Category[];
  value: number | null;
  onChange: (id: number) => void;
  initialGroup?: Group;
  onAddNew?: (group: Group) => void;
}

export function CategoryPicker({ categories, value, onChange, initialGroup, onAddNew }: Props) {
  const selected = categories.find((c) => c.id === value);
  const [group, setGroup] = useState<Group>(initialGroup ?? (selected ? groupOf(selected) : "variable"));
  const options = useMemo(
    () =>
      selectableCategories(categories)
        .filter((c) => groupOf(c) === group)
        .sort((a, b) => a.name.localeCompare(b.name, "he")),
    [categories, group],
  );

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 14 }}>
      <div className="segmented" role="group" aria-label="סוג">
        {(Object.keys(GROUP_LABELS) as Group[]).map((g) => (
          <button key={g} type="button" aria-pressed={group === g} onClick={() => setGroup(g)}>
            {GROUP_LABELS[g]}
          </button>
        ))}
      </div>
      <div className="chips" role="group" aria-label="קטגוריה">
        {options.map((c) => (
          <button key={c.id} type="button" className="chip" aria-pressed={c.id === value} onClick={() => onChange(c.id)}>
            {c.name}
          </button>
        ))}
        {onAddNew && (
          <button type="button" className="chip chip--add" onClick={() => onAddNew(group)}>
            + חדשה
          </button>
        )}
      </div>
    </div>
  );
}
