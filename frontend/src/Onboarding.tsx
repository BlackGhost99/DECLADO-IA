import { useEffect, useState, type FormEvent, type ReactNode } from "react";
import {
  activationLink,
  api,
  ApiError,
  ROLE_LABELS,
  type AccessRequestInput,
  type BusinessProfile,
  type InvitationPreview,
  type Me,
} from "./api";
import { Icon, Logo, type IconName } from "./Icon";
import { LanguageSelector, tr, useBusinessLabels, useI18n, type MessageKey } from "./i18n";
import { MFAEnrollment } from "./MFAEnrollment";
import { navigate } from "./router";

/** Pays de la CEMAC (codes ISO), nommés par les libellés déjà traduits. */
export const CEMAC_COUNTRIES: [string, MessageKey][] = [
  ["GA", "country.gabon"],
  ["CM", "country.cameroon"],
  ["CG", "country.congo"],
  ["CF", "country.car"],
  ["GQ", "country.eqGuinea"],
  ["TD", "country.chad"],
];

export const countryLabel = (code: string) => {
  const found = CEMAC_COUNTRIES.find(([c]) => c === code);
  return found ? tr(found[1]) : code;
};

/** Noms des langues dans leur propre écriture : ils ne se traduisent pas. */
export const LOCALES: [string, string][] = [
  ["fr", "Français"],
  ["en", "English"],
  ["es", "Español"],
  ["ar", "العربية"],
];

const PROFILES: [BusinessProfile, IconName, MessageKey, MessageKey][] = [
  ["transit", "ship", "onb.profile.transit", "onb.profile.transitHint"],
  ["importer", "box", "onb.profile.importer", "onb.later"],
  ["logistics", "truck", "onb.profile.logistics", "onb.later"],
  ["expert", "scale", "onb.profile.expert", "onb.later"],
];

/** Seul le métier transitaire est ouvert en V1 ; les autres sont annoncés, jamais simulés. */
export const OPEN_PROFILES: BusinessProfile[] = ["transit"];

export const profileLabel = (profile: BusinessProfile) =>
  tr(PROFILES.find(([p]) => p === profile)?.[2] ?? "onb.profile.transit");

export function Field({ label, required, children }: { label: string; required?: boolean; children: ReactNode }) {
  return (
    <label className="nc-field">
      <span className="nc-label">
        {label}
        {required && <span className="nc-req" aria-hidden="true"> *</span>}
      </span>
      <span className="nc-control">{children}</span>
    </label>
  );
}

export function ProfileChoice({ value, onChange, name }: { value: BusinessProfile; onChange: (p: BusinessProfile) => void; name: string }) {
  return (
    <div className="nc-field">
      <span className="nc-label">
        {tr("onb.profile")}
        <span className="nc-req" aria-hidden="true"> *</span>
      </span>
      <div className="onb-choices" role="radiogroup" aria-label={tr("onb.profile")}>
        {PROFILES.map(([profile, icon, label, hint]) => {
          const open = OPEN_PROFILES.includes(profile);
          return (
            <label key={profile} className={`onb-choice${value === profile ? " onb-on" : ""}${open ? "" : " onb-off"}`}>
              <input type="radio" name={name} checked={value === profile} disabled={!open} onChange={() => onChange(profile)} />
              <Icon name={icon} size={20} />
              <span>
                <strong>{tr(label)}</strong>
                <small>{tr(hint)}</small>
              </span>
            </label>
          );
        })}
      </div>
    </div>
  );
}

export function CountrySelect({ value, onChange, id }: { value: string; onChange: (code: string) => void; id: string }) {
  return (
    <select id={id} value={value} onChange={(e) => onChange(e.target.value)}>
      {CEMAC_COUNTRIES.map(([code, key]) => (
        <option key={code} value={code}>{tr(key)}</option>
      ))}
    </select>
  );
}

