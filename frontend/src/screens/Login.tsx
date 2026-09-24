import { useState, type FormEvent } from "react";

import { ApiError, errorMessage } from "../api/client";
import { useLogin } from "../api/queries";
import { LogoMark } from "../components/Icons";

export function LoginScreen({ serverError }: { serverError?: unknown }) {
  const [password, setPassword] = useState("");
  const login = useLogin();

  const submit = (event: FormEvent) => {
    event.preventDefault();
    if (password) login.mutate(password);
  };

  let error: string | null = null;
  if (login.error instanceof ApiError && login.error.status === 401) error = "הסיסמה שגויה.";
  else if (login.error instanceof ApiError && login.error.status === 503)
    error = "עדיין לא הוגדרה סיסמה. הריצו python -m app.password והוסיפו את APP_PASSWORD_HASH לקובץ ‎.env.";
  else if (login.error) error = errorMessage(login.error);
  else if (serverError) error = errorMessage(serverError);

  return (
    <main className="login">
      <form className="login-card" onSubmit={submit}>
        <div className="brand">
          <LogoMark />
          SmartFin
        </div>
        <p className="muted">התזרים שלך, בבית שלך.</p>
        <label className="field">
          סיסמה
          <input
            className="input"
            type="password"
            autoComplete="current-password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            autoFocus
            required
            aria-invalid={error ? true : undefined}
            aria-describedby={error ? "login-error" : undefined}
          />
        </label>
        {error && (
          <p id="login-error" className="error-text" role="alert">
            {error}
          </p>
        )}
        <button className="button button--block" type="submit" disabled={login.isPending || !password}>
          {login.isPending ? "מתחבר…" : "כניסה"}
        </button>
      </form>
    </main>
  );
}
