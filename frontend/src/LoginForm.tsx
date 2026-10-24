import { useState, type FormEvent } from "react";
import { api, ApiError, type Me } from "./api";
import { LanguageSelector, useI18n } from "./i18n";

export function LoginForm({ onLoggedIn }: { onLoggedIn: (me: Me) => void }) {
  const {t} = useI18n();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function submit(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      onLoggedIn(await api.login(email, password));
    } catch (err) {
      setError(err instanceof ApiError ? err.message : t("loginError"));
    } finally {
      setBusy(false);
    }
  }

  return (
    <main className="center">
      <form className="card login" onSubmit={submit} aria-labelledby="login-title">
        <LanguageSelector />
        <h1 id="login-title">{t("loginTitle")}</h1>
        <label>
          {t("email")}
          <input type="email" autoComplete="username" required value={email}
                 onChange={(e) => setEmail(e.target.value)} />
        </label>
        <label>
          {t("password")}
          <input type="password" autoComplete="current-password" required value={password}
                 onChange={(e) => setPassword(e.target.value)} />
        </label>
        {error && <p role="alert" className="error">⚠ {error}</p>}
        <button type="submit" disabled={busy}>{busy ? t("signingIn") : t("login")}</button>
      </form>
    </main>
  );
}
