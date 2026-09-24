import { percent, toNumber } from "../lib/format";

interface Props {
  value: string | number;
  max: string | number;
  size?: "thin" | "normal" | "thick";
  tone?: "default" | "muted" | "income";
  label: string;
}

export function ProgressBar({ value, max, size = "normal", tone = "default", label }: Props) {
  const over = toNumber(max) > 0 ? toNumber(value) > toNumber(max) : toNumber(value) > 0 && tone !== "income";
  const fill = over ? "bar-fill--over" : tone === "muted" ? "bar-fill--muted" : tone === "income" ? "bar-fill--income" : "";
  const pct = percent(value, max);
  return (
    <div
      className={`bar${size === "thin" ? " bar--thin" : size === "thick" ? " bar--thick" : ""}`}
      role="progressbar"
      aria-label={label}
      aria-valuemin={0}
      aria-valuemax={100}
      aria-valuenow={Math.round(pct)}
    >
      <div className={`bar-fill ${fill}`} style={{ width: `${pct}%` }} />
    </div>
  );
}
