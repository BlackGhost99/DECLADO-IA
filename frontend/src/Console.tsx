import { useEffect, useRef, useState, type FormEvent, type RefObject } from "react";
import {
  api,
  ApiError,
  type AccessRequestInfo,
  type Invitation,
  type NewOrganizationInput,
  type PlatformOrganization,
} from "./api";
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
          <button type="button" className="btn-primary" onClick={() => formRef.current?.querySelector("input")?.focus()}>
            <Icon name="plus" size={18} /> {tr("con.newCompany")}
          </button>
        )}
      </PageHeader>
      {error && <p role="alert" className="error">⚠ {error}</p>}
      {issued && <ActivationLink {...issued} />}
      <div className={view === "home" ? "onb-split" : undefined}>
        <Requests
          items={requests}
          full={view === "requests"}
          onAccept={(r) =>
            act(async () => issue(tr("con.linkFor", { name: r.contact_name }), (await api.acceptAccessRequest(r.id)).invitation))
          }
          onRefuse={(r, note) => act(() => api.refuseAccessRequest(r.id, note))}
        />
        {view === "home" && (
          <NewCompany
            formRef={formRef}
            onCreated={(name, invitation) => {
              issue(tr("con.linkFor", { name }), invitation);
              load();
            }}
          />
        )}
      </div>
      {view === "home" && (
        <Organizations
          items={organizations}
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

function orgState(o: PlatformOrganization): { tone: "green" | "amber" | "gray" | "red"; label: string } {
  if (!o.active) return { tone: "gray", label: tr("con.suspended") };
  if (o.members === 0 && o.admin_invitation) {
    return o.admin_invitation.status === "expired"
      ? { tone: "red", label: tr("con.invitationExpired") }
      : { tone: "amber", label: tr("con.invitationPending") };
  }
  return { tone: "green", label: tr("active") };
}

function Organizations({
  items,
  onState,
  onRenew,
}: {
  items: PlatformOrganization[] | null;
  onState: (o: PlatformOrganization, action: "suspend" | "reactivate") => void;
  onRenew: (invitation: Invitation) => void;
}) {
  return (
    <section className="card" aria-labelledby="orgs-title">
      <h2 id="orgs-title" className="card-title">{tr("con.companies")}</h2>
      {items === null ? (
        <p className="muted">{tr("loading")}</p>
      ) : items.length === 0 ? (
        <p className="empty">{tr("con.noCompany")}</p>
      ) : (
        <div className="table-wrap onb-table-wrap">
          <table className="data onb-table">
            <thead>
              <tr>
                <th scope="col">{tr("con.company")}</th>
                <th scope="col">{tr("onb.profile")}</th>
                <th scope="col">{tr("onb.country")}</th>
                <th scope="col">{tr("con.users")}</th>
                <th scope="col">{tr("status")}</th>
                <th scope="col"><span className="visually-hidden">{tr("col.actions")}</span></th>
              </tr>
            </thead>
            <tbody>
              {items.map((o) => {
                const state = orgState(o);
                return (
                  <tr key={o.id}>
                    <td>
                      <strong>{o.name}</strong>
                      {o.is_demo && <span className="block small muted">{tr("demo.fictitious")}</span>}
                    </td>
                    <td>{profileLabel(o.primary_profile)}</td>
                    <td>{countryLabel(o.country_code)}</td>
                    <td className="num">{o.max_users ? `${o.members} / ${o.max_users}` : o.members}</td>
                    <td><Chip tone={state.tone}>{state.label}</Chip></td>
                    <td>
                      <div className="onb-acts">
                        {o.active && o.members === 0 && o.admin_invitation && (
                          <button type="button" className="btn-outline-small" onClick={() => onRenew(o.admin_invitation!)}>
                            {tr("con.newLink")}
                          </button>
                        )}
                        <button type="button" className="btn-outline-small" onClick={() => onState(o, o.active ? "suspend" : "reactivate")}>
                          {tr(o.active ? "con.suspend" : "con.reactivate")}
                        </button>
                      </div>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
      <p className="onb-small">{tr("con.suspendHelp")}</p>
    </section>
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
