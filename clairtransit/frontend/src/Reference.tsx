import { useState, type FormEvent } from "react";
import { api, ApiError, type Evidence, type NodeDetail, type RecordDetail, type SearchResult } from "./api";

const QUALITY: Record<string, string> = { known: "lu", unknown: "inconnu (vide)", unparseable: "non numérique" };
const STATES: Record<string, string> = {
  extracted: "extrait de la source",
  derived: "déduit de la hiérarchie",
  review_required: "à vérifier",
  validated: "validé",
};

export function Reference() {
  const [q, setQ] = useState("");
  const [results, setResults] = useState<SearchResult[] | null>(null);
  const [detail, setDetail] = useState<NodeDetail | null>(null);
  const [record, setRecord] = useState<RecordDetail | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function search(event: FormEvent) {
    event.preventDefault();
    setError(null);
    try {
      setResults((await api.searchTariffs(q)).results);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Recherche impossible.");
    }
  }

  async function open(id: string) {
    setRecord(null);
    setDetail(await api.tariffNode(id));
  }

  async function openEvidence(evidence: Evidence | null) {
    if (evidence) setRecord(await api.tariffRecord(evidence.record_id));
  }

  return (
    <div className="split">
      <section className="card" aria-labelledby="ref-title">
        <h2 id="ref-title">Référentiel tarifaire</h2>
        <form className="row" onSubmit={search} role="search">
          <label>
            Code, préfixe ou mots
            <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="0101.10, chevaux…" required />
          </label>
          <button type="submit">Rechercher</button>
        </form>
        {error && <p role="alert" className="error">⚠ {error}</p>}
        {results && results.length === 0 && <p>Aucun résultat dans les éditions publiées.</p>}
        {results && results.length > 0 && (
          <ul className="plain results">
            {results.map((r) => (
              <li key={r.id}>
                <button type="button" className="link" onClick={() => void open(r.id)}>
                  <strong className="code">{r.code_display}</strong> {r.label || <em>libellé absent de la source</em>}
                </button>
                <div className="muted small">
                  {r.edition.label} · {r.reason}
                  {r.label_damaged && " · libellé abîmé"}
                </div>
              </li>
            ))}
          </ul>
        )}
      </section>

      {detail && (
        <section className="card" aria-labelledby="node-title">
          <h2 id="node-title">
            <span className="code">{detail.code_display}</span>{" "}
            {detail.label || <em className="muted">libellé absent de cette source</em>}
          </h2>
          {detail.edition.warning && <p className="warning" role="note">ⓘ {detail.edition.warning}</p>}
          <p className="muted small">
            {detail.edition.label} — {detail.edition.source.kind_label}
            {detail.edition.source.is_derived_copy && " (copie dérivée, original non fourni)"}
          </p>
          <nav aria-label="Chemin" className="small">
            {detail.ancestors.map((a) => (
              <span key={a.id}>
                <button type="button" className="link" onClick={() => void open(a.id)}>
                  {a.code_display}
                  {a.label && ` ${a.label}`}
                </button>{" › "}
              </span>
            ))}
            <strong>{detail.code_display}</strong>
          </nav>
          <dl className="facts">
            <dt>Déclarable selon la source</dt>
            <dd>{detail.declarable ? "oui" : "non"}</dd>
            <dt>État</dt>
            <dd>{STATES[detail.validation_state] ?? detail.validation_state}</dd>
            <dt>Preuve</dt>
            <dd>
              {detail.evidence ? (
                <button type="button" className="link" onClick={() => void openEvidence(detail.evidence)}>
                  Ouvrir {detail.evidence.location}
                </button>
              ) : (
                "déduit de la hiérarchie"
              )}
            </dd>
          </dl>
          {detail.issues.length > 0 && (
            <>
              <h3>Anomalies</h3>
              <ul>
                {detail.issues.map((i) => (
                  <li key={i.id}>
                    [{i.severity === "blocking" ? "Bloquante" : i.severity === "review" ? "À vérifier" : "Info"}]{" "}
                    {i.message} {i.state === "resolved" && "(résolue)"}
                  </li>
                ))}
              </ul>
            </>
          )}
          {detail.rate_observations.items.length > 0 && (
            <>
              <h3>Valeurs observées dans la source</h3>
              <p className="muted small">{detail.rate_observations.warning}</p>
              <table>
                <thead>
                  <tr><th scope="col">Colonne</th><th scope="col">Valeur brute</th><th scope="col">Lecture</th></tr>
                </thead>
                <tbody>
                  {detail.rate_observations.items.map((r) => (
                    <tr key={r.column}>
                      <td>{r.column}</td>
                      <td>{r.raw_value || "—"}</td>
                      <td>{QUALITY[r.quality] ?? r.quality}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </>
          )}
          {[...detail.notes, ...detail.related_notes].length > 0 && (
            <>
              <h3>Notes</h3>
              {[...detail.notes, ...detail.related_notes].map((n) => (
                <details key={n.id}>
                  <summary>
                    Note {n.scope_type === "chapter" ? "du chapitre" : "de la section"} {n.scope_ref} — {n.edition.label}
                  </summary>
                  <pre className="note">{n.text}</pre>
                  <button type="button" className="link" onClick={() => void openEvidence(n.evidence)}>
                    Ouvrir {n.evidence?.location}
                  </button>
                </details>
              ))}
            </>
          )}
          {detail.same_code_in_other_editions.length > 0 && (
            <>
              <h3>Même code dans d'autres éditions</h3>
              <ul>
                {detail.same_code_in_other_editions.map((o) => (
                  <li key={o.id}>
                    <button type="button" className="link" onClick={() => void open(o.id)}>
                      {o.edition.label}
                    </button>
                  </li>
                ))}
              </ul>
            </>
          )}
          {detail.children.length > 0 && (
            <>
              <h3>Subdivisions</h3>
              <ul className="plain">
                {detail.children.map((c) => (
                  <li key={c.id}>
                    <button type="button" className="link" onClick={() => void open(c.id)}>
                      <span className="code">{c.code_display}</span> {c.label}
                    </button>
                  </li>
                ))}
              </ul>
            </>
          )}
          {record && (
            <div className="evidence" role="region" aria-label="Preuve">
              <h3>Preuve : {record.location}</h3>
              <p className="muted small">
                {record.source.title}
                {record.source.is_derived_copy && " (copie dérivée)"} · empreinte {record.source.sha256.slice(0, 12)}…
              </p>
              {record.raw_text ? (
                <pre className="note">{record.raw_text}</pre>
              ) : (
                <table>
                  <thead>
                    <tr>{(record.header ?? []).map((h) => <th key={h} scope="col">{h}</th>)}</tr>
                  </thead>
                  <tbody>
                    <tr>{record.raw_cells.map((c, i) => <td key={i}>{c === "" ? "∅" : c}</td>)}</tr>
                  </tbody>
                </table>
              )}
            </div>
          )}
        </section>
      )}
    </div>
  );
}
