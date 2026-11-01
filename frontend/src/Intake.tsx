// Écran « Dépôt groupé » : les pièces de plusieurs envois sont déposées ensemble, ClairTransit propose
// un dossier par envoi d'après les références qu'elles partagent ; rien n'est créé avant la confirmation.
import { useEffect, useState } from "react";
import { api, type IntakePiece } from "./api";
import { Icon } from "./Icon";
import { tr } from "./i18n";
import { typeLabel } from "./pieceTypes";
import { Chip, PageHeader, errorText } from "./ui";

interface Deposit {
  key: string;
  name: string;
  status: "sending" | "ok" | "failed";
  piece?: IntakePiece;
  error?: string;
}

type Reason = { kind: "invoice" | "bl" | "container"; value: string; documents: number };
type Group = { id: string; title: string; parties: string[]; reasons: Reason[] };

const SORT = "sort";

export function IntakePage() {
  const [deposits, setDeposits] = useState<Deposit[]>([]);
  const [drag, setDrag] = useState(false);
  const [groups, setGroups] = useState<Group[] | null>(null);
  const [placement, setPlacement] = useState<Record<string, string>>({});
  const [types, setTypes] = useState<Record<string, { code: string; label_fr: string; label_en: string }>>({});
  const [created, setCreated] = useState<{ id: string; reference: string; title: string; documents: number }[] | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    api.documentTypes().then((r) => setTypes(Object.fromEntries(r.results.map((t) => [t.code, t]))), () => undefined);
  }, []);

  const pieces = Object.fromEntries(deposits.filter((d) => d.piece).map((d) => [d.piece!.document_id, d.piece!]));
  const pending = deposits.some((d) => d.status === "sending");
  const typeName = (code: string) => (code ? typeLabel(types[code] ?? { code }) : tr("intake.notRead"));

  async function addFiles(list: FileList | null) {
    if (!list) return;
    const added = [...list].map((file, i) => ({ file, key: `${Date.now()}-${i}-${file.name}` }));
    setGroups(null);
    setDeposits((cur) => [...cur, ...added.map(({ key, file }) => ({ key, name: file.name, status: "sending" as const }))]);
    for (const { key, file } of added) {
      try {
        const piece = await api.intakeUpload(file);
        setDeposits((cur) => cur.map((d) => (d.key === key ? { ...d, status: "ok", piece } : d)));
      } catch (err) {
        setDeposits((cur) => cur.map((d) => (d.key === key ? { ...d, status: "failed", error: errorText(err, tr("intake.failed")) } : d)));
      }
    }
  }

  async function propose() {
    setBusy(true);
    setError("");
    try {
      const ids = [...new Set(Object.keys(pieces))];
      const r = await api.intakeProposal(ids);
      const next = r.groups.map((g, i) => ({ id: `g${i}`, title: g.title, parties: g.parties, reasons: g.reasons }));
      const place: Record<string, string> = {};
      r.groups.forEach((g, i) => g.documents.forEach((d) => (place[d.document_id] = `g${i}`)));
      r.unassigned.forEach((d) => (place[d.document_id] = SORT));
      setGroups(next);
      setPlacement(place);
    } catch (err) {
      setError(errorText(err, tr("saveError")));
    } finally {
      setBusy(false);
    }
  }

  function move(docId: string, target: string) {
    if (target === "new" && groups) {
      const id = `g${Date.now()}`;
      setGroups([...groups, { id, title: pieces[docId]?.party || pieces[docId]?.name || tr("intake.newGroup"), parties: [], reasons: [] }]);
      setPlacement({ ...placement, [docId]: id });
      return;
    }
    setPlacement({ ...placement, [docId]: target });
  }

  const filled = (groups ?? []).filter((g) => Object.values(placement).includes(g.id));

  async function create() {
    setBusy(true);
    setError("");
    try {
      const body = filled.map((g) => ({
        title: g.title,
        document_ids: Object.entries(placement).filter(([, gid]) => gid === g.id).map(([doc]) => doc),
      }));
      setCreated((await api.intakeCreate(body)).results);
    } catch (err) {
      setError(errorText(err, tr("saveError")));
    } finally {
      setBusy(false);
    }
  }

  function restart() {
    setDeposits([]);
    setGroups(null);
    setPlacement({});
    setCreated(null);
  }

  if (created) {
    return (
      <div>
        <PageHeader title={tr("intake.title")} subtitle={tr("intake.subtitle")} />
        <section className="card" aria-labelledby="intake-created">
          <h2 id="intake-created" className="card-title">{tr("intake.createdTitle")}</h2>
          <p className="muted small">{tr("intake.createdHelp")}</p>
          <table className="data">
            <tbody>
              {created.map((c) => (
                <tr key={c.id}>
                  <td><strong>{c.reference}</strong></td>
                  <td>{c.title}</td>
                  <td>{tr("intake.piecesCount", { n: c.documents })}</td>
                  <td className="num"><a className="btn-secondary" href={`#/dossiers/${c.id}/documents`}>{tr("intake.open")} <Icon name="arrowRight" size={14} /></a></td>
                </tr>
              ))}
            </tbody>
          </table>
          <button type="button" className="btn-secondary" onClick={restart}><Icon name="plus" size={16} /> {tr("intake.again")}</button>
        </section>
      </div>
    );
  }

  const pieceRow = (docId: string, options: { id: string; title: string }[]) => {
    const p = pieces[docId];
    if (!p) return null;
    return (
      <tr key={docId}>
        <td>
          <strong>{p.name}</strong>
          <div className="muted small">{typeName(p.type)}{p.party ? ` · ${tr("intake.party", { party: p.party })}` : ""}</div>
        </td>
        <td>
          <select aria-label={tr("intake.moveTo")} value={placement[docId]} onChange={(e) => move(docId, e.target.value)}>
            {options.map((o) => (
              <option key={o.id} value={o.id}>{o.title}</option>
            ))}
            <option value={SORT}>{tr("intake.toSort")}</option>
            <option value="new">{tr("intake.newGroup")}…</option>
          </select>
        </td>
      </tr>
    );
  };

  return (
    <div>
      <PageHeader title={tr("intake.title")} subtitle={tr("intake.subtitle")} />
      <div className="grid-1-1">
        <section className="card" aria-labelledby="intake-files">
          <h2 id="intake-files" className="card-title">{tr("intake.filesTitle")}</h2>
          <label
            className={`nc-drop${drag ? " over" : ""}`}
            onDragOver={(e) => { e.preventDefault(); setDrag(true); }}
            onDragLeave={() => setDrag(false)}
            onDrop={(e) => { e.preventDefault(); setDrag(false); void addFiles(e.dataTransfer.files); }}
          >
            <Icon name="cloudUpload" size={40} />
            <strong>{tr("nc.drop")}</strong>
            <span>{tr("nc.browse")}</span>
            <small>{tr("nc.formats")}</small>
            <input type="file" multiple accept=".pdf,.png,.jpg,.jpeg,.xlsx" aria-label={tr("intake.filesTitle")} onChange={(e) => { void addFiles(e.target.files); e.target.value = ""; }} />
          </label>
          {deposits.length > 0 && (
            <table className="data">
              <tbody>
                {deposits.map((d) => (
                  <tr key={d.key}>
                    <td>
                      <strong>{d.name}</strong>
                      <div className="muted small">
                        {d.piece ? typeName(d.piece.type) : d.error ?? ""}
                        {d.piece?.already_in?.length ? ` · ${tr("intake.already", { refs: d.piece.already_in.join(", ") })}` : ""}
                      </div>
                    </td>
                    <td className="num">
                      {d.status === "sending" ? (
                        <Chip tone="gray" icon="clock">{tr("intake.sending")}</Chip>
                      ) : d.status === "failed" ? (
                        <Chip tone="red" icon="alert">{tr("intake.failed")}</Chip>
                      ) : d.piece?.read ? (
                        <Chip tone="green" icon="checkCircle">{tr("intake.read")}</Chip>
                      ) : (
                        <Chip tone="amber" icon="info">{tr("intake.notRead")}</Chip>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
          <button type="button" className="btn-primary btn-block" disabled={busy || pending || Object.keys(pieces).length === 0} onClick={() => void propose()}>
            <Icon name="layers" size={16} /> {tr("intake.propose")}
          </button>
          {error && <p className="note-amber small" role="alert">{error}</p>}
        </section>

        <section className="card" aria-labelledby="intake-proposal">
          <h2 id="intake-proposal" className="card-title">{tr("intake.proposalTitle")}</h2>
          <p className="muted small">{tr("intake.proposalHelp")}</p>
          {groups === null ? (
            <p className="empty">—</p>
          ) : (
            <>
              {groups.map((g) => {
                const docs = Object.keys(placement).filter((id) => placement[id] === g.id);
                if (docs.length === 0) return null;
                return (
                  <div key={g.id} className="intake-group">
                    <label className="nc-field">
                      <span className="nc-label">{tr("intake.caseTitle")}</span>
                      <input value={g.title} onChange={(e) => setGroups(groups.map((x) => (x.id === g.id ? { ...x, title: e.target.value } : x)))} />
                    </label>
                    <div className="actions-row">
                      {g.reasons.map((r) => (
                        <Chip key={`${r.kind}-${r.value}`} tone="blue" icon="check">
                          {tr(`intake.kind.${r.kind}`, { value: r.value })} · {tr("intake.shared", { n: r.documents })}
                        </Chip>
                      ))}
                    </div>
                    {g.parties.length > 1 && <p className="note-amber small">{tr("intake.namesDiffer", { names: g.parties.join(" ; ") })}</p>}
                    <table className="data">
                      <tbody>{docs.map((id) => pieceRow(id, groups.map((x) => ({ id: x.id, title: x.title }))))}</tbody>
                    </table>
                  </div>
                );
              })}
              {Object.values(placement).includes(SORT) && (
                <div className="intake-group">
                  <h3>{tr("intake.toSort")}</h3>
                  <p className="muted small">{tr("intake.toSortHelp")}</p>
                  <table className="data">
                    <tbody>
                      {Object.keys(placement).filter((id) => placement[id] === SORT).map((id) => pieceRow(id, groups.map((x) => ({ id: x.id, title: x.title }))))}
                    </tbody>
                  </table>
                </div>
              )}
              <p className="note-blue small">{tr("intake.note")}</p>
              <button type="button" className="btn-primary btn-block" disabled={busy || filled.length === 0} onClick={() => void create()}>
                <Icon name="folder" size={16} /> {tr("intake.create", { n: filled.length })}
              </button>
            </>
          )}
        </section>
      </div>
    </div>
  );
}
