import { Link } from "react-router-dom";

import { useAcknowledgeAlert, useAlerts } from "../api/queries";
import { ChevronStart } from "../components/Icons";
import { EmptyState, ErrorState, Loading } from "../components/States";
import { formatSyncTime } from "../lib/format";

export function AlertsScreen() {
  const alerts = useAlerts();
  const acknowledge = useAcknowledgeAlert();
  const unread = alerts.data?.filter((a) => !a.acknowledged) ?? [];

  return (
    <main className="screen">
      <Link to="/" className="back-link">
        <ChevronStart size={18} />
        תזרים
      </Link>
      <header className="screen-header">
        <h1 className="screen-title">התראות</h1>
        {unread.length > 1 && (
          <button type="button" className="button button--secondary button--small" onClick={() => unread.forEach((a) => acknowledge.mutate(a.id))}>
            סימון הכל כנקרא
          </button>
        )}
      </header>
      {alerts.isPending && <Loading rows={3} />}
      {alerts.isError && <ErrorState error={alerts.error} onRetry={() => alerts.refetch()} />}
      {alerts.data && alerts.data.length === 0 && (
        <EmptyState title="אין התראות" body="כאן יופיעו חריגות מהתקציב, יתרה נמוכה, חיובים גדולים וסנכרונים שנכשלו." />
      )}
      {alerts.data && alerts.data.length > 0 && (
        <div className="card card--flush">
          <div className="list">
            {alerts.data.map((alert) => (
              <div key={alert.id} className="list-row" style={{ alignItems: "flex-start", background: alert.acknowledged ? undefined : "var(--surface-2)" }}>
                <span className="list-row-main" style={{ whiteSpace: "pre-line" }}>
                  <span style={{ fontSize: 15, fontWeight: alert.acknowledged ? 400 : 500 }}>{alert.message}</span>
                  <span className="list-row-sub">{formatSyncTime(alert.triggered_at)}</span>
                </span>
                {!alert.acknowledged && (
                  <button type="button" className="button button--secondary button--small" onClick={() => acknowledge.mutate(alert.id)} aria-label={`סימון כנקרא: ${alert.message}`}>
                    נקרא
                  </button>
                )}
              </div>
            ))}
          </div>
        </div>
      )}
    </main>
  );
}
