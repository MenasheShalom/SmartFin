import { useMemo, useState } from "react";

import { errorMessage } from "../api/client";
import {
  UNCATEGORIZED_QUERY,
  useAccounts,
  useCategories,
  useCategoryMutations,
  useTransactions,
  useUpdateTransaction,
} from "../api/queries";
import type { Account, Category, Transaction } from "../api/types";
import { CategoryPicker, GROUP_LABELS, type Group } from "../components/CategoryPicker";
import { SearchIcon } from "../components/Icons";
import { Money } from "../components/Money";
import { MonthSwitcher } from "../components/MonthSwitcher";
import { Sheet } from "../components/Sheet";
import { EmptyState, ErrorState, Loading } from "../components/States";
import { useToast } from "../components/Toast";
import { TransactionRow } from "../components/TransactionRow";
import { byId } from "../lib/categories";
import { currentMonth, formatDay, ltr, relativeDay } from "../lib/format";

type Tab = "queue" | "all";

export function TransactionsScreen() {
  const queue = useTransactions(UNCATEGORIZED_QUERY);
  const count = queue.data?.length ?? 0;
  const [tab, setTab] = useState<Tab>(count > 0 || queue.isPending ? "queue" : "all");

  return (
    <main className="screen">
      <h1 className="screen-title">תנועות</h1>
      <div className="segmented" role="tablist" aria-label="תצוגה">
        <button type="button" role="tab" aria-selected={tab === "queue"} onClick={() => setTab("queue")}>
          לסיווג{count > 0 ? ` (${count})` : ""}
        </button>
        <button type="button" role="tab" aria-selected={tab === "all"} onClick={() => setTab("all")}>
          כל התנועות
        </button>
      </div>
      {tab === "queue" ? <Queue onDone={() => setTab("all")} /> : <AllTransactions />}
    </main>
  );
}

function Queue({ onDone }: { onDone: () => void }) {
  const queue = useTransactions(UNCATEGORIZED_QUERY);
  const categories = useCategories();
  const accounts = useAccounts();
  const [skipped, setSkipped] = useState<number[]>([]);

  if (queue.isPending || categories.isPending) return <Loading rows={2} />;
  if (queue.isError) return <ErrorState error={queue.error} onRetry={() => queue.refetch()} />;
  if (categories.isError) return <ErrorState error={categories.error} onRetry={() => categories.refetch()} />;

  const pending = queue.data.filter((t) => !skipped.includes(t.id));
  if (queue.data.length === 0) {
    return (
      <EmptyState title="הכל מסווג" body="כל התנועות קיבלו קטגוריה. תנועות חדשות יחכו כאן אחרי הסנכרון הבא.">
        <button type="button" className="button button--secondary button--small" onClick={onDone}>
          לכל התנועות
        </button>
      </EmptyState>
    );
  }
  if (pending.length === 0) {
    return (
      <EmptyState title="דילגת על כל התנועות" body="אפשר לחזור אליהן מתי שנוח.">
        <button type="button" className="button button--secondary button--small" onClick={() => setSkipped([])}>
          להתחיל מחדש
        </button>
      </EmptyState>
    );
  }
  const txn = pending[0];
  return (
    <>
      <p className="muted" style={{ fontSize: 14 }} aria-live="polite">
        {queue.data.length - pending.length + 1} מתוך {queue.data.length}
      </p>
      <CategorizeCard
        key={txn.id}
        txn={txn}
        categories={categories.data}
        account={accounts.data?.find((a) => a.id === txn.account_id)}
        onSkip={() => setSkipped([...skipped, txn.id])}
      />
    </>
  );
}

