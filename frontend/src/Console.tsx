import { useEffect, useRef, useState, type FormEvent, type RefObject } from "react";
import { CompanyManagement } from "./CompanyManagement";
import {
  api,
  ApiError,
  type AccessRequestInfo,
  type Invitation,
  type NewOrganizationInput,
  type PlatformOrganization,
} from "./api";
import { PlatformAIPanel } from "./PlatformAI";
import { Icon } from "./Icon";
import { tr } from "./i18n";
import { ActivationLink, issuedLink, type IssuedLink, CountrySelect, countryLabel, Field, LOCALES, ProfileChoice, profileLabel } from "./Onboarding";
import { Chip, PageHeader, relativeTime } from "./ui";

const errorText = (err: unknown) => (err instanceof ApiError ? err.message : tr("saveError"));

/** Console de l'exploitant : sociétés clientes et demandes d'ouverture. Aucun accès aux dossiers. */
export function Console({ view }: { view: "home" | "requests" }) {
  const [requests, setRequests] = useState<AccessRequestInfo[] | null>(null);
  const [organizations, setOrganizations] = useState<PlatformOrganization[] | null>(null);
  const [issued, setIssued] = useState<IssuedLink | null>(null);
  const [error, setError] = useState("");
  const [showCreate, setShowCreate] = useState(false);
  const formRef = useRef<HTMLFormElement>(null);

  const load = () => {
    api.accessRequests(view === "home" ? "pending" : "").then(setRequests, () => setRequests([]));
    api.platformOrganizations().then(setOrganizations, () => setOrganizations([]));
  };
  useEffect(load, [view]);

  async function act(run: () => Promise<unknown>) {
    setError("");
    try {
      await run();
      load();
    } catch (err) {
      setError(errorText(err));
    }
  }

  const issue = (title: string, invitation: Invitation) => setIssued(issuedLink(title, invitation));

  return (
    <>
      <PageHeader title={tr(view === "home" ? "con.title" : "con.requests")} subtitle={tr("con.subtitle")}>
        {view === "home" && (
          <button type="button" className="btn-primary" aria-expanded={showCreate} onClick={() => setShowCreate((v) => !v)}>
            <Icon name="plus" size={18} /> {tr(showCreate ? "con.closeCreate" : "con.newCompany")}
          </button>
        )}
      </PageHeader>
      {error && <p role="alert" className="error">⚠ {error}</p>}
      {issued && <ActivationLink {...issued} />}
      {view === "home" && <PlatformAIPanel />}
      {view === "home" && organizations && <CompanyStats items={organizations} />}
      {(view === "requests" || requests === null || requests.length > 0) && (
        <Requests
          items={requests}
          full={view === "requests"}
          onAccept={(r) =>
            act(async () => issue(tr("con.linkFor", { name: r.contact_name }), (await api.acceptAccessRequest(r.id)).invitation))
          }
          onRefuse={(r, note) => act(() => api.refuseAccessRequest(r.id, note))}
        />
      )}
      {view === "home" && showCreate && (
        <div className="console-create">
          <NewCompany
            formRef={formRef}
            onCreated={(name, invitation) => {
              issue(tr("con.linkFor", { name }), invitation);
              setShowCreate(false);
              load();
            }}
          />
        </div>
      )}
      {view === "home" && (
        <CompanyManagement
          items={organizations}
          onRefresh={load}
          onState={(o, action) => act(() => api.setOrganizationState(o.id, action))}
          onRenew={(inv) =>
            act(async () => issue(tr("con.linkFor", { name: inv.full_name || inv.email }), await api.renewAdminInvitation(inv.id)))
          }
        />
      )}
    </>
  );
}

function Requests({
  items,
  full,
  onAccept,
  onRefuse,
}: {
  items: AccessRequestInfo[] | null;
  full: boolean;
  onAccept: (r: AccessRequestInfo) => void;
  onRefuse: (r: AccessRequestInfo, note: string) => void;
}) {
  const [refusing, setRefusing] = useState<string | null>(null);
  const [note, setNote] = useState("");
  const pending = items?.filter((r) => r.status === "pending").length ?? 0;
  return (
    <section className="card" aria-labelledby="requests-title">
      <h2 id="requests-title" className="card-title">
        {tr("con.requests")} {pending > 0 && <span className="chip chip-amber onb-count">{tr("con.pending", { n: pending })}</span>}
      </h2>
      {items === null ? (
        <p className="muted">{tr("loading")}</p>
      ) : items.length === 0 ? (
        <p className="empty">{tr("con.noRequest")}</p>
      ) : (
        <ul className="onb-requests">
          {items.map((r) => (
            <li key={r.id} className="onb-request">
              <div>
                <strong>{r.company_name}</strong>
                <span className="muted">
                  {profileLabel(r.primary_profile)} · {countryLabel(r.country_code)} · {tr("con.registration", { value: r.registration_number })}
                </span>
                <span>
                  {tr("con.contact", { name: r.contact_name })}
                  {r.contact_role && `, ${r.contact_role}`} · {r.contact_email}
                  {r.contact_phone && ` · ${r.contact_phone}`}
                </span>
                <span className="muted">{tr("con.received", { when: relativeTime(r.created_at) })}</span>
                {r.status !== "pending" && (
                  <span>
                    <Chip tone={r.status === "accepted" ? "green" : "gray"}>{tr(r.status === "accepted" ? "con.accepted" : "con.refused")}</Chip>
                    {r.decision_note && ` ${r.decision_note}`}
                  </span>
                )}
              </div>
              {r.status === "pending" &&
                (refusing === r.id ? (
                  <form
                    className="onb-refuse"
                    onSubmit={(e) => {
                      e.preventDefault();
                      onRefuse(r, note);
                      setRefusing(null);
                      setNote("");
                    }}
                  >
                    <Field label={tr("con.refuseReason")}>
                      <input id={`refuse-${r.id}`} value={note} onChange={(e) => setNote(e.target.value)} maxLength={500} />
                    </Field>
                    <div className="onb-acts">
                      <button type="submit" className="btn-secondary btn-small-pad">{tr("con.confirmRefuse")}</button>
                      <button type="button" className="btn-outline-small" onClick={() => setRefusing(null)}>{tr("cancel")}</button>
                    </div>
                  </form>
                ) : (
                  <div className="onb-acts">
                    <button type="button" className="btn-primary btn-small-pad" onClick={() => onAccept(r)}>
                      <Icon name="check" size={16} /> {tr("con.accept")}
                    </button>
                    <button type="button" className="btn-outline-small" onClick={() => setRefusing(r.id)}>{tr("con.refuse")}</button>
                  </div>
                ))}
            </li>
          ))}
        </ul>
      )}
      {!full && <p className="onb-small">{tr("con.acceptHelp")}</p>}
    </section>
  );
}

