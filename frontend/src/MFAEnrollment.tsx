import { useState, type FormEvent } from "react";
import { api, ApiError, type Me } from "./api";

export function MFAEnrollment({ onComplete }: { onComplete: (me: Me) => void }) {
  const [setup, setSetup] = useState<{ secret: string; provisioning_uri: string } | null>(null);
  const [code, setCode] = useState("");
  const [recovery, setRecovery] = useState<string[] | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  async function begin() {
    setBusy(true);
    setError("");
    try {
      setSetup(await api.setupMfa());
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Impossible de démarrer la MFA.");
    } finally {
      setBusy(false);
    }
  }

  async function confirm(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError("");
    try {
      setRecovery((await api.confirmMfa(code)).recovery_codes);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Code incorrect.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <main className="center">
      <section className="card login">
        <h1>Sécurisation de votre compte</h1>
        <p>La double authentification protège l'accès aux factures et documents des sociétés.</p>
        {!setup && !recovery && <button type="button" onClick={() => void begin()} disabled={busy}>
          Configurer mon authentificateur
        </button>}
        {setup && !recovery && <>
          <p>Ouvrez une application TOTP (Google Authenticator, Aegis ou Microsoft Authenticator)
            et ajoutez le compte à l'aide de cette clé secrète :</p>
          <code style={{ overflowWrap: "anywhere" }}>{setup.secret}</code>
          <p>Vous pouvez aussi utiliser le lien d'initialisation :</p>
          <code style={{ overflowWrap: "anywhere" }}>{setup.provisioning_uri}</code>
          <form onSubmit={(e) => void confirm(e)}>
            <label>Code à six chiffres
              <input required value={code} inputMode="numeric" autoComplete="one-time-code"
                     onChange={(e) => setCode(e.target.value)} />
            </label>
            <button type="submit" disabled={busy}>Activer la MFA</button>
          </form>
        </>}
        {recovery && <>
          <h2>Codes de récupération</h2>
          <p>Conservez ces codes dans un endroit sûr. Chacun ne fonctionne qu'une fois.
            Ils ne seront plus affichés après cette page.</p>
          <pre style={{ whiteSpace: "pre-wrap", overflowWrap: "anywhere" }}>{recovery.join("\n")}</pre>
          <button type="button" onClick={() => void api.me().then(onComplete)}>J'ai sauvegardé mes codes</button>
        </>}
        {error && <p className="error" role="alert">{error}</p>}
      </section>
    </main>
  );
}
