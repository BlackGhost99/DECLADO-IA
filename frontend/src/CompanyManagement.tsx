import { useEffect, useState, type FormEvent } from "react";
import { api, ApiError, type Invitation, type PlatformCompanyDetail, type PlatformOrganization } from "./api";
import { Icon } from "./Icon";
import { tr } from "./i18n";
import { countryLabel, profileLabel } from "./Onboarding";
import { Chip } from "./ui";

type CompanyAction = "suspend" | "reactivate";
const message = (error: unknown) => error instanceof ApiError ? error.message : tr("saveError");
const limit = (value: number | null) => value === null ? tr("con.noLimit") : String(value);

function stateOf(o: PlatformOrganization) {
  if (!o.active) return { tone: "gray" as const, label: tr("con.suspended") };
  if (o.members === 0 && o.admin_invitation) return {
    tone: (o.admin_invitation.status === "expired" ? "red" : "amber") as "red" | "amber",
    label: tr(o.admin_invitation.status === "expired" ? "con.invitationExpired" : "con.invitationPending"),
  };
  return { tone: "green" as const, label: tr("active") };
}

export function CompanyManagement({
  items, onRefresh, onState, onRenew,
}: {
  items: PlatformOrganization[] | null;
  onRefresh: () => void;
  onState: (organization: PlatformOrganization, action: CompanyAction) => void;
  onRenew: (invitation: Invitation) => void;
}) {
  const [query, setQuery] = useState("");
  const [selected, setSelected] = useState<string | null>(null);
  const [detail, setDetail] = useState<PlatformCompanyDetail | null>(null);
  const [loadError, setLoadError] = useState("");
  const [confirming, setConfirming] = useState<{ organization: PlatformOrganization; action: CompanyAction } | null>(null);
  const [loading, setLoading] = useState(false);

  const refreshDetail = (id: string) => {
    setLoading(true);
    setLoadError("");
    return api.platformCompany(id)
      .then(setDetail, (error: unknown) => { setLoadError(message(error)); setDetail(null); })
      .finally(() => setLoading(false));
  };
  useEffect(() => {
    if (selected) void refreshDetail(selected);
    else setDetail(null);
  }, [selected]);
  const filtered = (items ?? []).filter((o) =>
    [o.name, o.country_code, profileLabel(o.primary_profile)].join(" ").toLocaleLowerCase().includes(query.toLocaleLowerCase())
  );

  return (
    <section className="card console-companies" aria-labelledby="companies-title">
      <div className="console-section-heading">
        <div>
          <h2 id="companies-title" className="card-title">{tr("con.companies")}</h2>
          <p className="muted small">{tr("con.companyControlHelp")}</p>
        </div>
        <label className="console-search">
          <span className="visually-hidden">{tr("con.searchCompanies")}</span>
          <Icon name="search" size={17}/>
          <input value={query} onChange={(e) => setQuery(e.target.value)} placeholder={tr("con.searchCompanies")} />
        </label>
      </div>
      {items === null ? <p className="muted">{tr("loading")}</p> : items.length === 0 ?
        <p className="empty">{tr("con.noCompany")}</p> : (
        <div className="table-wrap onb-table-wrap">
          <table className="data onb-table">
            <thead><tr>
              <th scope="col">{tr("con.company")}</th>
              <th scope="col">{tr("onb.profile")}</th>
              <th scope="col">{tr("onb.country")}</th>
              <th scope="col">{tr("con.users")}</th>
              <th scope="col">{tr("adm.agencies")}</th>
              <th scope="col">{tr("status")}</th>
              <th scope="col">{tr("col.actions")}</th>
            </tr></thead>
            <tbody>{filtered.map((o) => {
              const s = stateOf(o), seats = o.members + o.pending_invitations;
              const full = o.max_users !== null && seats >= o.max_users;
              return <tr key={o.id} className={selected === o.id ? "console-selected" : ""}>
                <td><strong>{o.name}</strong>{o.is_demo && <span className="block small muted">{tr("demo.fictitious")}</span>}</td>
                <td>{profileLabel(o.primary_profile)}</td>
                <td>{countryLabel(o.country_code)}</td>
                <td><span className={full ? "console-quota-full" : ""}>{o.members} / {limit(o.max_users)}{full ? " ⚠" : ""}</span>
                  {o.pending_invitations > 0 && <span className="block small muted">{tr("con.pendingSeats", { n: o.pending_invitations })}</span>}
                </td>
                <td>{o.agencies ?? 0} / {limit(o.max_agencies ?? null)}</td>
                <td><Chip tone={s.tone}>{s.label}</Chip></td>
                <td><div className="onb-acts">
                  <button type="button" className="btn-outline-small" aria-expanded={selected === o.id}
                    onClick={() => setSelected(selected === o.id ? null : o.id)}>{tr("con.manage")}</button>
                  {o.members === 0 && o.active && o.admin_invitation && (
                    <button type="button" className="btn-outline-small" onClick={() => onRenew(o.admin_invitation!)}>{tr("con.newLink")}</button>
                  )}
                  <button type="button" className="btn-outline-small" onClick={() => setConfirming({ organization: o, action: o.active ? "suspend" : "reactivate" })}>
                    {tr(o.active ? "con.suspend" : "con.reactivate")}
                  </button>
                </div></td>
              </tr>;
            })}</tbody>
          </table>
          {filtered.length === 0 && <p className="empty">{tr("con.noMatches")}</p>}
        </div>
      )}
      {confirming && <div className="console-confirm" role="alertdialog" aria-label={tr("con.confirmState")}>
        <strong>{tr("con.confirmState")}: {confirming.organization.name}</strong>
        <p>{tr(confirming.action === "suspend" ? "con.suspendHelp" : "con.confirmReactivate")}</p>
        <div className="onb-acts">
          <button className="btn-primary btn-small-pad" type="button" onClick={() => {
            onState(confirming.organization, confirming.action);
            if (selected === confirming.organization.id) setSelected(null);
            setConfirming(null);
          }}>{tr("con.confirmAction")}</button>
          <button className="btn-outline-small" type="button" onClick={() => setConfirming(null)}>{tr("cancel")}</button>
        </div>
      </div>}
      {selected && <div className="console-detail" aria-live="polite">
        {loading && <p className="muted">{tr("loading")}</p>}
        {loadError && <p className="error" role="alert">{loadError}</p>}
        {detail && detail.id === selected && <CompanyDetail
          key={detail.id}
          detail={detail}
          onUpdated={(updated) => { setDetail(updated); onRefresh(); }}
          onClose={() => setSelected(null)}
        />}
      </div>}
    </section>
  );
}

