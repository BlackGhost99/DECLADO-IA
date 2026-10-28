import { useEffect, useState, type FormEvent } from "react";
import {
  api,
  ApiError,
  ROLE_LABELS,
  type Agency,
  type Importer,
  type Invitation,
  type Member,
  type Membership,
  type OrganizationOverview,
  type Role,
} from "./api";
import { DocumentPolicies } from "./DocumentPolicies";
import { Icon } from "./Icon";
import { tr, useBusinessLabels, type MessageKey } from "./i18n";
import { ActivationLink, Field, issuedLink, type IssuedLink } from "./Onboarding";
import { AISettingsPanel, ImporterAIChoice } from "./OnlineAI";
import { Chip, initials, PageHeader } from "./ui";

export type AdminTab = "importers" | "documents" | "users" | "agencies" | "ia";
const ADMIN_TABS: AdminTab[] = ["importers", "documents", "users", "agencies", "ia"];
export const adminTab = (value: string | null): AdminTab =>
  ADMIN_TABS.includes(value as AdminTab) ? (value as AdminTab) : "importers";

/** Administration de la société : importateurs pour tous, utilisateurs pour l'administrateur. */
export function Administration({
  membership,
  selfEmail = "",
  initialTab = "importers",
}: {
  membership: Membership;
  selfEmail?: string;
  initialTab?: AdminTab;
}) {
  const canEdit = membership.roles.some((r) => r === "declarant" || r === "validator");
  const isAdmin = membership.roles.includes("org_admin");
  const [tab, setTab] = useState<AdminTab>(isAdmin || initialTab === "documents" ? initialTab : "importers");

  return (
    <>
      <PageHeader title={tr("nav.administration")} subtitle={tr("adm.settingsOf", { name: membership.organization.name })} />
      <div role="tablist" className="tabs">
        <button type="button" role="tab" aria-selected={tab === "importers"} onClick={() => setTab("importers")}>
          <Icon name="folder" size={18} /> {tr("importers")}
        </button>
        <button type="button" role="tab" aria-selected={tab === "documents"} onClick={() => setTab("documents")}>
          <Icon name="file" size={18} /> {tr("adm.caseDocs")}
        </button>
        {isAdmin && (
          <button type="button" role="tab" aria-selected={tab === "users"} onClick={() => setTab("users")}>
            <Icon name="users" size={18} /> {tr("adm.users")}
          </button>
        )}
        {isAdmin && (
          <button type="button" role="tab" aria-selected={tab === "agencies"} onClick={() => setTab("agencies")}>
            <Icon name="mapPin" size={18} /> {tr("adm.agencies")}
          </button>
        )}
        {isAdmin && (
          <button type="button" role="tab" aria-selected={tab === "ia"} onClick={() => setTab("ia")}>
            <Icon name="shield" size={18} /> {tr("adm.ai")}
          </button>
        )}
      </div>
      {tab === "importers" ? (
        <Importers canEdit={canEdit} isAdmin={isAdmin} />
      ) : tab === "documents" ? (
        <DocumentPolicies isAdmin={isAdmin} />
      ) : tab === "agencies" ? (
        <Agencies />
      ) : tab === "ia" ? (
        <AISettingsPanel organizationName={membership.organization.name} onManageClients={() => setTab("importers")} />
      ) : (
        <Members selfEmail={selfEmail} />
      )}
    </>
  );
}

