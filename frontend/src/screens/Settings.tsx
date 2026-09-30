import { useState, type ReactNode } from "react";
import { Link } from "react-router-dom";

import { ApiError, errorMessage } from "../api/client";
import {
  useAccounts,
  useCategories,
  useCategoryMutations,
  useLogout,
  useMe,
  useRuleMutations,
  useRules,
  useSyncStatus,
  useUpdateAccount,
} from "../api/queries";
import type { Category, CategoryKind, Rule } from "../api/types";
import { CategoryPicker, selectableCategories } from "../components/CategoryPicker";
import { ChevronEnd, ChevronStart, PlusIcon } from "../components/Icons";
import { Money } from "../components/Money";
import { Sheet } from "../components/Sheet";
import { EmptyState, ErrorState, Loading } from "../components/States";
import { useToast } from "../components/Toast";
import { formatSyncTime } from "../lib/format";
import { ConnectionsSection } from "./Connections";
import { MIN_PASSWORD } from "./Login";

function SubScreen({ title, subtitle, action, children }: { title: string; subtitle?: string; action?: ReactNode; children: ReactNode }) {
  return (
    <main className="screen">
      <Link to="/settings" className="back-link">
        <ChevronStart size={18} />
        הגדרות
      </Link>
      <header className="screen-header">
        <div>
          <h1 className="screen-title">{title}</h1>
          {subtitle && <p className="screen-subtitle">{subtitle}</p>}
        </div>
        {action}
      </header>
      {children}
    </main>
  );
}

export function SettingsScreen() {
  const logout = useLogout();
  const me = useMe();
  const [editingAccount, setEditingAccount] = useState(false);
  const items = [
    { to: "/settings/categories", title: "קטגוריות", sub: "שמות, קבועות ומשתנות" },
    { to: "/settings/rules", title: "כללי סיווג", sub: "איך תנועות מסווגות אוטומטית" },
    { to: "/settings/accounts", title: "חשבונות וסנכרון", sub: "חיבור בנקים וכרטיסי אשראי, יתרות וסנכרון" },
    { to: "/alerts", title: "התראות", sub: "חריגות, יתרה נמוכה וחיובים גדולים" },
  ];
  return (
    <main className="screen">
      <Link to="/" className="back-link">
        <ChevronStart size={18} />
        תזרים
      </Link>
      <h1 className="screen-title">הגדרות</h1>
      <nav className="card card--flush" aria-label="הגדרות">
        <div className="list">
          {items.map((item) => (
            <Link key={item.to} to={item.to} className="list-row">
              <span className="list-row-main">
                <span className="list-row-title">{item.title}</span>
                <span className="list-row-sub">{item.sub}</span>
              </span>
              <ChevronEnd size={18} />
            </Link>
          ))}
        </div>
      </nav>
      <section className="card card--flush" aria-label="משתמש">
        <button type="button" className="list-row" onClick={() => setEditingAccount(true)}>
          <span className="list-row-main">
            <span className="list-row-title">שם משתמש וסיסמה</span>
            <span className="list-row-sub">{me.data?.username ? `מחובר כ־${me.data.username}` : "שינוי פרטי הכניסה"}</span>
          </span>
          <ChevronEnd size={18} />
        </button>
      </section>
      <button type="button" className="button button--danger" onClick={() => logout.mutate()} disabled={logout.isPending}>
        התנתקות
      </button>
      {editingAccount && <AccountSheet username={me.data?.username ?? ""} onClose={() => setEditingAccount(false)} />}
    </main>
  );
}

