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
export function TariffSearch({ initialQuery = "" }: { initialQuery?: string }) {
  return (
    <>
      <nav className="breadcrumb" aria-label="Fil d'Ariane">
        <span>Marchandises</span>
        <Icon name="chevronRight" size={14} />
        <span>Recherche tarifaire</span>
      </nav>
      <PageHeader
        title="Recherche tarifaire"
        subtitle={
          <>
            <strong className="subtitle-strong">Retrouvez le bon code SH dans le tarif.</strong>
            <span className="block">
              Cherchez par numéro, préfixe ou mots. Chaque résultat dit pourquoi il est proposé (sans IA) ; un code ne devient un
              classement qu'une fois confirmé par un agent dans le dossier.
            </span>
          </>
        }
      />
      <TariffExplorer initialQuery={initialQuery} />
    </>
  );
}

const chapterOf = (code: string | null) => (code ? code.replace(/\D/g, "").slice(0, 2) : "");

export function TariffExplorer({ initialQuery = "" }: { initialQuery?: string }) {
  const [q, setQ] = useState(initialQuery);
  const [results, setResults] = useState<SearchResult[] | null>(null);
  const [detail, setDetail] = useState<NodeDetail | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [chapter, setChapter] = useState("");
  const [declarableOnly, setDeclarableOnly] = useState(false);

  async function run(text: string) {
    setError(null);
    try {
      const found = (await api.searchTariffs(text)).results;
      setResults(found);
      setChapter("");
      const first = found.find((r) => r.declarable) ?? found[0];
      if (first) void open(first.id);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Recherche impossible.");
    }
  }

  useEffect(() => {
    if (initialQuery) void run(initialQuery);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [initialQuery]);

  async function search(event: FormEvent) {
    event.preventDefault();
    await run(q);
  }

  const chapters = [...new Set((results ?? []).map((r) => chapterOf(r.code)).filter(Boolean))].sort();
  const shown = (results ?? []).filter((r) => (!chapter || chapterOf(r.code) === chapter) && (!declarableOnly || r.declarable));

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
        {results && results.length > 0 && (
          <div className="table-tools spaced">
            <label className="filter-mini">
              <Icon name="filter" size={16} />
              <select aria-label="Chapitre" value={chapter} onChange={(e) => setChapter(e.target.value)}>
                <option value="">Tous les chapitres</option>
                {chapters.map((c) => (
                  <option key={c} value={c}>Chapitre {c}</option>
                ))}
              </select>
            </label>
            <label className="check-inline">
              <input type="checkbox" checked={declarableOnly} onChange={(e) => setDeclarableOnly(e.target.checked)} /> Codes déclarables seulement
            </label>
            <span className="muted small">{shown.length} résultat(s)</span>
          </div>
        )}
        {error && <p role="alert" className="error">⚠ {error}</p>}
        {results === null && <p className="empty">Saisissez un code ou des mots pour interroger le tarif.</p>}
        {results && results.length === 0 && <p className="empty">Aucun résultat dans les éditions publiées.</p>}
        {results && results.length > 0 && (
          <div className="table-wrap">
            <table className="data selectable">
              <thead>
                <tr>
                  <th scope="col">Code SH</th><th scope="col">Libellé</th><th scope="col">Chapitre</th><th scope="col">Pourquoi</th>
                  <th scope="col">État</th>
                </tr>
              </thead>
              <tbody>
                {shown.map((r) => (
                  <tr key={r.id} className={detail?.id === r.id ? "selected" : undefined} onClick={() => void open(r.id)}>
                    <td>
                      <button type="button" className="link code" onClick={() => void open(r.id)}>{r.code_display}</button>
                    </td>
                    <td>
                      {r.label || <em className="muted">libellé absent de la source</em>}
                      {r.label_damaged && <Chip tone="amber">libellé abîmé</Chip>}
                    </td>
                    <td className="small">{chapterOf(r.code) || "—"}</td>
                    <td className="small muted">{r.reason}</td>
                    <td>
                      {r.declarable ? <Chip tone="blue">déclarable</Chip> : <Chip tone="gray">regroupement</Chip>}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
        {results && results.length > 0 && (
          <p className="muted small">Édition interrogée : {[...new Set(results.map((r) => r.edition.label))].join(", ")}.</p>
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

      <h3>Version et validité</h3>
      <dl className="kv">
        <dt>Version</dt>
        <dd>
          {detail.edition.label}{" "}
          <Chip tone={PUBLICATION[detail.edition.publication_state]?.tone ?? "gray"}>
            {detail.edition.publication_state === "operational" ? "Actuelle" : "Historique"}
          </Chip>
        </dd>
        <dt>Date d'effet</dt>
        <dd>{detail.edition.publication_state === "operational" ? "voir l'édition" : <em className="muted">non vérifiée</em>}</dd>
        <dt>Date de fin</dt>
        <dd>—</dd>
      </dl>
      <h3>Historique des versions</h3>
      <table className="data compact">
        <thead>
          <tr><th scope="col">Édition</th><th scope="col">État</th></tr>
        </thead>
        <tbody>
          <tr>
            <td>{detail.edition.label}</td>
            <td><Chip tone={PUBLICATION[detail.edition.publication_state]?.tone ?? "gray"}>{PUBLICATION[detail.edition.publication_state]?.label}</Chip></td>
          </tr>
          {detail.same_code_in_other_editions.map((o) => (
            <tr key={o.id}>
              <td>
                <button type="button" className="link" onClick={() => onOpen(o.id)}>{o.edition.label}</button>
              </td>
              <td><Chip tone={PUBLICATION[o.edition.publication_state]?.tone ?? "gray"}>{PUBLICATION[o.edition.publication_state]?.label}</Chip></td>
            </tr>
          ))}
        </tbody>
      </table>
      {detail.same_code_in_other_editions.length === 0 && <p className="muted small">Ce code n'existe que dans cette édition.</p>}

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
  const [tab, setTab] = useState<"tarif" | "taxes" | "versions" | "import">("tarif");

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
      <nav className="breadcrumb" aria-label="Fil d'Ariane">
        <span>Référentiel</span>
        <Icon name="chevronRight" size={14} />
        <span>Administration tarifaire</span>
      </nav>
      <PageHeader
        title="Administration tarifaire"
        subtitle="Le tarif douanier et les règles fiscales applicables. Un taux n'est utilisé que s'il est daté, sourcé et vérifié."
      />
      <div role="tablist" className="tabs" aria-label="Sections du référentiel">
        {(
          [
            ["tarif", "Tarif douanier", "file"],
            ["taxes", "Taxes et règles", "layers"],
            ["versions", "Versions", "history"],
            ["import", "Import Excel", "upload"],
          ] as const
        ).map(([key, label, icon]) => (
          <button key={key} type="button" role="tab" aria-selected={tab === key} onClick={() => setTab(key)}>
            <Icon name={icon} size={18} /> {label}
          </button>
        ))}
      </div>
      <div className="stats stats-3">
        <StatCard
          icon="file"
          tone="green"
          label="Version active"
          value={operational ? operational.label : "aucune"}
          hint={operational ? "en vigueur" : "les éditions publiées sont en consultation historique"}
        />
        <StatCard icon="clock" tone="blue" label="Dernière mise à jour" value={latest?.published_at ? fmtDate(latest.published_at) : "—"} hint={latest?.label} />
        <StatCard
          icon="book"
          tone="green"
          label="Lignes tarifaires"
          value={lines ?? "—"}
          hint={lines ? (operational ?? latest)?.label : canSeeImports ? "aucun import" : "visible du gestionnaire du référentiel"}
        />
      </div>

      {tab === "tarif" && (
        <>
          <div className="action-bar">
            <button type="button" className="btn-primary" disabled={!canSeeImports} onClick={() => setTab("import")}>
              <Icon name="plus" /> Importer un nouveau tarif
            </button>
            <button type="button" className="btn-secondary" disabled title="La comparaison de versions arrive avec la deuxième édition vérifiée.">
              <Icon name="refresh" /> Comparer les versions
            </button>
            <button type="button" className="btn-secondary" disabled title="L'export du tarif arrive dans une prochaine version.">
              <Icon name="upload" /> Exporter
            </button>
          </div>
          <TariffExplorer />
        </>
      )}

      {tab === "taxes" && (
        <section className="card" aria-labelledby="taxes-title">
          <h2 id="taxes-title" className="card-title">Taxes et règles</h2>
          <p className="note-amber small">
            Aucune règle fiscale n'est encore saisie : aucun taux n'est appliqué à un dossier. Les colonnes de taux du classeur 2016 restent
            des observations brutes, visibles dans la fiche de chaque code.
          </p>
          <div className="table-wrap">
            <table className="data">
              <thead>
                <tr><th scope="col">Code</th><th scope="col">Taxe</th><th scope="col">Assiette</th><th scope="col">Taux</th><th scope="col">Source</th><th scope="col">État</th></tr>
              </thead>
              <tbody>
                {TAX_RULES.map(([code, label, base]) => (
                  <tr key={code}>
                    <td><strong>{code}</strong></td>
                    <td>{label}</td>
                    <td className="small">{base}</td>
                    <td><em className="muted">non saisi</em></td>
                    <td><em className="muted">à fournir</em></td>
                    <td><Chip tone="gray">À définir</Chip></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      )}

      {tab === "versions" && (
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
      )}

      {tab === "import" && (
        <section className="card" aria-labelledby="imports-title">
          <h2 id="imports-title" className="card-title">Import Excel</h2>
          <p className="muted small">
            Un import crée une nouvelle édition en brouillon : chaque ligne garde sa cellule source, et rien n'est publié sans vérification.
            L'import se lance aujourd'hui par le gestionnaire du référentiel (commande <code>import_tariff_xlsx</code>) ; le dépôt depuis cet écran arrive ensuite.
          </p>
          {!canSeeImports ? (
            <p className="empty">Les imports sont visibles du gestionnaire du référentiel.</p>
          ) : !runs || runs.length === 0 ? (
            <p className="empty">Aucun import.</p>
          ) : (
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
          )}
        </section>
      )}
    </>
  );
}

const TAX_RULES: [string, string, string][] = [
  ["DD", "Droit de douane (TEC CEMAC)", "valeur en douane (CIF)"],
  ["TCI", "Taxe communautaire d'intégration", "valeur en douane"],
  ["CCI", "Contribution communautaire d'intégration", "valeur en douane"],
  ["RS", "Redevance statistique", "valeur en douane"],
  ["TVA", "Taxe sur la valeur ajoutée", "valeur en douane + droits"],
];
