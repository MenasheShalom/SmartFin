import { NavLink } from "react-router-dom";

import { CalendarIcon, ChartIcon, FlowIcon, ListIcon, PlanIcon } from "./Icons";

const TABS = [
  { to: "/", label: "תזרים", Icon: FlowIcon, end: true },
  { to: "/weekly", label: "שבועי", Icon: CalendarIcon, end: false },
  { to: "/history", label: "היסטוריה", Icon: ChartIcon, end: false },
  { to: "/transactions", label: "תנועות", Icon: ListIcon, end: false },
  { to: "/plan", label: "תוכנית", Icon: PlanIcon, end: false },
];

export function TabBar({ uncategorized = 0 }: { uncategorized?: number }) {
  return (
    <nav className="tabbar" aria-label="ניווט ראשי">
      <div className="tabbar-inner">
        {TABS.map(({ to, label, Icon, end }) => (
          <NavLink key={to} to={to} end={end} className="tab" style={{ position: "relative" }}>
            <Icon />
            <span>{label}</span>
            {to === "/transactions" && uncategorized > 0 && (
              <span className="badge" style={{ insetInlineEnd: "22%" }}>
                <span className="visually-hidden">לסיווג: </span>
                {uncategorized > 99 ? "99+" : uncategorized}
              </span>
            )}
          </NavLink>
        ))}
      </div>
    </nav>
  );
}