/** Lien d'activation à transmettre : copié en un clic, ou sélectionné si le presse-papiers est refusé. */
export function ActivationLink({ token, title }: { token: string; title?: string }) {
  const link = activationLink(token);
  const [copied, setCopied] = useState(false);
  const [id] = useState(() => `link-${Math.random().toString(36).slice(2)}`);
  async function copy() {
    try {
      await navigator.clipboard.writeText(link);
      setCopied(true);
    } catch {
      const node = document.getElementById(id);
      if (node) window.getSelection()?.selectAllChildren(node);
    }
  }
  return (
    <div className="onb-link" role="status">
      <Icon name="info" size={18} />
      <div>
        <strong>{title ?? tr("onb.linkCreated")}</strong>
        <span>{tr("onb.linkHelp")}</span>
        <code id={id}>{link}</code>
      </div>
      <button type="button" className="btn-secondary btn-small" onClick={() => void copy()}>
        <Icon name={copied ? "check" : "copy"} size={16} /> {copied ? tr("onb.copied") : tr("onb.copy")}
      </button>
    </div>
  );
}

function AuthShell({ title, wide, children }: { title: string; wide?: boolean; children: ReactNode }) {
  const { t } = useI18n();
  return (
    <main className="login-page">
      <section className={`card login onb-auth${wide ? " onb-auth-wide" : ""}`} aria-label={title}>
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
        <h1>{title}</h1>
        {children}
      </section>
    </main>
  );
}

const message = (err: unknown, fallback: MessageKey) => (err instanceof ApiError ? err.message : tr(fallback));

/** Premier lancement d'un serveur vide : création unique du compte exploitant. */
export function FirstLaunch({ onDone }: { onDone: (me: Me) => void }) {
  const [form, setForm] = useState({ full_name: "", email: "", password: "", confirm: "" });
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const set = (key: keyof typeof form) => (e: { target: { value: string } }) => setForm({ ...form, [key]: e.target.value });

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (form.password !== form.confirm) {
      setError(tr("onb.mismatch"));
      return;
    }
    setBusy(true);
    setError("");
    try {
      onDone(await api.setup({ full_name: form.full_name, email: form.email, password: form.password }));
    } catch (err) {
      setError(message(err, "saveError"));
    } finally {
      setBusy(false);
    }
  }

  return (
    <AuthShell title={tr("onb.setupTitle")}>
      <form className="onb-form" onSubmit={(e) => void submit(e)}>
        <p className="onb-lead">{tr("onb.setupLead")}</p>
        <Field label={tr("onb.fullName")} required>
          <input id="setup-name" required value={form.full_name} onChange={set("full_name")} autoComplete="name" />
        </Field>
        <Field label={tr("email")} required>
          <input id="setup-email" type="email" required value={form.email} onChange={set("email")} autoComplete="username" />
        </Field>
        <Field label={tr("password")} required>
          <input id="setup-password" type="password" required minLength={12} value={form.password} onChange={set("password")}
                 placeholder={tr("onb.min12")} autoComplete="new-password" />
        </Field>
        <Field label={tr("onb.confirmPassword")} required>
          <input id="setup-confirm" type="password" required value={form.confirm} onChange={set("confirm")} autoComplete="new-password" />
        </Field>
        <p className="onb-note"><Icon name="shield" size={18} /><span>{tr("onb.setupNote")}</span></p>
        {error && <p role="alert" className="error">⚠ {error}</p>}
        <button type="submit" className="btn-primary btn-block" disabled={busy}>{tr("onb.setupSubmit")}</button>
        <p className="onb-small">{tr("onb.setupOnce")}</p>
      </form>
    </AuthShell>
  );
}

const EMPTY_REQUEST: AccessRequestInput = {
  company_name: "",
  primary_profile: "transit",
  country_code: "GA",
  registration_number: "",
  contact_name: "",
  contact_role: "",
  contact_email: "",
  contact_phone: "",
  preferred_locale: "fr",
};

