import type { Category } from "../api/types";

export type CategoryMap = Map<number, Category>;

export function byId(categories: Category[] | undefined): CategoryMap {
  return new Map((categories ?? []).map((c) => [c.id, c]));
}

/** Day-to-day spending: expense categories that are not fixed bills */
export function isVariable(categoryId: number | null, map: CategoryMap): boolean {
  if (categoryId === null) return false;
  const category = map.get(categoryId);
  return category?.kind === "expense" && !category.is_fixed;
}

export function categoryLabel(categoryId: number | null, map: CategoryMap): string {
  if (categoryId === null) return "לא מסווג";
  return map.get(categoryId)?.name ?? "";
}
