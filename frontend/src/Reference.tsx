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
import { tr, type MessageKey } from "./i18n";
import { CodeTaxes, TaxesPanel } from "./Taxes";
import { Chip, fmtDate, PageHeader, StatCard, type Tone } from "./ui";

const QUALITY: Record<string, MessageKey> = { known: "originRead", unknown: "unknownBlank", unparseable: "notNumeric" };
const STATES: Record<string, MessageKey> = {
  extracted: "extractedFrom",
  derived: "derivedHierarchy",
  review_required: "toReview",
  validated: "validated",
};
const label = (map: Record<string, MessageKey>, value: string) => (map[value] ? tr(map[value]) : value);
const PUBLICATION_KEYS: Record<string, { label: MessageKey; tone: Tone }> = {
  operational: { label: "pub.operational", tone: "green" },
  consultation: { label: "pub.consultation", tone: "amber" },
  draft: { label: "pub.draft", tone: "gray" },
  withdrawn: { label: "pub.withdrawn", tone: "gray" },
};
/** État de publication d'une édition, dans la langue affichée. */
const PUBLICATION = new Proxy({} as Record<string, { label: string; tone: Tone } | undefined>, {
  get: (_, state: string) => (PUBLICATION_KEYS[state] ? { label: tr(PUBLICATION_KEYS[state].label), tone: PUBLICATION_KEYS[state].tone } : undefined),
});

