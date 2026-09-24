import type { ReactNode } from "react";

import { errorMessage } from "../api/client";
import { WarningIcon } from "./Icons";

export function Loading({ rows = 3, label = "טוען…" }: { rows?: number; label?: string }) {
  return (
    <div role="status" aria-live="polite" style={{ display: "flex", flexDirection: "column", gap: 14 }}>
      <span className="visually-hidden">{label}</span>
      <div className="skeleton" style={{ height: 150 }} />
      {Array.from({ length: rows - 1 }, (_, i) => (
        <div key={i} className="skeleton" style={{ height: 110 }} />
      ))}
    </div>
  );
}

export function ErrorState({ error, onRetry }: { error: unknown; onRetry?: () => void }) {
  return (
    <div className="card state" role="alert">
      <WarningIcon size={28} />
      <p className="state-title">לא הצלחנו לטעון</p>
      <p className="state-body">{errorMessage(error)}</p>
      {onRetry && (
        <button type="button" className="button button--secondary button--small" onClick={onRetry}>
          לנסות שוב
        </button>
      )}
    </div>
  );
}

export function EmptyState({ title, body, children }: { title: string; body?: string; children?: ReactNode }) {
  return (
    <div className="card state">
      <p className="state-title">{title}</p>
      {body && <p className="state-body">{body}</p>}
      {children}
    </div>
  );
}