function AccountSheet({ username: currentUsername, onClose }: { username: string; onClose: () => void }) {
  const [username, setUsername] = useState(currentUsername);
  const [current, setCurrent] = useState("");
  const [password, setPassword] = useState("");
  const [again, setAgain] = useState("");
  const [tried, setTried] = useState(false);
  const update = useUpdateAccount();
  const toast = useToast();

  let error: string | null = null;
  if (tried && password && password.length < MIN_PASSWORD) error = `הסיסמה החדשה צריכה להיות באורך ${MIN_PASSWORD} תווים לפחות.`;
  else if (tried && password !== again) error = "הסיסמאות החדשות לא תואמות.";
  else if (update.error instanceof ApiError && update.error.status === 400) error = "הסיסמה הנוכחית שגויה.";
  else if (update.error) error = errorMessage(update.error);

  const submit = () => {
    setTried(true);
    if (!username.trim() || !current || (password && password.length < MIN_PASSWORD) || password !== again) return;
    update.mutate(
      { current_password: current, username: username.trim(), ...(password ? { new_password: password } : {}) },
      {
        onSuccess: () => {
          toast(password ? "הפרטים עודכנו. מכשירים אחרים נותקו." : "שם המשתמש עודכן.");
          onClose();
        },
      },
    );
  };

  return (
    <Sheet title="שם משתמש וסיסמה" onClose={onClose}>
      <form
        style={{ display: "flex", flexDirection: "column", gap: 14 }}
        onSubmit={(e) => {
          e.preventDefault();
          submit();
        }}
      >
        <label className="field">
          שם משתמש
          <input
            className="input"
            autoComplete="username"
            autoCapitalize="none"
            maxLength={64}
            value={username}
            onChange={(e) => setUsername(e.target.value)}
            required
          />
        </label>
        <label className="field">
          סיסמה חדשה
          <span className="field-hint">השאירו ריק כדי לא לשנות</span>
          <input className="input" type="password" autoComplete="new-password" value={password} onChange={(e) => setPassword(e.target.value)} />
        </label>
        {password && (
          <label className="field">
            הסיסמה החדשה שוב
            <input className="input" type="password" autoComplete="new-password" value={again} onChange={(e) => setAgain(e.target.value)} />
          </label>
        )}
        <label className="field">
          הסיסמה הנוכחית
          <span className="field-hint">לאישור השינוי</span>
          <input
            className="input"
            type="password"
            autoComplete="current-password"
            value={current}
            onChange={(e) => setCurrent(e.target.value)}
            required
          />
        </label>
        {error && (
          <p className="error-text" role="alert">
            {error}
          </p>
        )}
        <button type="submit" className="button" disabled={update.isPending || !current || !username.trim()}>
          שמירה
        </button>
      </form>
    </Sheet>
  );
}

const KIND_SECTIONS: { kind: CategoryKind; fixed?: boolean; title: string }[] = [
  { kind: "expense", fixed: true, title: "הוצאות קבועות" },
  { kind: "expense", fixed: false, title: "הוצאות משתנות" },
  { kind: "income", title: "הכנסות" },
  { kind: "transfer", title: "העברות בין חשבונות" },
];

export function CategoriesScreen() {
  const categories = useCategories();
  const [editing, setEditing] = useState<Category | "new" | null>(null);

  return (
    <SubScreen
      title="קטגוריות"
      subtitle="קבועות נכנסות לתוכנית החודשית, משתנות לתקציב השבועי. העברות לא נספרות כהוצאה."
      action={
        <button type="button" className="icon-button" aria-label="קטגוריה חדשה" onClick={() => setEditing("new")}>
          <PlusIcon size={20} />
        </button>
      }
    >
      {categories.isPending && <Loading rows={3} />}
      {categories.isError && <ErrorState error={categories.error} onRetry={() => categories.refetch()} />}
      {categories.data &&
        KIND_SECTIONS.map((section) => {
          const roots = categories.data.filter(
            (c) => c.parent_id === null && c.kind === section.kind && (section.fixed === undefined || c.is_fixed === section.fixed),
          );
          if (roots.length === 0) return null;
          return (
            <section key={section.title} aria-label={section.title}>
              <h2 className="group-label">{section.title}</h2>
              <div className="card card--flush" style={{ marginTop: 6 }}>
                <div className="list">
                  {roots.flatMap((root) => [
                    <button key={root.id} type="button" className="list-row" onClick={() => setEditing(root)}>
                      <span className="list-row-title" style={{ fontWeight: 700 }}>{root.name}</span>
                      <ChevronEnd size={18} />
                    </button>,
                    ...categories.data
                      .filter((c) => c.parent_id === root.id)
                      .map((child) => (
                        <button key={child.id} type="button" className="list-row" onClick={() => setEditing(child)} style={{ paddingInlineStart: 34 }}>
                          <span className="list-row-title">
                            {child.name}
                            {child.is_fixed !== root.is_fixed && <span className="muted" style={{ fontSize: 13 }}> · {child.is_fixed ? "קבועה" : "משתנה"}</span>}
                          </span>
                          <ChevronEnd size={18} />
                        </button>
                      )),
                  ])}
                </div>
              </div>
            </section>
          );
        })}
      {editing && categories.data && (
        <CategorySheet category={editing === "new" ? null : editing} categories={categories.data} onClose={() => setEditing(null)} />
      )}
    </SubScreen>
  );
}