function CompanyStats({ items }: { items: PlatformOrganization[] }) {
  const active = items.filter((item) => item.active).length;
  const used = items.reduce((sum, item) => sum + item.members, 0);
  const pending = items.reduce((sum, item) => sum + item.pending_invitations, 0);
  const full = items.filter((item) => item.max_users !== null && item.members + item.pending_invitations >= item.max_users).length;
  return (
    <div className="console-stats" aria-label={tr("con.indicators")}>
      <div className="console-stat"><span>{tr("con.totalCompanies")}</span><strong>{items.length}</strong></div>
      <div className="console-stat"><span>{tr("con.activeCompanies")}</span><strong>{active}</strong></div>
      <div className="console-stat"><span>{tr("con.activeUsers")}</span><strong>{used}</strong></div>
      <div className="console-stat"><span>{tr("con.pendingInvites")}</span><strong>{pending}</strong></div>
      <div className="console-stat"><span>{tr("con.fullCompanies")}</span><strong>{full}</strong></div>
    </div>
  );
}

const EMPTY: NewOrganizationInput = {
  name: "",
  primary_profile: "transit",
  country_code: "GA",
  default_locale: "fr",
  max_users: null,
  admin_name: "",
  admin_email: "",
};

function NewCompany({
  formRef,
  onCreated,
}: {
  formRef: RefObject<HTMLFormElement | null>;
  onCreated: (name: string, invitation: Invitation) => void;
}) {
  const [form, setForm] = useState<NewOrganizationInput>(EMPTY);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const set = (key: keyof NewOrganizationInput) => (e: { target: { value: string } }) => setForm({ ...form, [key]: e.target.value });

  async function submit(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError("");
    try {
      const created = await api.createOrganization(form);
      onCreated(form.admin_name || form.admin_email, created.invitation);
      setForm(EMPTY);
    } catch (err) {
      setError(errorText(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <form ref={formRef} className="card onb-form" onSubmit={(e) => void submit(e)} aria-labelledby="new-company-title">
      <h2 id="new-company-title" className="nc-h2">{tr("con.newCompany")}</h2>
      <p className="onb-small">{tr("con.newCompanyHelp")}</p>
      <Field label={tr("onb.companyName")} required>
        <input id="org-name" required value={form.name} onChange={set("name")} />
      </Field>
      <ProfileChoice name="org-profile" value={form.primary_profile} onChange={(p) => setForm({ ...form, primary_profile: p })} />
      <div className="onb-row">
        <Field label={tr("onb.country")} required>
          <CountrySelect id="org-country" value={form.country_code} onChange={(c) => setForm({ ...form, country_code: c })} />
        </Field>
        <Field label={tr("con.language")} required>
          <select id="org-locale" value={form.default_locale} onChange={set("default_locale")}>
            {LOCALES.map(([code, name]) => (
              <option key={code} value={code}>{name}</option>
            ))}
          </select>
        </Field>
      </div>
      <Field label={tr("con.seats")}>
        <input id="org-seats" type="number" min={1} value={form.max_users ?? ""} placeholder={tr("con.noLimit")}
               onChange={(e) => setForm({ ...form, max_users: e.target.value ? Number(e.target.value) : null })} />
      </Field>
      <h3 className="onb-h3">{tr("con.companyAdmin")}</h3>
      <div className="onb-row">
        <Field label={tr("name")} required>
          <input id="org-admin" required value={form.admin_name} onChange={set("admin_name")} />
        </Field>
        <Field label={tr("email")} required>
          <input id="org-admin-email" type="email" required value={form.admin_email} onChange={set("admin_email")} />
        </Field>
      </div>
      {error && <p role="alert" className="error">⚠ {error}</p>}
      <button type="submit" className="btn-primary btn-block" disabled={busy}>{tr("con.create")}</button>
    </form>
  );
}