/** Demande d'espace : publique, rien n'est ouvert avant l'accord de l'exploitant. */
export function AccessRequestForm() {
  const { locale } = useI18n();
  const [form, setForm] = useState<AccessRequestInput>(EMPTY_REQUEST);
  const [sent, setSent] = useState(false);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const set = (key: keyof AccessRequestInput) => (e: { target: { value: string } }) => setForm({ ...form, [key]: e.target.value });

  async function submit(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError("");
    try {
      await api.requestAccess({ ...form, preferred_locale: locale });
      setSent(true);
    } catch (err) {
      setError(message(err, "saveError"));
    } finally {
      setBusy(false);
    }
  }

  if (sent) {
    return (
      <AuthShell title={tr("onb.requestSentTitle")}>
        <p className="onb-lead">{tr("onb.requestSent")}</p>
        <button type="button" className="btn-secondary btn-block" onClick={() => navigate("/")}>{tr("onb.backToLogin")}</button>
      </AuthShell>
    );
  }

  return (
    <AuthShell title={tr("onb.requestTitle")} wide>
      <form className="onb-form" onSubmit={(e) => void submit(e)}>
        <p className="onb-lead">{tr("onb.requestLead")}</p>
        <Field label={tr("onb.companyName")} required>
          <input id="req-company" required value={form.company_name} onChange={set("company_name")} />
        </Field>
        <ProfileChoice name="req-profile" value={form.primary_profile} onChange={(p) => setForm({ ...form, primary_profile: p })} />
        <div className="onb-row">
          <Field label={tr("onb.country")} required>
            <CountrySelect id="req-country" value={form.country_code} onChange={(c) => setForm({ ...form, country_code: c })} />
          </Field>
          <Field label={tr("onb.registration")} required>
            <input id="req-rccm" required value={form.registration_number} onChange={set("registration_number")}
                   placeholder={tr("onb.registrationHint")} />
          </Field>
        </div>
        <h2 className="onb-h3">{tr("onb.contact")}</h2>
        <div className="onb-row">
          <Field label={tr("name")} required>
            <input id="req-contact" required value={form.contact_name} onChange={set("contact_name")} autoComplete="name" />
          </Field>
          <Field label={tr("onb.contactRole")}>
            <input id="req-role" value={form.contact_role} onChange={set("contact_role")} />
          </Field>
        </div>
        <div className="onb-row">
          <Field label={tr("email")} required>
            <input id="req-email" type="email" required value={form.contact_email} onChange={set("contact_email")} autoComplete="email" />
          </Field>
          <Field label={tr("onb.phone")}>
            <input id="req-phone" type="tel" value={form.contact_phone} onChange={set("contact_phone")} autoComplete="tel" />
          </Field>
        </div>
        <p className="onb-note"><Icon name="info" size={18} /><span>{tr("onb.requestNote")}</span></p>
        {error && <p role="alert" className="error">⚠ {error}</p>}
        <button type="submit" className="btn-primary btn-block" disabled={busy}>{tr("onb.requestSubmit")}</button>
        <p className="onb-small">
          <a href="#/" onClick={(e) => { e.preventDefault(); navigate("/"); }}>{tr("onb.haveAccount")}</a>
        </p>
      </form>
    </AuthShell>
  );
}

