import { monthLabel, shiftMonth } from "../lib/format";
import { ChevronEnd, ChevronStart } from "./Icons";

interface Props {
  month: string;
  onChange: (month: string) => void;
  min?: string;
  max?: string;
}

export function MonthSwitcher({ month, onChange, min, max }: Props) {
  const previous = shiftMonth(month, -1);
  const next = shiftMonth(month, 1);
  return (
    <div className="month-switcher">
      <button
        type="button"
        className="icon-button icon-button--outline"
        onClick={() => onChange(previous)}
        disabled={min !== undefined && previous < min}
        aria-label={`לחודש הקודם, ${monthLabel(previous)}`}
      >
        <ChevronStart size={20} />
      </button>
      <div className="month-switcher-label" aria-live="polite">
        {monthLabel(month)}
      </div>
      <button
        type="button"
        className="icon-button icon-button--outline"
        onClick={() => onChange(next)}
        disabled={max !== undefined && next > max}
        aria-label={`לחודש הבא, ${monthLabel(next)}`}
      >
        <ChevronEnd size={20} />
      </button>
    </div>
  );
}
