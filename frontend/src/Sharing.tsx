import { useCallback, useEffect, useState, type FormEvent } from "react";
import { api, ApiError, type CaseShare, type Membership, type ShareDetail } from "./api";
import { Icon } from "./Icon";
import { tr, type MessageKey } from "./i18n";
import { profileLabel } from "./Onboarding";
import { navigate } from "./router";
import { Chip, fmtDateTime, PageHeader } from "./ui";

const message = (error: unknown) => error instanceof ApiError ? error.message : tr("saveError");
const STATUS: Record<CaseShare["status"], ["green" | "amber" | "gray" | "red", MessageKey]> = {
  pending: ["amber", "share.status.pending"],
  accepted: ["green", "share.status.accepted"],
  refused: ["red", "share.status.refused"],
  revoked: ["gray", "share.status.revoked"],
};
const levelLabel = (level: CaseShare["level"]) => tr(level === "comment" ? "share.level.comment" : "share.level.read");
const has = (m: Membership, ...roles: string[]) => m.roles.some((r) => roles.includes(r));

function StatusChip({ share }: { share: CaseShare }) {
  const [tone, label] = STATUS[share.status];
  return <Chip tone={tone}>{tr(label)}</Chip>;
}

/** COL-02, COL-04 : partager le dossier avec une société par son code, suivre et retirer les partages. */
export function CaseSharing({ caseId, membership }: { caseId: string; membership: Membership }) {
  const [shares, setShares] = useState<CaseShare[] | null>(null);
  const [code, setCode] = useState("");
  const [level, setLevel] = useState<CaseShare["level"]>("comment");
  const [note, setNote] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const canShare = has(membership, "declarant", "validator", "org_admin");
  const load = useCallback(() => api.caseShares(caseId).then((r) => setShares(r.results), (e: unknown) => setError(message(e))), [caseId]);
  useEffect(() => { void load(); }, [load]);

  const run = async (call: () => Promise<unknown>) => {
    setBusy(true);
    setError("");
    try { await call(); await load(); } catch (e) { setError(message(e)); } finally { setBusy(false); }
  };
  const submit = (event: FormEvent) => {
    event.preventDefault();
    void run(async () => { await api.createShare(caseId, { code: code.trim(), level, message: note.trim() }); setCode(""); setNote(""); });
  };
  const live = (shares ?? []).filter((s) => s.status === "pending" || s.status === "accepted");

  return (
    <section aria-labelledby="share-title">
      <h3 id="share-title" className="extracted-sub"><Icon name="users" size={16} /> {tr("share.title")}</h3>
      <p className="muted small">{tr("share.help")}</p>
      {live.length > 0 && <ul className="small">{live.map((s) => (
        <li key={s.id}>
          <strong>{s.organization.name}</strong> · {levelLabel(s.level)} <StatusChip share={s} />
          {canShare && <button type="button" className="btn-outline-small" disabled={busy}
            onClick={() => void run(() => api.revokeShare(s.id, ""))}>{tr("share.revoke")}</button>}
          {s.status === "accepted" && <button type="button" className="link" onClick={() => navigate(`/partages/${s.id}`)}>{tr("share.notes")}</button>}
        </li>
      ))}</ul>}
      {canShare && <form onSubmit={submit} className="console-cap-form" aria-label={tr("share.title")}>
        <label>{tr("share.code")}<input aria-label={tr("share.code")} required maxLength={40} value={code}
          placeholder="CT-XXXX-XXXX" onChange={(e) => setCode(e.target.value)} /></label>
        <label>{tr("share.level")}<select aria-label={tr("share.level")} value={level} onChange={(e) => setLevel(e.target.value as CaseShare["level"])}>
          <option value="comment">{tr("share.level.comment")}</option>
          <option value="read">{tr("share.level.read")}</option>
        </select></label>
        <label className="console-reason">{tr("share.message")}<input aria-label={tr("share.message")} maxLength={500} value={note}
          onChange={(e) => setNote(e.target.value)} /></label>
        <button type="submit" className="btn-secondary btn-block" disabled={busy || !code.trim()}>{tr("share.send")}</button>
      </form>}
      {error && <p role="alert" className="error">⚠ {error}</p>}
    </section>
  );
}

/** COL-01, COL-03 : dossiers partagés avec la société active, et le code à donner aux partenaires. */
export function SharedCases({ membership, shareId }: { membership: Membership; shareId?: string }) {
  if (shareId) return <SharedCaseView key={shareId} shareId={shareId} />;
  return <SharedList membership={membership} />;
}