/** Recherche tarifaire : code, préfixe ou mots, avec la fiche du code à droite. */
export function TariffSearch({ initialQuery = "" }: { initialQuery?: string }) {
  return (
    <>
      <nav className="breadcrumb" aria-label={tr("nav.breadcrumb")}>
        <span>{tr("ref.goods")}</span>
        <Icon name="chevronRight" size={14} />
        <span>{tr("nav.tariffSearch")}</span>
      </nav>
      <PageHeader
        title={tr("nav.tariffSearch")}
        subtitle={
          <>
            <strong className="subtitle-strong">{tr("ref.searchStrong")}</strong>
            <span className="block">{tr("ref.searchText")}</span>
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
      setError(err instanceof ApiError ? err.message : tr("searchUnavailable"));
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
        <h2 id="ref-title" className="card-title">{tr("ref.tariff")}</h2>
        <form className="searchbar" onSubmit={search} role="search">
          <label>
            <Icon name="search" />
            <input aria-label={tr("codeSearch")} value={q} onChange={(e) => setQ(e.target.value)} placeholder={tr("ref.placeholder")} required />
          </label>
          <button type="submit" className="btn-primary">{tr("search")}</button>
        </form>
        {results && results.length > 0 && (
          <div className="table-tools spaced">
            <label className="filter-mini">
              <Icon name="filter" size={16} />
              <select aria-label={tr("ref.chapter")} value={chapter} onChange={(e) => setChapter(e.target.value)}>
                <option value="">{tr("ref.allChapters")}</option>
                {chapters.map((c) => (
                  <option key={c} value={c}>{tr("ref.chapterN", { n: c })}</option>
                ))}
              </select>
            </label>
            <label className="check-inline">
              <input type="checkbox" checked={declarableOnly} onChange={(e) => setDeclarableOnly(e.target.checked)} /> {tr("ref.declarableOnly")}
            </label>
            <span className="muted small">{tr("ref.results", { n: shown.length })}</span>
          </div>
        )}
        {error && <p role="alert" className="error">⚠ {error}</p>}
        {results === null && <p className="empty">{tr("ref.typeToSearch")}</p>}
        {results && results.length === 0 && <p className="empty">{tr("noResults")}</p>}
        {results && results.length > 0 && (
          <div className="table-wrap">
            <table className="data selectable">
              <thead>
                <tr>
                  <th scope="col">{tr("ref.hsCode")}</th><th scope="col">{tr("ref.label")}</th><th scope="col">{tr("ref.chapter")}</th><th scope="col">{tr("ref.why")}</th>
                  <th scope="col">{tr("ref.state")}</th>
                </tr>
              </thead>
              <tbody>
                {shown.map((r) => (
                  <tr key={r.id} className={detail?.id === r.id ? "selected" : undefined} onClick={() => void open(r.id)}>
                    <td>
                      <button type="button" className="link code" onClick={() => void open(r.id)}>{r.code_display}</button>
                    </td>
                    <td>
                      {r.label || <em className="muted">{tr("sourceLabelMissing")}</em>}
                      {r.label_damaged && <Chip tone="amber">{tr("sourceDamaged")}</Chip>}
                    </td>
                    <td className="small">{chapterOf(r.code) || "—"}</td>
                    <td className="small muted">{r.reason}</td>
                    <td>
                      {r.declarable ? <Chip tone="blue">{tr("ref.declarable")}</Chip> : <Chip tone="gray">{tr("ref.grouping")}</Chip>}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
        {results && results.length > 0 && (
          <p className="muted small">{tr("ref.editionQueried", { list: [...new Set(results.map((r) => r.edition.label))].join(", ") })}</p>
        )}
      </section>
      <section className="card side-panel" aria-label={tr("ref.codeDetail")}>
        <div className="card-head">
          <h2 className="card-title">{tr("ref.codeDetail")}</h2>
          {detail && (
            <button type="button" className="icon-button" onClick={() => setDetail(null)} aria-label={tr("ref.closeDetail")}>
              <Icon name="x" />
            </button>
          )}
        </div>
        {detail ? <NodePanel detail={detail} onOpen={(id) => void open(id)} /> : <p className="empty">{tr("ref.pickCode")}</p>}
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
      <p className="node-label">{detail.label || <em className="muted">{tr("noSourceLabel")}</em>}</p>
      <nav aria-label={tr("path")} className="crumbs small">
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

      <h3>{tr("ref.general")}</h3>
      <dl className="kv">
        <dt>{tr("ref.edition")}</dt>
        <dd>
          {detail.edition.label}
          <span className="block small muted">
            {detail.edition.source.kind_label}
            {detail.edition.source.is_derived_copy && tr("ref.derivedCopyParen")}
          </span>
        </dd>
        <dt>{tr("tariffDeclarable")}</dt>
        <dd>{detail.declarable ? tr("yes") : tr("no")}</dd>
        <dt>{tr("ref.state")}</dt>
        <dd>{label(STATES, detail.validation_state)}</dd>
        <dt>{tr("proof")}</dt>
        <dd>
          {detail.evidence ? (
            <button type="button" className="link" onClick={() => void openEvidence(detail.evidence)}>
              {tr("ref.openAt", { loc: detail.evidence.location })}
            </button>
          ) : (
            tr("derivedHierarchy")
          )}
        </dd>
      </dl>

      <CodeTaxes code={detail.code} />

      <h3>{tr("fx.sourceValues")}</h3>
      {detail.rate_observations.items.length === 0 ? (
        <p className="muted small">{tr("ref.noValue")}</p>
      ) : (
        <>
          <p className="muted small">{detail.rate_observations.warning}</p>
          <table className="data compact">
            <thead>
              <tr><th scope="col">{tr("column")}</th><th scope="col">{tr("rawValue")}</th><th scope="col">{tr("reading")}</th></tr>
            </thead>
            <tbody>
              {detail.rate_observations.items.map((r) => (
                <tr key={r.column}>
                  <td>{r.column}</td>
                  <td>{r.raw_value || "—"}</td>
                  <td>{label(QUALITY, r.quality)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </>
      )}

      <h3>{tr("ref.versionValidity")}</h3>
      <dl className="kv">
        <dt>{tr("ref.version")}</dt>
        <dd>
          {detail.edition.label}{" "}
          <Chip tone={PUBLICATION[detail.edition.publication_state]?.tone ?? "gray"}>
            {detail.edition.publication_state === "operational" ? tr("ref.current") : tr("ref.historical")}
          </Chip>
        </dd>
        <dt>{tr("ref.effective")}</dt>
        <dd>{detail.edition.publication_state === "operational" ? tr("ref.seeEdition") : <em className="muted">{tr("ref.notVerified")}</em>}</dd>
        <dt>{tr("ref.endDate")}</dt>
        <dd>—</dd>
      </dl>
      <h3>{tr("ref.versionHistory")}</h3>
      <table className="data compact">
        <thead>
          <tr><th scope="col">{tr("ref.edition")}</th><th scope="col">{tr("ref.state")}</th></tr>
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
      {detail.same_code_in_other_editions.length === 0 && <p className="muted small">{tr("ref.onlyHere")}</p>}

      {detail.issues.length > 0 && (
        <>
          <h3>{tr("anomalies")}</h3>
          <ul className="issue-list">
            {detail.issues.map((i) => (
              <li key={i.id} className={i.severity === "blocking" ? "issue-red" : "issue-amber"}>
                {i.message} {i.state === "resolved" && tr("ref.resolvedParen")}
              </li>
            ))}
          </ul>
        </>
      )}
      {notes.length > 0 && (
        <>
          <h3>{tr("notes")}</h3>
          {notes.map((n) => (
            <details key={n.id}>
              <summary>
                {tr(n.scope_type === "chapter" ? "ref.noteChapter" : "ref.noteSection", { ref: n.scope_ref, edition: n.edition.label })}
              </summary>
              <pre className="note">{n.text}</pre>
              <button type="button" className="link" onClick={() => void openEvidence(n.evidence)}>
                {tr("ref.openAt", { loc: n.evidence?.location ?? "" })}
              </button>
            </details>
          ))}
        </>
      )}
      {detail.children.length > 0 && (
        <>
          <h3>{tr("subdivisions")}</h3>
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
        <div className="evidence" role="region" aria-label={tr("proof")}>
          <h3>{tr("ref.proofAt", { loc: record.location })}</h3>
          <p className="muted small">
            {record.source.title}
            {record.source.is_derived_copy && ` (${tr("ref.derivedShort")})`} · {tr("ref.fingerprint", { hash: record.source.sha256.slice(0, 12) })}
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
      <nav className="breadcrumb" aria-label={tr("nav.breadcrumb")}>
        <span>{tr("nav.reference")}</span>
        <Icon name="chevronRight" size={14} />
        <span>{tr("ref.adminTitle")}</span>
      </nav>
      <PageHeader
        title={tr("ref.adminTitle")}
        subtitle={tr("ref.adminSub")}
      />
      <div role="tablist" className="tabs" aria-label={tr("ref.sections")}>
        {(
          [
            ["tarif", "ref.tariff", "file"],
            ["taxes", "ref.taxesRules", "layers"],
            ["versions", "ref.versions", "history"],
            ["import", "ref.importExcel", "upload"],
          ] as const
        ).map(([key, key2, icon]) => (
          <button key={key} type="button" role="tab" aria-selected={tab === key} onClick={() => setTab(key)}>
            <Icon name={icon} size={18} /> {tr(key2)}
          </button>
        ))}
      </div>
      {tab !== "taxes" && (
      <div className="stats stats-3">
        <StatCard
          icon="file"
          tone="green"
          label={tr("ref.activeVersion")}
          value={operational ? operational.label : tr("ref.noneF")}
          hint={operational ? tr("ref.inForce") : tr("ref.allConsultation")}
        />
        <StatCard icon="clock" tone="blue" label={tr("ref.lastUpdate")} value={latest?.published_at ? fmtDate(latest.published_at) : "—"} hint={latest?.label} />
        <StatCard
          icon="book"
          tone="green"
          label={tr("ref.tariffLines")}
          value={lines ?? "—"}
          hint={lines ? (operational ?? latest)?.label : canSeeImports ? tr("ref.noImport") : tr("ref.managerOnly")}
        />
      </div>
      )}

      {tab === "tarif" && (
        <>
          <div className="action-bar">
            <button type="button" className="btn-primary" disabled={!canSeeImports} onClick={() => setTab("import")}>
              <Icon name="plus" /> {tr("ref.importNew")}
            </button>
            <button type="button" className="btn-secondary" disabled title={tr("ref.compareHint")}>
              <Icon name="refresh" /> {tr("ref.compare")}
            </button>
            <button type="button" className="btn-secondary" disabled title={tr("ref.exportHint")}>
              <Icon name="upload" /> {tr("ref.export")}
            </button>
          </div>
          <TariffExplorer />
        </>
      )}

      {tab === "taxes" && <TaxesPanel />}

      {tab === "versions" && (
      <section className="card" aria-labelledby="editions-title">
        <h2 id="editions-title" className="card-title">{tr("ref.editions")}</h2>
        {editions === null ? (
          <p className="muted">{tr("loading")}</p>
        ) : editions.length === 0 ? (
          <p className="empty">{tr("ref.noEdition")}</p>
        ) : (
          <div className="table-wrap">
            <table className="data">
              <thead>
                <tr><th scope="col">{tr("ref.edition")}</th><th scope="col">{tr("ref.source")}</th><th scope="col">{tr("ref.effective")}</th><th scope="col">{tr("ref.publishedOn")}</th><th scope="col">{tr("ref.state")}</th></tr>
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
                      {e.source?.is_derived_copy && <span className="block muted">{tr("ref.derivedShort")}</span>}
                    </td>
                    <td>{e.effective_from ? fmtDate(e.effective_from) : <em className="muted">{tr("ref.notVerified")}</em>}</td>
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
          <h2 id="imports-title" className="card-title">{tr("ref.importExcel")}</h2>
          <p className="muted small">
            {tr("ref.importText1")} {tr("ref.importText2", { cmd: "import_tariff_xlsx" })}
          </p>
          {!canSeeImports ? (
            <p className="empty">{tr("ref.importsManager")}</p>
          ) : !runs || runs.length === 0 ? (
            <p className="empty">{tr("ref.noImports")}</p>
          ) : (
            <div className="table-wrap">
              <table className="data">
                <thead>
                  <tr><th scope="col">{tr("ref.source")}</th><th scope="col">{tr("ref.importedOn")}</th><th scope="col">{tr("ref.tariffLines")}</th><th scope="col">{tr("ref.openIssues")}</th></tr>
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
