import { useEffect, useState, type FormEvent } from "react";
import {
  api,
  ApiError,
  type Edition,
  type Evidence,
  type ImportRunInfo,
  type NodeDetail,
  type RecordDetail,
  type SearchResult,
} from "./api";
import { Icon } from "./Icon";
import { Chip, fmtDate, PageHeader, StatCard, type Tone } from "./ui";

const QUALITY: Record<string, string> = { known: "lu", unknown: "inconnu (vide)", unparseable: "non numérique" };
const STATES: Record<string, string> = {
  extracted: "extrait de la source",
  derived: "déduit de la hiérarchie",
  review_required: "à vérifier",
  validated: "validé",
};
const PUBLICATION: Record<string, { label: string; tone: Tone }> = {
  operational: { label: "En vigueur", tone: "green" },
  consultation: { label: "Consultation historique", tone: "amber" },
  draft: { label: "Brouillon", tone: "gray" },
  withdrawn: { label: "Retirée", tone: "gray" },
};

/** Recherche tarifaire : code, préfixe ou mots, avec la fiche du code à droite. */
export function TariffSearch() {
  return (
    <>
      <PageHeader
        title="Recherche tarifaire"
        subtitle="Cherchez un code SH par son numéro ou par des mots. Chaque résultat dit pourquoi il est proposé, sans IA."
      />
      <TariffExplorer />
    </>
  );
}