function Importers({ canEdit, isAdmin }: { canEdit: boolean; isAdmin: boolean }) {
  const [items, setItems] = useState<Importer[]>([]);
  const [editing, setEditing] = useState<Importer | null>(null);
  const canChooseAI = canEdit || isAdmin;
  const [name, setName] = useState("");
  const [nif, setNif] = useState("");
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = async () => setItems((await api.importers()).results);
  useEffect(() => {
    void load();
  }, []);

  async function create(event: FormEvent) {
    event.preventDefault();
    setError(null);
    setMessage(null);
    try {
      const created = await api.createImporter({ name, identifiers: nif ? { nif } : {} });
      const dups = created.possible_duplicates ?? [];
      setMessage(
        dups.length
          ? tr("adm.duplicate", { names: dups.map((d) => d.name).join(", ") })
          : tr("importerSaved"),
      );
      setName("");
      setNif("");
      await load();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : tr("saveError"));
    }
  }

  return (
    <section className="card" aria-labelledby="importers-title">
      <h2 id="importers-title" className="card-title">{tr("adm.importersClients")}</h2>
      {items.length === 0 ? (
        <p className="empty">{tr("importerNone")}</p>
      ) : (
        <div className="table-wrap">
          <table className="data">
            <thead>
              <tr>
                <th scope="col">{tr("name")}</th><th scope="col">{tr("identifiers")}</th><th scope="col">{tr("imp.aiCol")}</th>
                {canChooseAI && <th scope="col"><span className="visually-hidden">{tr("actions")}</span></th>}
              </tr>
            </thead>
            <tbody>
              {items.map((i) => (
                <tr key={i.id}>
                  <td>{i.name}</td>
                  <td>{Object.entries(i.identifiers).map(([k, v]) => `${k.toUpperCase()} ${v}`).join(" · ")}</td>
                  <td>{i.ai_refused ? <Chip tone="gray">{tr("imp.aiRefused")}</Chip> : <Chip tone="green">{tr("imp.aiAllowed")}</Chip>}</td>
                  {canChooseAI && (
                    <td>
                      <button type="button" className="btn-outline-small" aria-label={`${tr("imp.edit")} : ${i.name}`} onClick={() => setEditing(i)}>
                        <Icon name="edit" size={14} /> {tr("imp.edit")}
                      </button>
                    </td>
                  )}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {editing && (
        <ImporterAIChoice
          key={editing.id}
          importer={editing}
          isAdmin={isAdmin}
          onClose={() => setEditing(null)}
          onSaved={(updated) => {
            setItems((all) => all.map((x) => (x.id === updated.id ? updated : x)));
            setEditing(null);
            setError(null);
            setMessage(tr("imp.aiSaved"));
          }}
        />
      )}
      {canEdit && (
        <form className="form-grid" onSubmit={create}>
          <label>
            {tr("name")}
            <input required value={name} onChange={(e) => setName(e.target.value)} />
          </label>
          <label>
            {tr("optionalTax")}
            <input value={nif} onChange={(e) => setNif(e.target.value)} />
          </label>
          <div className="form-end">
            <button type="submit" className="btn-primary"><Icon name="plus" /> {tr("add")}</button>
          </div>
        </form>
      )}
      {message && <p role="status">{message}</p>}
      {error && <p role="alert" className="error">⚠ {error}</p>}
    </section>
  );
}

const INVITABLE: [Role, MessageKey][] = [
  ["declarant", "adm.roleDeclarantHint"],
  ["validator", "adm.roleValidatorHint"],
  ["org_admin", "adm.roleAdminHint"],
];

const INVITATION_TONE = { pending: "amber", expired: "red", accepted: "green", revoked: "gray" } as const;

function Members({ selfEmail }: { selfEmail: string }) {
  const labels = useBusinessLabels();
  const [members, setMembers] = useState<Member[]>([]);
  const [invitations, setInvitations] = useState<Invitation[]>([]);
  const [agencies, setAgencies] = useState<Agency[]>([]);
  const [overview, setOverview] = useState<OrganizationOverview | null>(null);
  const [issued, setIssued] = useState<IssuedLink | null>(null);
  const [error, setError] = useState("");

  const load = () => {
    void api.members().then((p) => setMembers(p.results));
    void api.invitations().then(setInvitations, () => setInvitations([]));
    void api.agencies().then(setAgencies, () => setAgencies([]));
    void api.organizationOverview().then(setOverview, () => setOverview(null));
  };
  useEffect(load, []);

  async function act(run: () => Promise<unknown>) {
    setError("");
    try {
      await run();
      load();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : tr("saveError"));
    }
  }

  const roleNames = (roles: Role[]) => roles.map((r) => labels.role(r, ROLE_LABELS[r] ?? r)).join(", ");
  const renew = (inv: Invitation) =>
    act(async () => {
      const fresh = await api.invitationAction(inv.id, "renew");
      setIssued(issuedLink(tr("con.linkFor", { name: inv.full_name || inv.email }), fresh));
    });

  return (
    <>
      {issued && <ActivationLink {...issued} />}
      {error && <p role="alert" className="error">⚠ {error}</p>}
      <div className="onb-split onb-split-wide">
        <section className="card" aria-labelledby="members-title">
          <h2 id="members-title" className="card-title">
            {tr("orgUsers")}
            {overview && (
              <span className="muted onb-count">
                {overview.max_users ? `${overview.seats_used} / ${overview.max_users}` : overview.seats_used}
              </span>
            )}
          </h2>
          <p className="muted small">{tr("adm.neverDeleted")}</p>
          <div className="table-wrap onb-table-wrap">
            <table className="data onb-table">
              <thead>
                <tr>
                  <th scope="col">{tr("adm.user")}</th>
                  <th scope="col">{tr("rolesHeader")}</th>
                  <th scope="col">{tr("adm.agency")}</th>
                  <th scope="col">{tr("status")}</th>
                  <th scope="col"><span className="visually-hidden">{tr("col.actions")}</span></th>
                </tr>
              </thead>
              <tbody>
                {members.map((m) => (
                  <tr key={m.id}>
                    <td>
                      <span className="person">
                        <span className="avatar small-avatar">{initials(m.full_name || m.email)}</span>
                        <span>
                          {m.full_name || m.email}
                          {m.full_name && <span className="block small muted">{m.email}</span>}
                        </span>
                      </span>
                    </td>
                    <td>{roleNames(m.roles)}</td>
                    <td>
                      {agencies.length > 0 ? (
                        <select
                          aria-label={tr("adm.agencyOf", { name: m.full_name || m.email })}
                          value={m.agency ?? ""}
                          onChange={(e) => void act(() => api.setMemberAgency(m.id, e.target.value || null))}
                        >
                          <option value="">{tr("adm.noAgency")}</option>
                          {agencies.map((a) => (
                            <option key={a.id} value={a.id}>{a.name}</option>
                          ))}
                        </select>
                      ) : (
                        <span className="muted">{m.agency_name ?? "—"}</span>
                      )}
                    </td>
                    <td>{m.active ? <Chip tone="green">{tr("active")}</Chip> : <Chip tone="gray">{tr("inactive")}</Chip>}</td>
                    <td>
                      <div className="onb-acts">
                        {m.email === selfEmail ? null : m.active ? (
                          <button type="button" className="btn-outline-small" onClick={() => void act(() => api.deactivateMember(m.id))}>
                            {tr("adm.deactivate")}
                          </button>
                        ) : (
                          <button type="button" className="btn-outline-small" onClick={() => void act(() => api.reactivateMember(m.id))}>
                            {tr("adm.reactivate")}
                          </button>
                        )}
                      </div>
                    </td>
                  </tr>
                ))}
                {invitations.map((inv) => (
                  <tr key={inv.id}>
                    <td>
                      <span className="person">
                        <span className="avatar small-avatar">{initials(inv.full_name || inv.email)}</span>
                        <span>
                          {inv.full_name || inv.email}
                          {inv.full_name && <span className="block small muted">{inv.email}</span>}
                        </span>
                      </span>
                    </td>
                    <td>{roleNames(inv.roles)}</td>
                    <td>{inv.agency_name ?? "—"}</td>
                    <td>
                      <Chip tone={INVITATION_TONE[inv.status]}>{tr(inv.status === "expired" ? "con.invitationExpired" : "con.invitationPending")}</Chip>
                    </td>
                    <td>
                      <div className="onb-acts">
                        <button type="button" className="btn-outline-small" onClick={() => void renew(inv)}>{tr("con.newLink")}</button>
                        <button type="button" className="btn-outline-small" onClick={() => void act(() => api.invitationAction(inv.id, "revoke"))}>
                          {tr("cancel")}
                        </button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
        <InviteForm
          agencies={agencies}
          onInvited={(inv) => {
            setIssued(issuedLink(tr("con.linkFor", { name: inv.full_name || inv.email }), inv));
            load();
          }}
        />
      </div>
    </>
  );
}

function InviteForm({ agencies, onInvited }: { agencies: Agency[]; onInvited: (inv: Invitation) => void }) {
  const labels = useBusinessLabels();
  const [form, setForm] = useState({ email: "", full_name: "", agency_id: "" });
  const [roles, setRoles] = useState<Role[]>(["declarant"]);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  async function submit(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError("");
    try {
      onInvited(await api.invite({ ...form, roles, agency_id: form.agency_id || null }));
      setForm({ email: "", full_name: "", agency_id: form.agency_id });
      setRoles(["declarant"]);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : tr("saveError"));
    } finally {
      setBusy(false);
    }
  }

  const toggle = (role: Role) => setRoles(roles.includes(role) ? roles.filter((r) => r !== role) : [...roles, role]);

  return (
    <form className="card onb-form" onSubmit={(e) => void submit(e)} aria-labelledby="invite-title">
      <h2 id="invite-title" className="nc-h2">{tr("adm.inviteTitle")}</h2>
      <Field label={tr("name")} required>
        <input id="invite-name" required value={form.full_name} onChange={(e) => setForm({ ...form, full_name: e.target.value })} />
      </Field>
      <Field label={tr("email")} required>
        <input id="invite-email" type="email" required value={form.email} onChange={(e) => setForm({ ...form, email: e.target.value })} />
      </Field>
      <fieldset className="nc-field plain-fieldset">
        <legend className="nc-label">{tr("rolesHeader")}<span className="nc-req" aria-hidden="true"> *</span></legend>
        <div className="onb-checks">
          {INVITABLE.map(([role, hint]) => (
            <label key={role} className="onb-check">
              <input type="checkbox" checked={roles.includes(role)} onChange={() => toggle(role)} />
              <span>
                <strong>{labels.role(role, ROLE_LABELS[role])}</strong>
                <small>{tr(hint)}</small>
              </span>
            </label>
          ))}
        </div>
      </fieldset>
      {agencies.length > 0 && (
        <Field label={tr("adm.agency")}>
          <select id="invite-agency" value={form.agency_id} onChange={(e) => setForm({ ...form, agency_id: e.target.value })}>
            <option value="">{tr("adm.noAgency")}</option>
            {agencies.map((a) => (
              <option key={a.id} value={a.id}>{a.name}</option>
            ))}
          </select>
        </Field>
      )}
      {error && <p role="alert" className="error">⚠ {error}</p>}
      <button type="submit" className="btn-primary btn-block" disabled={busy || roles.length === 0}>{tr("adm.createInvitation")}</button>
      <p className="onb-note"><Icon name="shield" size={18} /><span>{tr("adm.neverPassword")}</span></p>
    </form>
  );
}

function Agencies() {
  const [items, setItems] = useState<Agency[] | null>(null);
  const [form, setForm] = useState({ name: "", code: "" });
  const [error, setError] = useState("");
  const load = () => void api.agencies().then(setItems, () => setItems([]));
  useEffect(load, []);

  async function create(event: FormEvent) {
    event.preventDefault();
    setError("");
    try {
      await api.createAgency(form);
      setForm({ name: "", code: "" });
      load();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : tr("saveError"));
    }
  }

  return (
    <section className="card" aria-labelledby="agencies-title">
      <h2 id="agencies-title" className="card-title">{tr("adm.agencies")}</h2>
      <p className="muted small">{tr("adm.agenciesHelp")}</p>
      {items === null ? (
        <p className="muted">{tr("loading")}</p>
      ) : items.length === 0 ? (
        <p className="empty">{tr("adm.noAgencyYet")}</p>
      ) : (
        <div className="table-wrap">
          <table className="data">
            <thead>
              <tr><th scope="col">{tr("name")}</th><th scope="col">{tr("adm.agencyCode")}</th></tr>
            </thead>
            <tbody>
              {items.map((a) => (
                <tr key={a.id}><td>{a.name}</td><td className="code">{a.code}</td></tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      <form className="form-grid" onSubmit={(e) => void create(e)}>
        <label>
          {tr("name")}
          <input id="agency-name" required value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} />
        </label>
        <label>
          {tr("adm.agencyCode")}
          <input id="agency-code" required maxLength={40} value={form.code} onChange={(e) => setForm({ ...form, code: e.target.value })} />
        </label>
        <div className="form-end">
          <button type="submit" className="btn-primary"><Icon name="plus" /> {tr("add")}</button>
        </div>
      </form>
      {error && <p role="alert" className="error">⚠ {error}</p>}
    </section>
  );
}
