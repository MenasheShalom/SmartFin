/** Formatting for a Hebrew, right-to-left UI. Amounts arrive from the API as decimal strings. */

export const HEBREW_MONTHS = [
  "ינואר", "פברואר", "מרץ", "אפריל", "מאי", "יוני",
  "יולי", "אוגוסט", "ספטמבר", "אוקטובר", "נובמבר", "דצמבר",
];
export const SHORT_MONTHS = [
  "ינו׳", "פבר׳", "מרץ", "אפר׳", "מאי", "יוני",
  "יולי", "אוג׳", "ספט׳", "אוק׳", "נוב׳", "דצמ׳",
];

const MINUS = "−";
const grouping = new Intl.NumberFormat("en-US", { maximumFractionDigits: 0 });
const cents = new Intl.NumberFormat("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 });

export type Decimals = 0 | 2 | "auto";
export type Sign = "auto" | "always" | "never";

export function toNumber(value: string | number | null | undefined): number {
  if (value === null || value === undefined || value === "") return 0;
  const n = typeof value === "number" ? value : Number(value);
  return Number.isFinite(n) ? n : 0;
}

/** "₪1,646", "−₪1,450.50", "+₪1,646". The symbol leads, as Israeli apps show it. */
export function formatMoney(
  value: string | number | null | undefined,
  { decimals = "auto", sign = "auto" }: { decimals?: Decimals; sign?: Sign } = {},
): string {
  const n = toNumber(value);
  const abs = Math.abs(n);
  const showCents = decimals === 2 || (decimals === "auto" && Math.round(abs * 100) % 100 !== 0);
  const body = showCents ? cents.format(abs) : grouping.format(Math.round(abs));
  const isZero = showCents ? Math.round(abs * 100) === 0 : Math.round(abs) === 0;
  let prefix = "";
  if (!isZero && n < 0 && sign !== "never") prefix = MINUS;
  else if (!isZero && n > 0 && sign === "always") prefix = "+";
  return `${prefix}₪${body}`;
}

export function parseMonth(month: string): { year: number; month: number } {
  const [year, m] = month.split("-").map(Number);
  return { year, month: m };
}

export function formatMonthKey(year: number, month: number): string {
  return `${year}-${String(month).padStart(2, "0")}`;
}

export function shiftMonth(month: string, delta: number): string {
  const { year, month: m } = parseMonth(month);
  const index = year * 12 + (m - 1) + delta;
  return formatMonthKey(Math.floor(index / 12), (index % 12) + 1);
}

export function monthLabel(month: string): string {
  const { year, month: m } = parseMonth(month);
  return `${HEBREW_MONTHS[m - 1]} ${year}`;
}

export function monthName(month: string): string {
  return HEBREW_MONTHS[parseMonth(month).month - 1];
}

export function shortMonthLabel(month: string): string {
  return SHORT_MONTHS[parseMonth(month).month - 1];
}

/** Today's date in Israel, as "YYYY-MM-DD", whatever the device's time zone. */
export function israelToday(now: Date = new Date()): string {
  return new Intl.DateTimeFormat("en-CA", { timeZone: "Asia/Jerusalem" }).format(now);
}

export function currentMonth(now: Date = new Date()): string {
  return israelToday(now).slice(0, 7);
}

function asDate(day: string): Date {
  // Noon UTC keeps the calendar day stable in every time zone
  return new Date(`${day}T12:00:00Z`);
}

const dayFormat = new Intl.DateTimeFormat("he-IL", {
  weekday: "short",
  day: "numeric",
  month: "long",
  timeZone: "UTC",
});
const shortDayFormat = new Intl.DateTimeFormat("he-IL", {
  day: "numeric",
  month: "long",
  timeZone: "UTC",
});

/** "יום ב׳, 21 בספטמבר" */
export function formatDay(day: string): string {
  return dayFormat.format(asDate(day));
}

/** "21 בספטמבר" */
export function formatShortDay(day: string): string {
  return shortDayFormat.format(asDate(day));
}

/** "היום", "אתמול", or the full day */
export function relativeDay(day: string, today: string = israelToday()): string {
  if (day === today) return "היום";
  const diff = Math.round((asDate(today).getTime() - asDate(day).getTime()) / 86_400_000);
  if (diff === 1) return "אתמול";
  return formatDay(day);
}

/** Keep a run of text left to right inside Hebrew ("…8901", "1–5") */
export function ltr(text: string): string {
  return `\u2066${text}\u2069`;
}

/** "1–5" for a week inside one month, kept left to right */
export function dayRange(start: string, end: string): string {
  const a = Number(start.slice(8, 10));
  const b = Number(end.slice(8, 10));
  return ltr(a === b ? String(a) : `${a}–${b}`);
}

const timeFormat = new Intl.DateTimeFormat("he-IL", {
  hour: "2-digit",
  minute: "2-digit",
  timeZone: "Asia/Jerusalem",
});

/** "היום ב־03:02", "אתמול ב־03:02", "21 בספטמבר ב־03:02" */
export function formatSyncTime(iso: string, now: Date = new Date()): string {
  const at = new Date(iso);
  const day = israelToday(at);
  const today = israelToday(now);
  const label = day === today ? "היום" : relativeDay(day, today) === "אתמול" ? "אתמול" : formatShortDay(day);
  return `${label} ב־${timeFormat.format(at)}`;
}

export function greeting(now: Date = new Date()): string {
  const hour = Number(
    new Intl.DateTimeFormat("en-US", { hour: "numeric", hour12: false, timeZone: "Asia/Jerusalem" }).format(now),
  );
  if (hour >= 5 && hour < 12) return "בוקר טוב";
  if (hour >= 12 && hour < 17) return "צהריים טובים";
  if (hour >= 17 && hour < 22) return "ערב טוב";
  return "לילה טוב";
}

/** Share of a budget used, clamped to 0..100 for progress bars */
export function percent(part: string | number, whole: string | number): number {
  const w = toNumber(whole);
  if (w <= 0) return toNumber(part) > 0 ? 100 : 0;
  return Math.max(0, Math.min(100, (toNumber(part) / w) * 100));
}