function CategorizeCard({
  txn,
  categories,
  account,
  onSkip,
}: {
  txn: Transaction;
  categories: Category[];
  account?: Account;
  onSkip: () => void;
}) {
  const [categoryId, setCategoryId] = useState<number | null>(null);
  const [remember, setRemember] = useState(true);
  const [adding, setAdding] = useState<Group | null>(null);
  const update = useUpdateTransaction();
  const toast = useToast();
  const income = Number(txn.amount) > 0;

  const save = () => {
    if (categoryId === null) return;
    update.mutate(
      { id: txn.id, category_id: categoryId, create_rule: remember },
      {
        onSuccess: (result) => {
          const name = categories.find((c) => c.id === categoryId)?.name ?? "";
          toast(
            result.recategorized > 0
              ? `נשמר ב״${name}״. עוד ${result.recategorized} תנועות סווגו לפי אותו כלל.`
              : `נשמר ב״${name}״.`,
          );
        },
        onError: (err) => toast(errorMessage(err)),
      },
    );
  };

  return (
    <>
      <section className="card" style={{ gap: 18, padding: "22px 20px" }}>
        <div className="txn-hero">
          <p className="muted" style={{ fontSize: 14 }}>
            {account ? `${account.institution_label} ${ltr(account.account_number)} · ` : ""}
            {formatDay(txn.date)}
          </p>
          <p className="txn-hero-name">{txn.description}</p>
          {txn.memo && <p className="muted" style={{ fontSize: 14 }}>{txn.memo}</p>}
          <p className={`txn-hero-amount${income ? " pos" : ""}`}>
            <Money value={txn.amount} sign={income ? "always" : "auto"} />
          </p>
        </div>
        <CategoryPicker
          categories={categories}
          value={categoryId}
          onChange={setCategoryId}
          initialGroup={income ? "other" : "variable"}
          onAddNew={setAdding}
        />
        <label className="check">
          <input type="checkbox" checked={remember} onChange={(e) => setRemember(e.target.checked)} />
          לזכור לתנועות הבאות מ״{txn.description}״
        </label>
      </section>
      <div className="button-row">
        <button type="button" className="button" onClick={save} disabled={categoryId === null || update.isPending}>
          {update.isPending ? "שומר…" : "שמירה והבאה"}
        </button>
        <button type="button" className="button button--secondary" onClick={onSkip} style={{ minWidth: 96 }}>
          דלג
        </button>
      </div>
      <p className="tip">משתנה נכנסת לתקציב השבועי. קבועה נכנסת לתוכנית החודשית, ובחודש הבא תופיע בה מראש.</p>
      {adding && (
        <NewCategorySheet
          group={adding}
          categories={categories}
          onClose={() => setAdding(null)}
          onCreated={(c) => {
            setCategoryId(c.id);
            setAdding(null);
          }}
        />
      )}
    </>
  );
}

export function NewCategorySheet({
  group,
  categories,
  onClose,
  onCreated,
}: {
  group: Group;
  categories: Category[];
  onClose: () => void;
  onCreated: (category: Category) => void;
}) {
  const [name, setName] = useState("");
  const parents = categories.filter(
    (c) =>
      c.parent_id === null &&
      (group === "other" ? c.kind !== "expense" : c.kind === "expense" && c.is_fixed === (group === "fixed")),
  );
  const [parentId, setParentId] = useState<number | "">("");
  const [otherKind, setOtherKind] = useState<"income" | "transfer">("income");
  const { create } = useCategoryMutations();
  const toast = useToast();

  const submit = () => {
    const trimmed = name.trim();
    if (!trimmed) return;
    create.mutate(
      parentId === ""
        ? { name: trimmed, kind: group === "other" ? otherKind : "expense", is_fixed: group === "fixed" }
        : { name: trimmed, parent_id: parentId },
      {
        onSuccess: onCreated,
        onError: (err) => toast(errorMessage(err)),
      },
    );
  };

  return (
    <Sheet title={`קטגוריה חדשה · ${GROUP_LABELS[group]}`} onClose={onClose}>
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
        <label className="field">
          בתוך
          <select className="input" value={parentId} onChange={(e) => setParentId(e.target.value ? Number(e.target.value) : "")}>
            <option value="">קטגוריה ראשית</option>
            {parents.map((p) => (
              <option key={p.id} value={p.id}>
                {p.name}
              </option>
            ))}
          </select>
        </label>
        {group === "other" && parentId === "" && (
          <div className="segmented" role="group" aria-label="סוג">
            <button type="button" aria-pressed={otherKind === "income"} onClick={() => setOtherKind("income")}>
              הכנסה
            </button>
            <button type="button" aria-pressed={otherKind === "transfer"} onClick={() => setOtherKind("transfer")}>
              העברה בין חשבונות
            </button>
          </div>
        )}
        <button type="submit" className="button" disabled={!name.trim() || create.isPending}>
          יצירה
        </button>
      </form>
    </Sheet>
  );
}