function SharedList({ membership }: { membership: Membership }) {
  const [items, setItems] = useState<CaseShare[] | null>(null);
  const [code, setCode] = useState("");
  const [error, setError] = useState("");
  const canDecide = has(membership, "validator", "org_admin");
  const isAdmin = has(membership, "org_admin");
  const load = useCallback(() => api.incomingShares().then((r) => setItems(r.results), (e: unknown) => setError(message(e))), []);
  useEffect(() => {
    void load();
    void api.partnerCode().then((r) => setCode(r.code), () => undefined);
  }, [load]);
  const act = (call: () => Promise<unknown>) => void call().then(load, (e: unknown) => setError(message(e)));

  return (
    <div>
      <PageHeader title={tr("share.pageTitle")} subtitle={tr("share.pageSubtitle")} />
      <section className="card" aria-labelledby="partner-code">
        <h2 id="partner-code" className="card-title">{tr("share.ourCode")}</h2>
        <p><strong>{code || "…"}</strong></p>
        <p className="muted small">{tr("share.ourCodeHelp")}</p>
        {isAdmin && <button type="button" className="btn-outline-small"
          onClick={() => act(async () => setCode((await api.renewPartnerCode()).code))}>{tr("share.renewCode")}</button>}
      </section>
      <section className="card" aria-labelledby="incoming-title">
        <h2 id="incoming-title" className="card-title">{tr("share.incoming")}</h2>
        {error && <p role="alert" className="error">⚠ {error}</p>}
        {items === null ? <p className="muted">{tr("loading")}</p> : items.length === 0 ? <p className="muted small">{tr("share.none")}</p> :
          <table className="data">
            <tbody>{items.map((s) => (
              <tr key={s.id}>
                <td><strong>{s.case_reference}</strong>{s.case_title && <div className="muted small">{s.case_title}</div>}</td>
                <td>{s.organization.name}<div className="muted small">{s.organization.profiles.map(profileLabel).join(", ")}</div></td>
                <td>{levelLabel(s.level)}{s.message && <div className="muted small">« {s.message} »</div>}</td>
                <td><StatusChip share={s} /><div className="muted small">{fmtDateTime(s.created_at)}</div></td>
                <td>
                  {s.status === "pending" && canDecide && <>
                    <button type="button" className="btn-outline-small" onClick={() => act(() => api.decideShare(s.id, "accept"))}>{tr("share.accept")}</button>{" "}
                    <button type="button" className="btn-outline-small" onClick={() => act(() => api.decideShare(s.id, "refuse"))}>{tr("share.refuse")}</button>
                  </>}
                  {s.status === "accepted" && <button type="button" className="btn-outline-small" onClick={() => navigate(`/partages/${s.id}`)}>{tr("share.open")}</button>}
                </td>
              </tr>
            ))}</tbody>
          </table>}
      </section>
    </div>
  );
}

function SharedCaseView({ shareId }: { shareId: string }) {
  const [detail, setDetail] = useState<ShareDetail | null>(null);
  const [text, setText] = useState("");
  const [error, setError] = useState("");
  useEffect(() => { void api.shareDetail(shareId).then(setDetail, (e: unknown) => setError(message(e))); }, [shareId]);
  const send = (event: FormEvent) => {
    event.preventDefault();
    void api.addShareNote(shareId, text.trim()).then((r) => { setDetail((d) => d && { ...d, notes: r.notes }); setText(""); },
      (e: unknown) => setError(message(e)));
  };
  if (!detail) return error ? <p role="alert" className="error">⚠ {error}</p> : <p className="muted">{tr("loading")}</p>;
  const { share, case: c, notes } = detail;
  return (
    <div>
      <PageHeader title={share.case_reference} subtitle={tr("share.sharedBy", { name: share.organization.name })} />
      <p className="muted small">{tr("share.readOnlyNote")}</p>
      {c && <div className="grid-2-1">
        <div>
          <section className="card" aria-labelledby="sh-goods">
            <h2 id="sh-goods" className="card-title">{tr("share.goods")}</h2>
            {c.goods.length === 0 ? <p className="muted small">—</p> : <table className="data"><tbody>{c.goods.map((g) => (
              <tr key={g.ordinal}><td>{g.ordinal}</td><td>{g.description}</td><td>{g.origin_country || "—"}</td><td><strong>{g.code ?? "—"}</strong></td></tr>
            ))}</tbody></table>}
          </section>
          <section className="card" aria-labelledby="sh-inv">
            <h2 id="sh-inv" className="card-title">{tr("share.invoices")}</h2>
            {c.invoices.length === 0 ? <p className="muted small">—</p> : <table className="data"><tbody>{c.invoices.map((i, n) => (
              <tr key={n}><td>{i.number || "—"}</td><td>{i.supplier || "—"}</td><td>{i.incoterm}</td><td>{i.total ?? "—"} {i.currency}</td></tr>
            ))}</tbody></table>}
          </section>
        </div>
        <div>
          <section className="card" aria-labelledby="sh-state">
            <h2 id="sh-state" className="card-title">{c.state_label}</h2>
            <dl className="recap">
              <div><dt>{tr("share.owner")}</dt><dd>{c.owner}</dd></div>
              <div><dt>{tr("importers")}</dt><dd>{c.importer ?? "—"}</dd></div>
              <div><dt>{tr("share.revision")}</dt><dd>{c.revision_no}</dd></div>
              {c.customs_declaration_number && <div><dt>{tr("life.number")}</dt><dd>{c.customs_declaration_number}</dd></div>}
            </dl>
          </section>
          <section className="card" aria-labelledby="sh-docs">
            <h2 id="sh-docs" className="card-title">{tr("share.documents")}</h2>
            {c.documents.length === 0 ? <p className="muted small">—</p> :
              <ul className="small">{c.documents.map((d, n) => <li key={n}><strong>{d.usage_label}</strong> · {d.name}</li>)}</ul>}
          </section>
        </div>
      </div>}
      <section className="card" aria-labelledby="sh-notes">
        <h2 id="sh-notes" className="card-title">{tr("share.notes")}</h2>
        {notes.length === 0 ? <p className="muted small">{tr("share.noNotes")}</p> :
          <ul className="small">{notes.map((n) => (
            <li key={n.id}><strong>{n.organization}</strong> · {n.author} · <span className="muted">{fmtDateTime(n.created_at)}</span><div>{n.text}</div></li>
          ))}</ul>}
        {share.status === "accepted" && share.level === "comment" && <form onSubmit={send} className="console-cap-form">
          <label className="console-reason">{tr("share.addNote")}<textarea aria-label={tr("share.addNote")} maxLength={2000}
            value={text} onChange={(e) => setText(e.target.value)} /></label>
          <button type="submit" className="btn-secondary" disabled={!text.trim()}>{tr("share.sendNote")}</button>
        </form>}
        {error && <p role="alert" className="error">⚠ {error}</p>}
      </section>
    </div>
  );
}
