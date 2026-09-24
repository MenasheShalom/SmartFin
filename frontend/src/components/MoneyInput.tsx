import { useId } from "react";

interface Props {
  label: string;
  value: string;
  onChange: (value: string) => void;
  hint?: string;
  autoFocus?: boolean;
}

/** Whole shekels or agorot; keeps only digits and one decimal point */
export function MoneyInput({ label, value, onChange, hint, autoFocus }: Props) {
  const hintId = useId();
  return (
    <label className="field">
      {label}
      <input
        className="input input--money"
        inputMode="decimal"
        autoComplete="off"
        value={value}
        autoFocus={autoFocus}
        aria-describedby={hint ? hintId : undefined}
        onChange={(e) => {
          const cleaned = e.target.value.replace(/[^\d.]/g, "").replace(/(\..*?)\..*/, "$1");
          const [whole, cents] = cleaned.split(".");
          onChange(cents !== undefined ? `${whole}.${cents.slice(0, 2)}` : whole);
        }}
      />
      {hint && (
        <span id={hintId} className="field-hint">
          {hint}
        </span>
      )}
    </label>
  );
}

export function toAmount(value: string): string | null {
  if (!value.trim()) return null;
  const n = Number(value);
  return Number.isFinite(n) && n >= 0 ? n.toFixed(2) : null;
}
