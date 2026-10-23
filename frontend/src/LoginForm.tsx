import { useState, type FormEvent } from "react";
import { api, ApiError, type Me } from "./api";
import { Logo } from "./Icon";

export function LoginForm({ onLoggedIn }: { onLoggedIn: (me: Me) => void }) {
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
      setError(err instanceof ApiError ? err.message : "Connexion impossible. Réessayez.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <main className="login-page">
      <form className="card login" onSubmit={submit} aria-labelledby="login-title">
        <div className="login-brand">
          <Logo size={48} />
          <span>
            <strong>ClairTransit</strong>
            <small>Assistant de préparation douanière</small>
          </span>
        </div>
        <h1 id="login-title">Connexion à ClairTransit</h1>
        <label>
          Adresse e-mail
          <input type="email" autoComplete="username" required value={email}
                 onChange={(e) => setEmail(e.target.value)} />
        </label>
        <label>
          Mot de passe
          <input type="password" autoComplete="current-password" required value={password}
                 onChange={(e) => setPassword(e.target.value)} />
        </label>
        {error && <p role="alert" className="error">⚠ {error}</p>}
        <button type="submit" className="btn-primary btn-block" disabled={busy}>{busy ? "Connexion…" : "Se connecter"}</button>
      </form>
    </main>
  );
}