function CategorySheet({ category, categories, onClose }: { category: Category | null; categories: Category[]; onClose: () => void }) {
  const [name, setName] = useState(category?.name ?? "");
  const [parentId, setParentId] = useState<number | "">(category?.parent_id ?? "");
  const [kind, setKind] = useState<CategoryKind>(category?.kind ?? "expense");
  const [fixed, setFixed] = useState(category?.is_fixed ?? false);
  const { create, update, remove } = useCategoryMutations();
  const toast = useToast();
  const parent = categories.find((c) => c.id === parentId);
  const effectiveKind = parent ? parent.kind : kind;
  const pending = create.isPending || update.isPending || remove.isPending;
  const fail = (err: unknown) => toast(errorMessage(err));

  const submit = () => {
    const trimmed = name.trim();
    if (!trimmed) return;
    if (category) {
      update.mutate(
        {
          id: category.id,
          name: trimmed,
          ...(category.parent_id === null && kind !== category.kind ? { kind } : {}),
          ...(effectiveKind === "expense" ? { is_fixed: fixed } : {}),
        },
        { onSuccess: () => { toast("הקטגוריה עודכנה."); onClose(); }, onError: fail },
      );
    } else {
      create.mutate(
        parentId === ""
          ? { name: trimmed, kind, is_fixed: kind === "expense" && fixed }
          : { name: trimmed, parent_id: parentId, is_fixed: fixed },
        { onSuccess: () => { toast("הקטגוריה נוספה."); onClose(); }, onError: fail },
      );
    }
  };

  const onDelete = () => {
    if (!category || !window.confirm(`למחוק את ״${category.name}״?`)) return;
    remove.mutate(category.id, {
      onSuccess: () => { toast("הקטגוריה נמחקה."); onClose(); },
      onError: (err) =>
        toast(
          errorMessage(err) === "אי אפשר: הפריט בשימוש."
            ? "אי אפשר למחוק קטגוריה שיש בה תנועות, כללים, תקציבים או תתי־קטגוריות."
            : errorMessage(err),
        ),
    });
  };

  return (
    <Sheet title={category ? category.name : "קטגוריה חדשה"} onClose={onClose}>
      <form
        style={{ display: "flex", flexDirection: "column", gap: 14 }}
        onSubmit={(e) => {
          e.preventDefault();
          submit();
        }}
      >
        <label className="field">
          שם
          <input className="input" value={name} onChange={(e) => setName(e.target.value)} maxLength={100} required />
        </label>
        {!category && (
          <label className="field">
            בתוך
            <select className="input" value={parentId} onChange={(e) => {
              const id = e.target.value ? Number(e.target.value) : "";
              setParentId(id);
              const p = categories.find((c) => c.id === id);
              if (p) setFixed(p.is_fixed);
            }}>
              <option value="">קטגוריה ראשית</option>
              {categories.filter((c) => c.parent_id === null).map((c) => (
                <option key={c.id} value={c.id}>{c.name}</option>
              ))}
            </select>
          </label>
        )}
        {(category ? category.parent_id === null : parentId === "") && (
          <label className="field">
            סוג
            <select className="input" value={kind} onChange={(e) => setKind(e.target.value as CategoryKind)}>
              <option value="expense">הוצאה</option>
              <option value="income">הכנסה</option>
              <option value="transfer">העברה בין חשבונות (לא נספרת)</option>
            </select>
          </label>
        )}
        {effectiveKind === "expense" && (
          <label className="switch-row">
            <span>
              הוצאה קבועה
              <span className="field-hint" style={{ display: "block" }}>
                חשבון שחוזר כל חודש, כמו שכירות או ביטוח
              </span>
            </span>
            <input type="checkbox" className="switch" checked={fixed} onChange={(e) => setFixed(e.target.checked)} />
          </label>
        )}
        <button type="submit" className="button" disabled={!name.trim() || pending}>
          שמירה
        </button>
        {category && (
          <button type="button" className="button button--danger" onClick={onDelete} disabled={pending}>
            מחיקה
          </button>
        )}
      </form>
    </Sheet>
  );
}