function AllTransactions() {
  const [month, setMonth] = useState(currentMonth());
  const [search, setSearch] = useState("");
  const [limit, setLimit] = useState(100);
  const [editing, setEditing] = useState<Transaction | null>(null);
  const q = search.trim();
  const txns = useTransactions(q ? { q, limit } : { month, limit });
  const categories = useCategories();
  const accounts = useAccounts();
  const map = byId(categories.data);

  const groups = useMemo(() => {
    const byDay = new Map<string, Transaction[]>();
    for (const t of txns.data ?? []) byDay.set(t.date, [...(byDay.get(t.date) ?? []), t]);
    return [...byDay.entries()];
  }, [txns.data]);

  return (
    <>
      <label className="search">
        <span className="visually-hidden">חיפוש</span>
        <SearchIcon size={18} />
        <input
          className="input"
          type="search"
          placeholder="חיפוש בכל התנועות"
          value={search}
          onChange={(e) => {
            setSearch(e.target.value);
            setLimit(100);
          }}
        />
      </label>
      {!q && <MonthSwitcher month={month} onChange={(m) => { setMonth(m); setLimit(100); }} />}

      {(txns.isPending || categories.isPending) && <Loading rows={3} />}
      {txns.isError && <ErrorState error={txns.error} onRetry={() => txns.refetch()} />}
      {txns.data && categories.data && groups.length === 0 && (
        <EmptyState title={q ? "לא נמצאו תנועות" : "אין תנועות בחודש הזה"} />
      )}
      {categories.data &&
        groups.map(([day, rows]) => (
          <section key={day} aria-label={formatDay(day)}>
            <h2 className="group-label">{relativeDay(day)}</h2>
            <div className="card card--flush" style={{ marginTop: 6 }}>
              <div className="list">
                {rows.map((t) => (
                  <TransactionRow
                    key={t.id}
                    txn={t}
                    categories={map}
                    account={accounts.data?.find((a) => a.id === t.account_id)}
                    onSelect={setEditing}
                  />
                ))}
              </div>
            </div>
          </section>
        ))}
      {txns.data && txns.data.length >= limit && (
        <button type="button" className="button button--secondary" onClick={() => setLimit(limit + 100)}>
          לטעון עוד
        </button>
      )}
      {editing && categories.data && (
        <EditTransactionSheet txn={editing} categories={categories.data} onClose={() => setEditing(null)} />
      )}
    </>
  );
}

function EditTransactionSheet({ txn, categories, onClose }: { txn: Transaction; categories: Category[]; onClose: () => void }) {
  const [categoryId, setCategoryId] = useState<number | null>(txn.category_id);
  const [remember, setRemember] = useState(false);
  const [adding, setAdding] = useState<Group | null>(null);
  const update = useUpdateTransaction();
  const toast = useToast();

  const save = (category: number | null) =>
    update.mutate(
      { id: txn.id, category_id: category, create_rule: category !== null && remember },
      {
        onSuccess: (result) => {
          toast(
            category === null
              ? "הסיווג חזר לכללים האוטומטיים."
              : result.recategorized > 0
                ? `נשמר. עוד ${result.recategorized} תנועות סווגו לפי אותו כלל.`
                : "נשמר.",
          );
          onClose();
        },
        onError: (err) => toast(errorMessage(err)),
      },
    );

  return (
    <Sheet title={txn.description} onClose={onClose}>
      <p className="muted" style={{ fontSize: 14 }}>
        {formatDay(txn.date)} · <Money value={txn.amount} decimals={2} />
        {txn.memo ? ` · ${txn.memo}` : ""}
      </p>
      <CategoryPicker categories={categories} value={categoryId} onChange={setCategoryId} onAddNew={setAdding} />
      <label className="check">
        <input type="checkbox" checked={remember} onChange={(e) => setRemember(e.target.checked)} />
        להחיל גם על תנועות עתידיות מ״{txn.description}״
      </label>
      <button type="button" className="button" disabled={categoryId === null || update.isPending} onClick={() => save(categoryId)}>
        שמירה
      </button>
      {txn.category_manual && (
        <button type="button" className="button button--secondary" disabled={update.isPending} onClick={() => save(null)}>
          החזרה לסיווג אוטומטי
        </button>
      )}
      {adding && (
        <NewCategorySheet
          group={adding}
          categories={categories}
          onClose={() => setAdding(null)}
          onCreated={(c) => {
            setCategoryId(c.id);
            setAdding(null);
          }}
        />
      )}
    </Sheet>
  );
}