export function TariffExplorer() {
  const [q, setQ] = useState("");
  const [results, setResults] = useState<SearchResult[] | null>(null);
  const [detail, setDetail] = useState<NodeDetail | null>(null);
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
    setDetail(await api.tariffNode(id));
  }

  return (
    <div className="split-panel">
      <section className="card" aria-labelledby="ref-title">
        <h2 id="ref-title" className="card-title">Tarif douanier</h2>
        <form className="searchbar" onSubmit={search} role="search">
          <label>
            <Icon name="search" />
            <input aria-label="Code, préfixe ou mots" value={q} onChange={(e) => setQ(e.target.value)} placeholder="Code, préfixe ou mots : 8528, téléviseurs…" required />
          </label>
          <button type="submit" className="btn-primary">Rechercher</button>
        </form>
        {error && <p role="alert" className="error">⚠ {error}</p>}
        {results === null && <p className="empty">Saisissez un code ou des mots pour interroger le tarif.</p>}
        {results && results.length === 0 && <p className="empty">Aucun résultat dans les éditions publiées.</p>}
        {results && results.length > 0 && (
          <div className="table-wrap">
            <table className="data selectable">
              <thead>
                <tr><th scope="col">Code SH</th><th scope="col">Libellé</th><th scope="col">Pourquoi</th><th scope="col">Édition</th></tr>
              </thead>
              <tbody>
                {results.map((r) => (
                  <tr key={r.id} className={detail?.id === r.id ? "selected" : undefined}>
                    <td>
                      <button type="button" className="link code" onClick={() => void open(r.id)}>{r.code_display}</button>
                    </td>
                    <td>
                      {r.label || <em className="muted">libellé absent de la source</em>}
                      {r.label_damaged && <Chip tone="amber">libellé abîmé</Chip>}
                    </td>
                    <td className="small muted">{r.reason}</td>
                    <td className="small">{r.edition.label}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>
      <section className="card side-panel" aria-label="Détail du code tarifaire">
        <div className="card-head">
          <h2 className="card-title">Détail du code tarifaire</h2>
          {detail && (
            <button type="button" className="icon-button" onClick={() => setDetail(null)} aria-label="Fermer le détail">
              <Icon name="x" />
            </button>
          )}
        </div>
        {detail ? <NodePanel detail={detail} onOpen={(id) => void open(id)} /> : <p className="empty">Choisissez un code dans la liste.</p>}
      </section>
    </div>
  );
}

function NodePanel({ detail, onOpen }: { detail: NodeDetail; onOpen: (id: string) => void }) {
  const [record, setRecord] = useState<RecordDetail | null>(null);
  useEffect(() => setRecord(null), [detail.id]);

  async function openEvidence(evidence: Evidence | null) {
    if (evidence) setRecord(await api.tariffRecord(evidence.record_id));
  }
  const notes = [...detail.notes, ...detail.related_notes];

  return (
    <div>
      <div className="node-head">
        <span className="code big-code" id="node-title">{detail.code_display}</span>
        <Chip tone={PUBLICATION[detail.edition.publication_state]?.tone ?? "gray"}>
          {PUBLICATION[detail.edition.publication_state]?.label ?? detail.edition.publication_state}
        </Chip>
      </div>
      <p className="node-label">{detail.label || <em className="muted">libellé absent de cette source</em>}</p>
      <nav aria-label="Chemin" className="crumbs small">
        {detail.ancestors.map((a) => (
          <span key={a.id}>
            <button type="button" className="link" onClick={() => onOpen(a.id)}>
              {a.code_display}
            </button>
            <Icon name="chevronRight" size={12} />
          </span>
        ))}
        <strong>{detail.code_display}</strong>
      </nav>
      {detail.edition.warning && <p className="note-amber small" role="note">ⓘ {detail.edition.warning}</p>}

      <h3>Informations générales</h3>
      <dl className="kv">
        <dt>Édition</dt>
        <dd>
          {detail.edition.label}
          <span className="block small muted">
            {detail.edition.source.kind_label}
            {detail.edition.source.is_derived_copy && " (copie dérivée, original non fourni)"}
          </span>
        </dd>
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

      <h3>Taxes et taux</h3>
      {detail.rate_observations.items.length === 0 ? (
        <p className="muted small">Aucune valeur relevée dans la source.</p>
      ) : (
        <>
          <p className="muted small">{detail.rate_observations.warning}</p>
          <table className="data compact">
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

      {detail.issues.length > 0 && (
        <>
          <h3>Anomalies</h3>
          <ul className="issue-list">
            {detail.issues.map((i) => (
              <li key={i.id} className={i.severity === "blocking" ? "issue-red" : "issue-amber"}>
                {i.message} {i.state === "resolved" && "(résolue)"}
              </li>
            ))}
          </ul>
        </>
      )}
      {notes.length > 0 && (
        <>
          <h3>Notes</h3>
          {notes.map((n) => (
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
      {detail.children.length > 0 && (
        <>
          <h3>Subdivisions</h3>
          <ul className="plain">
            {detail.children.map((c) => (
              <li key={c.id}>
                <button type="button" className="link" onClick={() => onOpen(c.id)}>
                  <span className="code">{c.code_display}</span> {c.label}
                </button>
              </li>
            ))}
          </ul>
        </>
      )}
      {detail.same_code_in_other_editions.length > 0 && (
        <>
          <h3>Même code dans d'autres éditions</h3>
          <ul className="plain">
            {detail.same_code_in_other_editions.map((o) => (
              <li key={o.id}>
                <button type="button" className="link" onClick={() => onOpen(o.id)}>
                  {o.edition.label}
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
            <div className="table-wrap">
              <table className="data compact">
                <thead>
                  <tr>{(record.header ?? []).map((h) => <th key={h} scope="col">{h}</th>)}</tr>
                </thead>
                <tbody>
                  <tr>{record.raw_cells.map((c, i) => <td key={i}>{c === "" ? "∅" : c}</td>)}</tr>
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

/** Administration tarifaire : éditions publiées, imports (gestionnaire du référentiel), recherche. */
export function ReferenceAdmin({ canSeeImports }: { canSeeImports: boolean }) {
  const [editions, setEditions] = useState<Edition[] | null>(null);
  const [runs, setRuns] = useState<ImportRunInfo[] | null>(null);

  useEffect(() => {
    api.editions().then(setEditions, () => setEditions([]));
    // Les imports ne sont visibles que du gestionnaire du référentiel ; les autres n'en voient rien.
    if (canSeeImports) api.importRuns().then((p) => setRuns(p.results), () => setRuns(null));
  }, [canSeeImports]);

  const visible = (editions ?? []).filter((e) => e.publication_state !== "withdrawn");
  const operational = visible.find((e) => e.publication_state === "operational");
  const latest = [...visible].sort((a, b) => (b.published_at ?? "").localeCompare(a.published_at ?? ""))[0];
  const lines = runs?.find((r) => r.edition_id === (operational ?? latest)?.id)?.counts.tariff_lines;

  return (
    <>
      <PageHeader title="Référentiel tarifaire" subtitle="Les éditions du tarif, leur source et leur état. Un taux n'est utilisé que s'il est vérifié." />
      <div className={`stats ${runs ? "stats-3" : "stats-2"}`}>
        <StatCard
          icon="file"
          tone="green"
          label="Édition en vigueur"
          value={operational ? operational.label : "aucune"}
          hint={operational ? undefined : "les éditions publiées sont en consultation historique"}
        />
        <StatCard icon="clock" tone="blue" label="Dernière publication" value={latest?.published_at ? fmtDate(latest.published_at) : "—"} hint={latest?.label} />
        {runs && <StatCard icon="book" tone="green" label="Lignes tarifaires" value={lines ?? "—"} hint={lines ? (operational ?? latest)?.label : undefined} />}
      </div>

      <section className="card" aria-labelledby="editions-title">
        <h2 id="editions-title" className="card-title">Éditions</h2>
        {editions === null ? (
          <p className="muted">Chargement…</p>
        ) : editions.length === 0 ? (
          <p className="empty">Aucune édition publiée.</p>
        ) : (
          <div className="table-wrap">
            <table className="data">
              <thead>
                <tr><th scope="col">Édition</th><th scope="col">Source</th><th scope="col">Date d'effet</th><th scope="col">Publiée le</th><th scope="col">État</th></tr>
              </thead>
              <tbody>
                {editions.map((e) => (
                  <tr key={e.id}>
                    <td>
                      <strong>{e.label}</strong>
                      {e.warning && <div className="small muted">{e.warning}</div>}
                    </td>
                    <td className="small">
                      {e.source?.title}
                      {e.source?.is_derived_copy && <span className="block muted">copie dérivée</span>}
                    </td>
                    <td>{e.effective_from ? fmtDate(e.effective_from) : <em className="muted">non vérifiée</em>}</td>
                    <td>{e.published_at ? fmtDate(e.published_at) : "—"}</td>
                    <td>
                      <Chip tone={PUBLICATION[e.publication_state]?.tone ?? "gray"}>{PUBLICATION[e.publication_state]?.label ?? e.publication_state}</Chip>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>

      {runs && runs.length > 0 && (
        <section className="card" aria-labelledby="imports-title">
          <h2 id="imports-title" className="card-title">Imports</h2>
          <div className="table-wrap">
            <table className="data">
              <thead>
                <tr><th scope="col">Source</th><th scope="col">Importé le</th><th scope="col">Lignes tarifaires</th><th scope="col">Anomalies ouvertes</th></tr>
              </thead>
              <tbody>
                {runs.map((r) => (
                  <tr key={r.id}>
                    <td>{r.source}</td>
                    <td>{fmtDate(r.started_at)}</td>
                    <td>{r.counts.tariff_lines ?? "—"}</td>
                    <td>{r.open_issues > 0 ? <Chip tone="amber">{r.open_issues}</Chip> : <Chip tone="green">0</Chip>}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      )}

      <TariffExplorer />
    </>
  );
}
