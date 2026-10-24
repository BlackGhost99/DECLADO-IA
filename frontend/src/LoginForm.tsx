import { useState, type FormEvent } from "react";
import { api, ApiError, type Me } from "./api";
import { Logo } from "./Icon";
import { LanguageSelector, tr, useI18n } from "./i18n";
import { navigate } from "./router";

export function LoginForm({ onLoggedIn }: { onLoggedIn: (me: Me) => void }) {
  const { t } = useI18n();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [secondFactor, setSecondFactor] = useState(false);
  const [code, setCode] = useState("");

  async function submit(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      if (secondFactor) {
        onLoggedIn(await api.verifyMfa(code));
      } else {
        const result = await api.login(email, password);
        if ("mfa_required" in result) setSecondFactor(true);
        else onLoggedIn(result);
      }
    } catch (err) {
      setError(err instanceof ApiError ? err.message : t("loginError"));
    } finally {
      setBusy(false);
    }
  }

  return (
    <main className="login-page">
      <form className="card login" onSubmit={submit} aria-labelledby="login-title">
        <div className="login-lang">
          <LanguageSelector />
        </div>
        <div className="login-brand">
          <Logo size={48} />
          <span>
            <strong>ClairTransit</strong>
            <small>{t("dash.heroSub")}</small>
          </span>
        </div>
        <h1 id="login-title">{t("loginTitle")}</h1>
        {secondFactor && <p>{t("mfa.enterCode")}</p>}
        {!secondFactor && (
          <label>
            {t("email")}
            <input type="email" autoComplete="username" required value={email}
                   onChange={(e) => setEmail(e.target.value)} />
          </label>
        )}
        {!secondFactor && (
          <label>
            {t("password")}
            <input type="password" autoComplete="current-password" required value={password}
                   onChange={(e) => setPassword(e.target.value)} />
          </label>
        )}
        {secondFactor && (
          <label>
            {t("mfa.code")}
            <input autoComplete="one-time-code" value={code} required
                   onChange={(e) => setCode(e.target.value)} />
          </label>
        )}
        {error && <p role="alert" className="error">⚠ {error}</p>}
        <button type="submit" className="btn-primary btn-block" disabled={busy}>
          {busy ? t("signingIn") : secondFactor ? t("mfa.validate") : t("login")}
        </button>
        {!secondFactor && (
          <p className="onb-small onb-sep">
            {tr("onb.noSpace")}{" "}
            <a href="#/demande" onClick={(e) => { e.preventDefault(); navigate("/demande"); }}>{tr("onb.requestLink")}</a>
          </p>
        )}
      </form>
    </main>
  );
}
