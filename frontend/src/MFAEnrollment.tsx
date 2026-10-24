import { useState, type FormEvent } from "react";
import { api, ApiError, type Me } from "./api";
import { tr } from "./i18n";

export function MFAEnrollment({
  onComplete,
  onSkip,
  step,
}: {
  onComplete: (me: Me) => void;
  /** Activation d'un agent : la double authentification peut être configurée plus tard. */
  onSkip?: () => void;
  /** Étape affichée au-dessus du titre pendant l'activation d'un compte. */
  step?: string;
}) {
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
      setError(err instanceof ApiError ? err.message : tr("mfa.startFailed"));
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
      setError(err instanceof ApiError ? err.message : tr("mfa.wrongCode"));
    } finally {
      setBusy(false);
    }
  }

  return (
    <main className="login-page">
      <section className="card login">
        {step && <p className="onb-small">{step}</p>}
        <h1>{tr("mfa.title")}</h1>
        <p>{tr("mfa.intro")}</p>
        {!setup && !recovery && <button type="button" className="btn-primary btn-block" onClick={() => void begin()} disabled={busy}>
          {tr("mfa.configure")}
        </button>}
        {setup && !recovery && <>
          <p>{tr("mfa.openApp")}</p>
          <code style={{ overflowWrap: "anywhere" }}>{setup.secret}</code>
          <p>{tr("mfa.orLink")}</p>
          <code style={{ overflowWrap: "anywhere" }}>{setup.provisioning_uri}</code>
          <form onSubmit={(e) => void confirm(e)}>
            <label>{tr("mfa.sixDigits")}
              <input required value={code} inputMode="numeric" autoComplete="one-time-code"
                     onChange={(e) => setCode(e.target.value)} />
            </label>
            <button type="submit" className="btn-primary btn-block" disabled={busy}>{tr("mfa.activate")}</button>
          </form>
        </>}
        {recovery && <>
          <h2>{tr("mfa.recovery")}</h2>
          <p>{tr("mfa.keepSafe")}</p>
          <pre style={{ whiteSpace: "pre-wrap", overflowWrap: "anywhere" }}>{recovery.join("\n")}</pre>
          <button type="button" className="btn-primary btn-block" onClick={() => void api.me().then(onComplete)}>{tr("mfa.saved")}</button>
        </>}
        {error && <p className="error" role="alert">{error}</p>}
        {onSkip && !recovery && (
          <button type="button" className="btn-secondary btn-block" onClick={onSkip}>{tr("onb.later")}</button>
        )}
      </section>
    </main>
  );
}
