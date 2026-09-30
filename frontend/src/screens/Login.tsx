import { useState, type FormEvent, type ReactNode } from "react";

import { ApiError, errorMessage } from "../api/client";
import { useAuthStatus, useLogin, useSetup } from "../api/queries";
import { LogoMark } from "../components/Icons";
import { Loading } from "../components/States";

export const MIN_PASSWORD = 8;

export function LoginScreen({ serverError }: { serverError?: unknown }) {
  const status = useAuthStatus();
  if (status.isPending) {
    return (
      <main className="screen screen--bare">
        <Loading />
      </main>
    );
  }
  if (status.data?.setup_required) return <SetupForm />;
  return <LoginForm serverError={serverError ?? status.error} />;
}

function LoginCard({ intro, onSubmit, children }: { intro: string; onSubmit: () => void; children: ReactNode }) {
  const submit = (event: FormEvent) => {
    event.preventDefault();
    onSubmit();
  };
  return (
    <main className="login">
      <form className="login-card" onSubmit={submit}>
        <div className="brand">
          <LogoMark />
          SmartFin
        </div>
        <p className="muted">{intro}</p>
        {children}
      </form>
    </main>
  );
}

function ErrorText({ error }: { error: string | null }) {
  if (!error) return null;
  return (
    <p id="login-error" className="error-text" role="alert">
      {error}
    </p>
  );
}

function LoginForm({ serverError }: { serverError?: unknown }) {
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const login = useLogin();
  const ready = username.trim() !== "" && password !== "";

  let error: string | null = null;
  if (login.error instanceof ApiError && login.error.status === 401) error = "שם המשתמש או הסיסמה שגויים.";
  else if (login.error) error = errorMessage(login.error);
  else if (serverError) error = errorMessage(serverError);
  const invalid = error ? { "aria-invalid": true, "aria-describedby": "login-error" } : {};

  return (
    <LoginCard intro="התזרים שלך, בבית שלך." onSubmit={() => ready && login.mutate({ username, password })}>
      <label className="field">
        שם משתמש
        <input
          className="input"
          autoComplete="username"
          autoCapitalize="none"
          value={username}
          onChange={(e) => setUsername(e.target.value)}
          autoFocus
          required
          {...invalid}
        />
      </label>
      <label className="field">
        סיסמה
        <input
          className="input"
          type="password"
          autoComplete="current-password"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          required
          {...invalid}
        />
      </label>
      <ErrorText error={error} />
      <button className="button button--block" type="submit" disabled={login.isPending || !ready}>
        {login.isPending ? "מתחבר…" : "כניסה"}
      </button>
    </LoginCard>
  );
}

function SetupForm() {
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [again, setAgain] = useState("");
  const [tried, setTried] = useState(false);
  const setup = useSetup();

  let error: string | null = null;
  if (tried && password.length < MIN_PASSWORD) error = `הסיסמה צריכה להיות באורך ${MIN_PASSWORD} תווים לפחות.`;
  else if (tried && again !== password) error = "הסיסמאות לא תואמות.";
  else if (setup.error instanceof ApiError && setup.error.status === 409)
    error = "כבר נוצר משתמש. רעננו את הדף כדי להתחבר.";
  else if (setup.error) error = errorMessage(setup.error);
  const invalid = error ? { "aria-invalid": true, "aria-describedby": "login-error" } : {};

  const submit = () => {
    setTried(true);
    if (!username.trim() || password.length < MIN_PASSWORD || again !== password) return;
    setup.mutate({ username: username.trim(), password });
  };

  return (
    <LoginCard intro="ברוכים הבאים! בחרו שם משתמש וסיסמה לכניסה לאפליקציה." onSubmit={submit}>
      <label className="field">
        שם משתמש
        <input
          className="input"
          autoComplete="username"
          autoCapitalize="none"
          maxLength={64}
          value={username}
          onChange={(e) => setUsername(e.target.value)}
          autoFocus
          required
        />
      </label>
      <label className="field">
        סיסמה
        <span className="field-hint">{MIN_PASSWORD} תווים לפחות</span>
        <input
          className="input"
          type="password"
          autoComplete="new-password"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          required
          {...invalid}
        />
      </label>
      <label className="field">
        הסיסמה שוב
        <input
          className="input"
          type="password"
          autoComplete="new-password"
          value={again}
          onChange={(e) => setAgain(e.target.value)}
          required
          {...invalid}
        />
      </label>
      <ErrorText error={error} />
      <button className="button button--block" type="submit" disabled={setup.isPending || !username.trim()}>
        {setup.isPending ? "יוצר…" : "יצירת משתמש"}
      </button>
    </LoginCard>
  );
}
