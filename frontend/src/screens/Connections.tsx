import { useState } from "react";

import { ApiError, errorMessage } from "../api/client";
import { useConnectionMutations, useConnections } from "../api/queries";
import type { Company, Connection } from "../api/types";
import { ChevronEnd, PlusIcon, WarningIcon } from "../components/Icons";
import { Sheet } from "../components/Sheet";
import { Loading } from "../components/States";
import { useToast } from "../components/Toast";
import { formatSyncTime } from "../lib/format";

// israeli-bank-scrapers login field ids, as each site calls them
const FIELD_LABELS: Record<string, string> = {
  username: "שם משתמש",
  userCode: "קוד משתמש",
  password: "סיסמה",
  id: "תעודת זהות",
  nationalID: "תעודת זהות",
  num: "קוד מזהה",
  card6Digits: "6 הספרות האחרונות של הכרטיס",
};
const NUMERIC_FIELDS = new Set(["id", "nationalID", "card6Digits"]);

export function syncErrorText(errorType: string | null): string {
  switch (errorType) {
    case "INVALID_PASSWORD":
      return "פרטי הכניסה שגויים. עדכנו אותם כאן.";
    case "CHANGE_PASSWORD":
      return "האתר מבקש להחליף סיסמה. החליפו אותה באתר ועדכנו כאן.";
    case "ACCOUNT_BLOCKED":
      return "הגישה נחסמה באתר. שחררו אותה שם ונסו שוב.";
    case "TIMEOUT":
      return "האתר לא ענה בזמן. ננסה שוב בסנכרון הבא.";
    default:
      return "ההתחברות נכשלה. ננסה שוב בסנכרון הבא.";
  }
}

function statusText(c: Connection): { text: string; failed?: boolean } {
  if (c.sync === "running") return { text: "מתחבר ומוריד תנועות…" };
  if (c.sync === "queued") return { text: "ממתין לסנכרון" };
  if (c.last_sync && !c.last_sync.ok) return { text: syncErrorText(c.last_sync.error_type), failed: true };
  if (c.last_sync?.finished_at) return { text: `מחובר · עודכן ${formatSyncTime(c.last_sync.finished_at)}` };
  return { text: "מחובר" };
}

export function ConnectionsSection() {
  const connections = useConnections();
  const { syncAll } = useConnectionMutations();
  const toast = useToast();
  const [editing, setEditing] = useState<Connection | "new" | null>(null);

  const syncing = connections.data?.connections.some((c) => c.sync) ?? false;
  const unreachable = connections.error instanceof ApiError && connections.error.status === 503;

  return (
    <section aria-labelledby="connections-title">
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 12 }}>
        <h2 id="connections-title" className="group-label">
          בנקים וכרטיסי אשראי
        </h2>
        {connections.data && connections.data.connections.length > 0 && (
          <button
            type="button"
            className="button button--secondary button--small"
            disabled={syncing || syncAll.isPending}
            onClick={() => syncAll.mutate(undefined, { onError: (err) => toast(errorMessage(err)) })}
          >
            {syncing ? "מסנכרן…" : "סנכרון עכשיו"}
          </button>
        )}
      </div>

      {connections.isPending && <Loading rows={2} />}
      {connections.isError && (
        <div className="card state" role="alert" style={{ marginTop: 6 }}>
          <WarningIcon size={28} />
          <p className="state-title">{unreachable ? "שירות הסנכרון לא זמין" : "לא הצלחנו לטעון"}</p>
          <p className="state-body">
            {unreachable
              ? "בדקו בשרת שהשירות scraper רץ (docker compose ps), ונסו שוב."
              : errorMessage(connections.error)}
          </p>
          <button type="button" className="button button--secondary button--small" onClick={() => connections.refetch()}>
            לנסות שוב
          </button>
        </div>
      )}

      {connections.data && (
        <div className="card card--flush" style={{ marginTop: 6 }}>
          <div className="list">
            {connections.data.connections.length === 0 && (
              <div className="list-row">
                <span className="list-row-main">
                  <span className="list-row-title">עוד לא חיברתם בנק או כרטיס</span>
                  <span className="list-row-sub">
                    הזינו את הפרטים שבהם אתם נכנסים לאתר. הם נשמרים מוצפנים בשרת הביתי בלבד, ומשמשים רק להורדת התנועות.
                  </span>
                </span>
              </div>
            )}
            {connections.data.connections.map((c) => {
              const status = statusText(c);
              return (
                <button key={c.id} type="button" className="list-row" onClick={() => setEditing(c)}>
                  <span className="list-row-main">
                    <span className="list-row-title">
                      {c.label}
                      {c.hint && (
                        <>
                          {" "}
                          <bdi dir="ltr" className="muted">
                            {c.hint}
                          </bdi>
                        </>
                      )}
                    </span>
                    <span className={`list-row-sub${status.failed ? " neg" : ""}`}>{status.text}</span>
                  </span>
                  <ChevronEnd size={18} />
                </button>
              );
            })}
            <button type="button" className="list-row" onClick={() => setEditing("new")}>
              <span className="list-row-main">
                <span className="list-row-title">הוספת בנק או כרטיס אשראי</span>
              </span>
              <PlusIcon size={20} />
            </button>
          </div>
        </div>
      )}

      {editing && connections.data && (
        <ConnectionSheet
          connection={editing === "new" ? null : editing}
          companies={connections.data.companies}
          onClose={() => setEditing(null)}
        />
      )}
    </section>
  );
}