export function RulesScreen() {
  const rules = useRules();
  const categories = useCategories();
  const [editing, setEditing] = useState<Rule | "new" | null>(null);
  const names = new Map((categories.data ?? []).map((c) => [c.id, c.name]));

  return (
    <SubScreen
      title="כללי סיווג"
      subtitle="תנועה שהתיאור שלה מכיל את הטקסט מסווגת לקטגוריה. כלל ספציפי (ארוך יותר) גובר על כללי."
      action={
        <button type="button" className="icon-button" aria-label="כלל חדש" onClick={() => setEditing("new")}>
          <PlusIcon size={20} />
        </button>
      }
    >
      {(rules.isPending || categories.isPending) && <Loading rows={3} />}
      {rules.isError && <ErrorState error={rules.error} onRetry={() => rules.refetch()} />}
      {rules.data && rules.data.length === 0 && (
        <EmptyState title="עוד אין כללים" body="כשמסווגים תנועה עם ״לזכור לפעמים הבאות״, נוצר כאן כלל. אפשר גם להוסיף ידנית." />
      )}
      {rules.data && rules.data.length > 0 && categories.data && (
        <div className="card card--flush">
          <div className="list">
            {rules.data.map((rule) => (
              <button key={rule.id} type="button" className="list-row" onClick={() => setEditing(rule)}>
                <span className="list-row-main">
                  <span className="list-row-title" dir="auto">{rule.match_pattern}</span>
                  <span className="list-row-sub">
                    ← {names.get(rule.category_id)}
                    {rule.is_regex && " · ביטוי רגולרי"}
                    {rule.priority !== 0 && ` · עדיפות ${rule.priority}`}
                  </span>
                </span>
                <ChevronEnd size={18} />
              </button>
            ))}
          </div>
        </div>
      )}
      {editing && categories.data && (
        <RuleSheet rule={editing === "new" ? null : editing} categories={categories.data} onClose={() => setEditing(null)} />
      )}
    </SubScreen>
  );
}

function RuleSheet({ rule, categories, onClose }: { rule: Rule | null; categories: Category[]; onClose: () => void }) {
  const [pattern, setPattern] = useState(rule?.match_pattern ?? "");
  const [categoryId, setCategoryId] = useState<number | null>(rule?.category_id ?? null);
  const [regex, setRegex] = useState(rule?.is_regex ?? false);
  const [priority, setPriority] = useState(String(rule?.priority ?? 0));
  const { create, update, remove } = useRuleMutations();
  const toast = useToast();
  const pending = create.isPending || update.isPending || remove.isPending;

  const report = (result: { recategorized: number }) => {
    toast(result.recategorized > 0 ? `נשמר. ${result.recategorized} תנועות סווגו מחדש.` : "נשמר.");
    onClose();
  };
  const fail = (err: unknown) => toast(errorMessage(err));

  const submit = () => {
    if (!pattern.trim() || categoryId === null) return;
    const body = { match_pattern: pattern.trim(), category_id: categoryId, is_regex: regex, priority: Number(priority) || 0 };
    if (rule) update.mutate({ id: rule.id, ...body }, { onSuccess: report, onError: fail });
    else create.mutate(body, { onSuccess: report, onError: fail });
  };

  return (
    <Sheet title={rule ? "עריכת כלל" : "כלל חדש"} onClose={onClose}>
      <form
        style={{ display: "flex", flexDirection: "column", gap: 14 }}
        onSubmit={(e) => {
          e.preventDefault();
          submit();
        }}
      >
        <label className="field">
          כשהתיאור מכיל
          <input className="input" dir="auto" value={pattern} onChange={(e) => setPattern(e.target.value)} maxLength={255} required />
        </label>
        <div className="field">
          לסווג כ־
          <CategoryPicker categories={selectableCategories(categories)} value={categoryId} onChange={setCategoryId} />
        </div>
        <label className="switch-row">
          <span>ביטוי רגולרי</span>
          <input type="checkbox" className="switch" checked={regex} onChange={(e) => setRegex(e.target.checked)} />
        </label>
        <label className="field">
          עדיפות
          <input className="input" inputMode="numeric" value={priority} onChange={(e) => setPriority(e.target.value.replace(/[^\d-]/g, ""))} />
          <span className="field-hint">כשכמה כללים מתאימים, העדיפות הגבוהה גוברת.</span>
        </label>
        <button type="submit" className="button" disabled={!pattern.trim() || categoryId === null || pending}>
          שמירה
        </button>
        {rule && (
          <button
            type="button"
            className="button button--danger"
            disabled={pending}
            onClick={() => window.confirm("למחוק את הכלל?") && remove.mutate(rule.id, { onSuccess: report, onError: fail })}
          >
            מחיקה
          </button>
        )}
      </form>
    </Sheet>
  );
}