function CompanyDetail({ detail, onUpdated, onClose }: {
  detail: PlatformCompanyDetail;
  onUpdated: (updated: PlatformCompanyDetail) => void;
  onClose: () => void;
}) {
  const [users, setUsers] = useState(limitInput(detail.max_users));
  const [agencies, setAgencies] = useState(limitInput(detail.max_agencies));
  const [reason, setReason] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  useEffect(() => {
    setUsers(limitInput(detail.max_users));
    setAgencies(limitInput(detail.max_agencies));
  }, [detail.max_users, detail.max_agencies, detail.row_version]);

  async function save(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError("");
    try {
      const updated = await api.updateCompanyCapacities(detail.id, {
        max_users: users.trim() === "" ? null : Number(users),
        max_agencies: agencies.trim() === "" ? null : Number(agencies),
        row_version: detail.row_version, reason: reason.trim(),
      });
      onUpdated(updated);
      setReason("");
    } catch (err) { setError(message(err)); }
    finally { setBusy(false); }
  }

  return <div>
    <div className="console-section-heading">
      <div><h3>{detail.name}</h3><p className="muted small">{countryLabel(detail.country_code)} · {profileLabel(detail.primary_profile)}</p></div>
      <button type="button" className="btn-outline-small" onClick={onClose}>{tr("con.closeDetails")}</button>
    </div>
    <div className="console-detail-grid">
      <section className="console-panel">
        <h4>{tr("con.capacities")}</h4>
        <p className="muted small">{tr("con.usedCapacity", { users: detail.members, pending: detail.pending_invitations, agencies: detail.agencies })}</p>
        <form onSubmit={(e) => void save(e)} className="console-cap-form">
          <label>{tr("con.userLimit")}<input aria-label={tr("con.userLimit")} type="number" min={1} max={100000} value={users}
            placeholder={tr("con.noLimit")} onChange={(e) => setUsers(e.target.value)} /></label>
          <label>{tr("con.agencyLimit")}<input aria-label={tr("con.agencyLimit")} type="number" min={1} max={10000} value={agencies}
            placeholder={tr("con.noLimit")} onChange={(e) => setAgencies(e.target.value)} /></label>
          <label className="console-reason">{tr("con.reason")}<textarea aria-label={tr("con.reason")} minLength={8} maxLength={500} required
            value={reason} onChange={(e) => setReason(e.target.value)} placeholder={tr("con.reasonHint")} /></label>
          {error && <p className="error" role="alert">{error}</p>}
          <button className="btn-primary btn-small-pad" type="submit" disabled={busy || reason.trim().length < 8 ||
            (users === limitInput(detail.max_users) && agencies === limitInput(detail.max_agencies))}>{tr("con.saveCapacities")}</button>
        </form>
      </section>
      <section className="console-panel">
        <h4>{tr("con.companyAdmins")}</h4>
        {detail.administrators.length === 0 ? <p className="muted small">{tr("con.noAdmin")}</p> :
          <ul className="console-admin-list">{detail.administrators.map((a) => <li key={a.email}>
            <strong>{a.full_name || a.email}</strong><span className="muted small">{a.email}</span>
            <div className="console-admin-tags">
              <Chip tone={a.active ? "green" : "gray"}>{tr(a.active ? "active" : "con.suspended")}</Chip>
              <Chip tone={a.mfa_enabled ? "green" : "amber"}>{tr(a.mfa_enabled ? "con.mfaEnabled" : "con.mfaMissing")}</Chip>
            </div>
          </li>)}</ul>}
        <p className="muted small">{tr("con.privacyBoundary")}</p>
      </section>
    </div>
    <section className="console-panel console-history">
      <h4>{tr("con.platformHistory")}</h4>
      {detail.history.length === 0 ? <p className="muted small">{tr("con.noHistory")}</p> :
        <ul>{detail.history.map((e) => <li key={e.id}>
          <strong>{tr(e.event_type === "organization.capacities_changed" ? "con.capacitiesChanged" :
            e.event_type === "organization.created" ? "con.companyCreated" :
            e.event_type === "organization.suspended" ? "con.companySuspended" : "con.companyReactivated")}</strong>
          <span className="muted small">{new Date(e.at).toLocaleString()} · {e.actor || "—"}</span>
          {e.event_type === "organization.capacities_changed" &&
            <span className="small">{tr("con.users")}: {limit(asLimit(e.previous?.max_users))} → {limit(asLimit(e.current?.max_users))} · {tr("adm.agencies")}: {limit(asLimit(e.previous?.max_agencies))} → {limit(asLimit(e.current?.max_agencies))}</span>}
          {typeof e.current?.reason === "string" && <span className="muted small">{e.current.reason}</span>}
        </li>)}</ul>}
    </section>
  </div>;
}
const limitInput = (value: number | null) => value === null ? "" : String(value);
const asLimit = (value: unknown): number | null => typeof value === "number" ? value : null;