function ConnectionSheet({
  connection,
  companies,
  onClose,
}: {
  connection: Connection | null;
  companies: Company[];
  onClose: () => void;
}) {
  const [companyId, setCompanyId] = useState(connection?.company ?? "");
  const [values, setValues] = useState<Record<string, string>>({});
  const { add, update, remove } = useConnectionMutations();
  const toast = useToast();
  const company = companies.find((c) => c.id === companyId);
  const fields = company?.login_fields ?? [];
  const complete = fields.length > 0 && fields.every((f) => (values[f] ?? "").trim() !== "");
  const pending = add.isPending || update.isPending || remove.isPending;
  const mutationError = add.error ?? update.error;

  const submit = () => {
    if (!company || !complete) return;
    const credentials = Object.fromEntries(fields.map((f) => [f, values[f]]));
    const done = () => {
      toast(
        connection
          ? "הפרטים עודכנו. מתחבר מחדש…"
          : "נשמר. מתחבר ומוריד תנועות מהשנה האחרונה; זה יכול לקחת כמה דקות.",
      );
      onClose();
    };
    if (connection) update.mutate({ id: connection.id, credentials }, { onSuccess: done });
    else add.mutate({ company: company.id, credentials }, { onSuccess: done });
  };

  const onDelete = () => {
    if (!connection || !window.confirm(`לנתק את ${connection.label}? התנועות שכבר ירדו יישארו.`)) return;
    remove.mutate(connection.id, {
      onSuccess: () => {
        toast("החיבור הוסר.");
        onClose();
      },
      onError: (err) => toast(errorMessage(err)),
    });
  };

  const group = (kind: Company["kind"]) => companies.filter((c) => c.kind === kind);

  return (
    <Sheet title={connection ? connection.label : "חיבור בנק או כרטיס"} onClose={onClose}>
      <form
        style={{ display: "flex", flexDirection: "column", gap: 14 }}
        autoComplete="off"
        onSubmit={(e) => {
          e.preventDefault();
          submit();
        }}
      >
        {connection ? (
          <p className="field-hint">
            מטעמי אבטחה הפרטים השמורים לא מוצגים. כדי לעדכן, הזינו את כל פרטי הכניסה מחדש.
          </p>
        ) : (
          <label className="field">
            בנק או חברת אשראי
            <select className="input" value={companyId} onChange={(e) => setCompanyId(e.target.value)} required>
              <option value="">בחרו…</option>
              <optgroup label="בנקים">
                {group("bank").map((c) => (
                  <option key={c.id} value={c.id}>
                    {c.label}
                  </option>
                ))}
              </optgroup>
              <optgroup label="כרטיסי אשראי">
                {group("card").map((c) => (
                  <option key={c.id} value={c.id}>
                    {c.label}
                  </option>
                ))}
              </optgroup>
            </select>
          </label>
        )}

        {fields.map((field) => (
          <label key={field} className="field">
            {FIELD_LABELS[field] ?? field}
            <input
              className="input"
              dir="ltr"
              type={field === "password" ? "password" : "text"}
              inputMode={NUMERIC_FIELDS.has(field) ? "numeric" : undefined}
              autoComplete={field === "password" ? "new-password" : "off"}
              autoCapitalize="none"
              spellCheck={false}
              maxLength={200}
              value={values[field] ?? ""}
              onChange={(e) => setValues({ ...values, [field]: e.target.value })}
              required
            />
          </label>
        ))}

        {company && (
          <p className="field-hint">
            הפרטים עוברים ישירות לשירות הסנכרון בשרת הביתי ונשמרים שם מוצפנים. הם לא נשמרים במסד הנתונים או בגיבויים.
          </p>
        )}

        {mutationError && (
          <p className="error-text" role="alert">
            {mutationError instanceof ApiError && mutationError.status === 503
              ? "שירות הסנכרון לא זמין כרגע. נסו שוב בעוד רגע."
              : errorMessage(mutationError)}
          </p>
        )}

        <button type="submit" className="button" disabled={!complete || pending}>
          {connection ? "עדכון פרטי הכניסה" : "חיבור"}
        </button>
        {connection && (
          <button type="button" className="button button--danger" onClick={onDelete} disabled={pending}>
            ניתוק
          </button>
        )}
      </form>
    </Sheet>
  );
}