export function AccountsScreen() {
  const accounts = useAccounts();
  const sync = useSyncStatus();

  return (
    <SubScreen title="חשבונות וסנכרון" subtitle="הסנכרון רץ כל לילה. פרטי הכניסה לבנקים נשמרים מוצפנים רק בשרת הביתי.">
      <ConnectionsSection />
      {(accounts.isPending || sync.isPending) && <Loading rows={2} />}
      {accounts.isError && <ErrorState error={accounts.error} onRetry={() => accounts.refetch()} />}
      {sync.data && (
        <section aria-label="מצב הסנכרון">
          <h2 className="group-label">סנכרון אחרון</h2>
          {sync.data.length === 0 ? (
            <EmptyState title="עוד לא היה סנכרון" body="חברו בנק או כרטיס אשראי למעלה, והתנועות יורדו מיד." />
          ) : (
            <div className="card card--flush" style={{ marginTop: 6 }}>
              <div className="list">
                {sync.data.map((s) => (
                  <div key={s.institution} className="list-row">
                    <span className="list-row-main">
                      <span className="list-row-title">{s.institution_label}</span>
                      <span className={`list-row-sub${s.status === "failed" ? " neg" : ""}`}>
                        {s.status === "failed"
                          ? `נכשל${s.finished_at ? ` ${formatSyncTime(s.finished_at)}` : ""}: ${s.error_message ?? ""}`
                          : s.finished_at
                            ? `עודכן ${formatSyncTime(s.finished_at)}`
                            : "רץ עכשיו"}
                      </span>
                      {s.status === "failed" && s.last_success_at && (
                        <span className="list-row-sub">הצלחה אחרונה {formatSyncTime(s.last_success_at)}</span>
                      )}
                    </span>
                  </div>
                ))}
              </div>
            </div>
          )}
        </section>
      )}
      {accounts.data && accounts.data.length > 0 && (
        <section aria-label="חשבונות">
          <h2 className="group-label">חשבונות</h2>
          <div className="card card--flush" style={{ marginTop: 6 }}>
            <div className="list">
              {accounts.data.map((a) => (
                <div key={a.id} className="list-row">
                  <span className="list-row-main">
                    <span className="list-row-title">
                      {a.institution_label} <bdi dir="ltr">{a.account_number}</bdi>
                    </span>
                    <span className="list-row-sub">{a.account_type === "bank" ? "חשבון בנק" : "כרטיס אשראי"}</span>
                  </span>
                  <span className="list-row-end">
                    {a.balance === null ? "—" : a.account_type === "bank" ? <Money value={a.balance} decimals={2} /> : <><Money value={Math.abs(Number(a.balance))} decimals={0} /> לחיוב</>}
                  </span>
                </div>
              ))}
            </div>
          </div>
        </section>
      )}
    </SubScreen>
  );
}