/** Activation depuis un lien d'invitation : l'invité choisit son mot de passe, puis sa double authentification. */
export function Activation({ token, onDone }: { token: string; onDone: (me: Me) => void }) {
  const labels = useBusinessLabels();
  const [preview, setPreview] = useState<InvitationPreview | null>(null);
  const [invalid, setInvalid] = useState(false);
  const [form, setForm] = useState({ full_name: "", password: "", confirm: "" });
  const [joined, setJoined] = useState<Me | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [current, setCurrent] = useState<Me | null>(null);

  useEffect(() => {
    // Activer ce lien ferme la session ouverte dans ce navigateur : on le dit avant.
    api.me().then(setCurrent, () => setCurrent(null));
  }, []);

  useEffect(() => {
    api.lookupInvitation(token).then(
      (p) => {
        setPreview(p);
        setForm((f) => ({ ...f, full_name: p.full_name }));
      },
      () => setInvalid(true),
    );
  }, [token]);

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (!preview?.existing_account && form.password !== form.confirm) {
      setError(tr("onb.mismatch"));
      return;
    }
    setBusy(true);
    setError("");
    try {
      const me = await api.acceptInvitation({ token, full_name: form.full_name, password: form.password });
      if (me.mfa_enabled) finish(me);
      else setJoined(me);
    } catch (err) {
      setError(message(err, "saveError"));
    } finally {
      setBusy(false);
    }
  }

  function finish(me: Me) {
    navigate("/");
    onDone(me);
  }

  if (joined) {
    const admin = preview?.roles.includes("org_admin") ?? false;
    // Obligatoire pour un administrateur ; un agent peut la configurer plus tard (sauf si le serveur l'exige).
    const skippable = !admin && !joined.mfa_required_for_access;
    return <MFAEnrollment onComplete={finish} onSkip={skippable ? () => finish(joined) : undefined} step={tr("onb.step2")} />;
  }

  if (invalid) {
    return (
      <AuthShell title={tr("onb.activateTitle")}>
        <p role="alert" className="error">⚠ {tr("onb.invalidLink")}</p>
        <button type="button" className="btn-secondary btn-block" onClick={() => navigate("/")}>{tr("onb.backToLogin")}</button>
      </AuthShell>
    );
  }

  if (!preview) {
    return <p className="center">{tr("loading")}</p>;
  }

  const roles = preview.roles.map((r) => labels.role(r, ROLE_LABELS[r] ?? r)).join(", ");
  return (
    <AuthShell title={tr("onb.activateTitle")}>
      <form className="onb-form" onSubmit={(e) => void submit(e)}>
        <ol className="onb-steps">
          <li className="onb-step-on">{tr("onb.stepPassword")}</li>
          <li>{tr("onb.stepMfa")}</li>
        </ol>
        <p className="onb-lead">{tr("onb.invitedAs", { roles, organization: preview.organization_name })}</p>
        {current && current.email.toLowerCase() !== preview.email.toLowerCase() && (
          <p className="onb-note" role="status">
            <Icon name="info" size={18} />
            <span>{tr("onb.otherSession", { email: current.email })}</span>
          </p>
        )}
        <Field label={tr("email")}>
          <input id="act-email" type="email" value={preview.email} readOnly autoComplete="username" />
        </Field>
        {preview.existing_account ? (
          <>
            <p className="onb-note"><Icon name="info" size={18} /><span>{tr("onb.existingAccount")}</span></p>
            <Field label={tr("password")} required>
              <input id="act-password" type="password" required value={form.password}
                     onChange={(e) => setForm({ ...form, password: e.target.value })} autoComplete="current-password" />
            </Field>
          </>
        ) : (
          <>
            <Field label={tr("onb.displayName")} required>
              <input id="act-name" required value={form.full_name} onChange={(e) => setForm({ ...form, full_name: e.target.value })} autoComplete="name" />
            </Field>
            <Field label={tr("onb.choosePassword")} required>
              <input id="act-password" type="password" required minLength={12} value={form.password} placeholder={tr("onb.min12")}
                     onChange={(e) => setForm({ ...form, password: e.target.value })} autoComplete="new-password" />
            </Field>
            <Field label={tr("onb.confirmPassword")} required>
              <input id="act-confirm" type="password" required value={form.confirm}
                     onChange={(e) => setForm({ ...form, confirm: e.target.value })} autoComplete="new-password" />
            </Field>
          </>
        )}
        {error && <p role="alert" className="error">⚠ {error}</p>}
        <button type="submit" className="btn-primary btn-block" disabled={busy}>{tr("onb.continue")}</button>
        <p className="onb-small">{tr("onb.nobodyKnows")}</p>
      </form>
    </AuthShell>
  );
}
