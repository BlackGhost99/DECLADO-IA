import { Fragment, useCallback, useEffect, useState, type FormEvent } from "react";
import {
  api,
  ApiError,
  type AuditEntry,
  type CaseDetail,
  type CaseDocument,
  type CodeCheck,
  type FieldSource,
  type GoodsLine,
  type Invoice,
  type Me,
  type Membership,
  type Preview,
  type Revision,
} from "./api";
import { Controls, controlItems } from "./Controls";
import { Divergences, ExtractionControls, Flags, LineEditor, OriginBadge, TotalsPanel } from "./Extraction";
import { Icon, type IconName } from "./Icon";
import { ProposalsPanel } from "./Proposals";
import { navigate, rememberCase } from "./router";
import {
  caseSteps,
  Chip,
  errorText,
  eventIcon,
  eventLabel,
  fmtDate,
  fmtDateTime,
  goodsStatus,
  personName,
  StatCard,
  StateChip,
  Stepper,
  type EditionOption,
  type Tone,
} from "./ui";

const USAGES: [string, string][] = [
  ["invoice", "Facture"],
  ["packing_list", "Liste de colisage"],
  ["transport", "Document de transport"],
  ["origin", "Certificat d'origine"],
  ["other", "Autre pièce"],
];

const CONFIRMATION: Record<string, string> = {
  pending: "confirmation métier attendue",
  confirmed: "confirmé",
  stale: "données modifiées depuis le contrôle : relancer",
};

export const CASE_TABS: { key: string; label: string; icon: IconName }[] = [
  { key: "apercu", label: "Aperçu", icon: "eye" },
  { key: "documents", label: "Documents", icon: "file" },
  { key: "donnees", label: "Données extraites", icon: "edit" },
  { key: "marchandises", label: "Marchandises", icon: "box" },
  { key: "controles", label: "Contrôles", icon: "checkCircle" },
  { key: "calculs", label: "Calculs", icon: "calculator" },
  { key: "validation", label: "Validation", icon: "shield" },
  { key: "export", label: "Export", icon: "upload" },
  { key: "historique", label: "Historique", icon: "history" },
];

type Act = (a: () => Promise<unknown>) => Promise<void>;

/** « 1 500,00 » → « 1500.00 » ; le texte reste une chaîne, jamais un nombre flottant. */
export function decimalInput(value: string): string | null {
  const v = value.replace(/\s/g, "");
  if (!v) return null;
  return v.includes(",") && !v.includes(".") ? v.replace(",", ".") : v;
}

function formatBytes(n: number) {
  return n > 1024 * 1024 ? `${(n / 1024 / 1024).toFixed(1)} Mo` : `${Math.max(1, Math.round(n / 1024))} Ko`;
}

const running = (rev: Revision) =>
  rev.documents.some((d) => d.latest_extraction && (d.latest_extraction.status === "queued" || d.latest_extraction.status === "running"));

export function CaseDetailView({
  caseId,
  tab,
  me,
  membership,
}: {
  caseId: string;
  tab: string;
  me: Pick<Me, "id">;
  membership: Membership;
}) {
  const canEdit = membership.roles.some((r) => r === "declarant" || r === "validator");
  const [detail, setDetail] = useState<CaseDetail | null>(null);
  const [editions, setEditions] = useState<EditionOption[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [tick, setTick] = useState(0);

  const reload = useCallback(async () => {
    try {
      setDetail(await api.caseDetail(caseId));
      setTick((t) => t + 1);
    } catch (err) {
      setError(errorText(err, "Dossier introuvable."));
    }
  }, [caseId]);

  useEffect(() => {
    rememberCase(caseId);
    void reload();
    api.editions().then(
      (list) => setEditions(list.filter((e) => e.publication_state !== "withdrawn")),
      () => setEditions([]),
    );
  }, [caseId, reload]);

  // Une lecture lancée depuis « Nouveau dossier » se termine en arrière-plan : on suit son avancement.
  useEffect(() => {
    if (!detail || !running(detail.revision)) return;
    const timer = setTimeout(() => void reload(), 2000);
    return () => clearTimeout(timer);
  }, [detail, reload]);

  async function act(action: () => Promise<unknown>) {
    setError(null);
    try {
      await action();
    } catch (err) {
      setError(errorText(err, "Action impossible."));
    }
    await reload();
  }

  if (!detail) return <p className="muted">{error ?? "Chargement…"}</p>;
  const rev = detail.revision;
  const editable = canEdit && rev.is_editable;
  const steps = caseSteps(rev);
  const go = (key: string) => navigate(`/dossiers/${detail.id}/${key}`);

  return (
    <>
      <nav className="breadcrumb" aria-label="Fil d'Ariane">
        <button type="button" className="link" onClick={() => navigate("/dossiers")}>
          <Icon name="arrowLeft" size={16} /> Mes dossiers
        </button>
        <Icon name="chevronRight" size={14} />
        <span className="code">{detail.reference}</span>
      </nav>
      <div className="case-header">
        <div>
          <h1 id="case-title">
            Dossier <span className="code">{detail.reference}</span>
            {detail.importer && <> — {detail.importer.name}</>}
          </h1>
          <p className="case-meta">
            {detail.title && <span>{detail.title}</span>}
            <span>{rev.mode_label}</span>
            <span>Révision {rev.revision_no}</span>
            <span>
              Créé le {fmtDate(detail.created_at)} par {personName(detail.created_by)}
            </span>
            <span>
              Agent : {personName(detail.assigned_to) || "non affecté"}
              {canEdit && !detail.assigned_to && (
                <button type="button" className="btn-small" onClick={() => act(() => api.assignCase(detail.id, me.id, detail.row_version))}>
                  Prendre le dossier
                </button>
              )}
            </span>
          </p>
        </div>
        <StateChip state={rev.state} label={rev.state_label} />
      </div>
      {error && <p role="alert" className="error">⚠ {error}</p>}

      <section className="card stepper-card">
        <Stepper steps={steps} onSelect={go} />
      </section>

      <div role="tablist" className="tabs" aria-label="Sections du dossier">
        {CASE_TABS.map((t) => (
          <button key={t.key} type="button" role="tab" aria-selected={tab === t.key} onClick={() => go(t.key)}>
            <Icon name={t.icon} size={18} />
            {t.label}
          </button>
        ))}
      </div>

      <div role="tabpanel">
        {tab === "apercu" && (
          <Overview detail={detail} editions={editions} editable={editable} act={act} go={go} />
        )}
        {tab === "documents" && <DocumentsTab caseId={detail.id} revision={rev} editable={editable} onChange={reload} />}
        {tab === "donnees" && <Invoices revision={rev} editable={editable} act={act} />}
        {tab === "marchandises" && <GoodsTab revision={rev} editions={editions} editable={editable} act={act} />}
        {tab === "controles" && <Controls detail={detail} go={go} />}
        {tab === "calculs" && <Calculation revision={rev} go={go} />}
        {(tab === "validation" || tab === "export") && <Finalisation detail={detail} kind={tab} go={go} />}
        {tab === "historique" && <History caseId={detail.id} version={tick} />}
      </div>
    </>
  );
}

// ---- Aperçu ------------------------------------------------------------------------------------

function Overview({
  detail,
  editions,
  editable,
  act,
  go,
}: {
  detail: CaseDetail;
  editions: EditionOption[];
  editable: boolean;
  act: Act;
  go: (tab: string) => void;
}) {
  const rev = detail.revision;
  const next = caseSteps(rev).find((s) => s.state === "current");
  return (
    <div className="grid-2-1">
      <div>
        <section className="card" aria-labelledby="info-title">
          <h2 id="info-title" className="card-title">Informations du dossier</h2>
          <p className="muted small">{rev.status_note}</p>
          {rev.target_edition?.warning && <p className="note-amber small" role="note">ⓘ {rev.target_edition.warning}</p>}
          <RevisionForm revision={rev} editions={editions} editable={editable} onSave={(data) => act(() => api.updateRevision(rev.id, data))} />
        </section>
        <Completeness revision={rev} />
      </div>
      <section className="card">
        <h2 className="card-title">Prochaine étape</h2>
        {next ? (
          <>
            <p className="big-line">{next.label}</p>
            <p className="muted">{next.detail}</p>
            <button type="button" className="btn-primary" onClick={() => go(next.key)}>
              Continuer <Icon name="arrowRight" />
            </button>
          </>
        ) : (
          <p>Les étapes disponibles sont terminées. Le calcul et l'export arriveront dans les prochaines versions.</p>
        )}
      </section>
    </div>
  );
}

function RevisionForm({
  revision,
  editions,
  editable,
  onSave,
}: {
  revision: Revision;
  editions: EditionOption[];
  editable: boolean;
  onSave: (data: Record<string, unknown>) => void;
}) {
  const [form, setForm] = useState({
    planned_declaration_date: revision.planned_declaration_date ?? "",
    regime: revision.regime,
    target_edition_id: revision.target_edition?.id ?? "",
  });
  useEffect(() => {
    setForm({
      planned_declaration_date: revision.planned_declaration_date ?? "",
      regime: revision.regime,
      target_edition_id: revision.target_edition?.id ?? "",
    });
  }, [revision]);

  function submit(event: FormEvent) {
    event.preventDefault();
    onSave({
      planned_declaration_date: form.planned_declaration_date || null,
      regime: form.regime,
      target_edition_id: form.target_edition_id || null,
      row_version: revision.row_version,
    });
  }

  return (
    <form onSubmit={submit}>
      <fieldset disabled={!editable} className="form-grid plain-fieldset">
        <label>
          Date de déclaration prévue
          <input type="date" value={form.planned_declaration_date} onChange={(e) => setForm({ ...form, planned_declaration_date: e.target.value })} />
        </label>
        <label>
          Régime
          <input value={form.regime} onChange={(e) => setForm({ ...form, regime: e.target.value })} />
        </label>
        <label>
          Tarif utilisé
          <select value={form.target_edition_id} onChange={(e) => setForm({ ...form, target_edition_id: e.target.value })}>
            <option value="">À choisir</option>
            {editions.map((e) => (
              <option key={e.id} value={e.id}>{e.label}</option>
            ))}
          </select>
        </label>
        <div className="form-end">
          <button type="submit" className="btn-secondary">Enregistrer</button>
        </div>
      </fieldset>
    </form>
  );
}

function Completeness({ revision }: { revision: Revision }) {
  const { blocking, warnings } = revision.completeness;
  return (
    <section className="card" aria-labelledby="completeness-title">
      <h2 id="completeness-title" className="card-title">Avant calcul et validation</h2>
      {blocking.length === 0 ? (
        <p className="ok-line"><Icon name="checkCircle" size={18} /> Aucun manque bloquant.</p>
      ) : (
        <>
          <p className="muted small">{blocking.length} élément(s) à compléter. Le brouillon reste enregistrable.</p>
          <ul className="issue-list">
            {blocking.map((b) => (
              <li key={`${b.id}-${b.field}`} className="issue-red">
                <strong>{b.label}</strong> : {b.message}
              </li>
            ))}
          </ul>
        </>
      )}
      {warnings.length > 0 && (
        <>
          <h3>À examiner</h3>
          <ul className="issue-list">
            {warnings.map((w) => (
              <li key={`${w.id}-${w.field}-${w.message}`} className="issue-amber">
                <strong>{w.label}</strong> : {w.message}
              </li>
            ))}
          </ul>
        </>
      )}
    </section>
  );
}

// ---- Documents : la pièce au centre, les données lues à droite --------------------------------

function DocumentsTab({
  caseId,
  revision,
  editable,
  onChange,
}: {
  caseId: string;
  revision: Revision;
  editable: boolean;
  onChange: () => Promise<void>;
}) {
  const active = revision.documents.filter((d) => !d.replaced_by_id);
  const replaced = revision.documents.filter((d) => d.replaced_by_id);
  const [selectedId, setSelectedId] = useState<string | null>(
    (active.find((d) => d.usage === "invoice") ?? active[0])?.id ?? null,
  );
  const [page, setPage] = useState<number | null>(null);
  const selected = revision.documents.find((d) => d.id === selectedId) ?? active[0] ?? null;

  useEffect(() => {
    if (!selectedId && active[0]) setSelectedId(active[0].id);
  }, [active, selectedId]);

  return (
    <div className="doc-layout">
      <section className="card doc-list" aria-labelledby="docs-title">
        <h2 id="docs-title" className="card-title">Documents du dossier</h2>
        {editable && <Upload caseId={caseId} onDone={async (id) => { await onChange(); if (id) setSelectedId(id); }} />}
        {active.length === 0 ? (
          <p className="empty">Aucune pièce.</p>
        ) : (
          <ul className="doc-items">
            {active.map((link) => (
              <li key={link.id}>
                <button
                  type="button"
                  className={`doc-item${selected?.id === link.id ? " selected" : ""}`}
                  onClick={() => { setSelectedId(link.id); setPage(null); }}
                >
                  <span className={`doc-type doc-${link.document.mime.includes("pdf") ? "pdf" : link.document.mime.startsWith("image/") ? "img" : "xls"}`}>
                    {link.document.mime.includes("pdf") ? "PDF" : link.document.mime.startsWith("image/") ? "IMG" : "XLS"}
                  </span>
                  <span className="doc-text">
                    <strong>{link.usage_label}</strong>
                    <span>{link.document.original_name}</span>
                    <small>
                      {fmtDate(link.created_at)} · {formatBytes(link.document.bytes)}
                      {link.document.readability !== "ok" && ` · ${link.document.readability_label}`}
                    </small>
                  </span>
                </button>
              </li>
            ))}
          </ul>
        )}
        {replaced.length > 0 && (
          <details className="small">
            <summary>{replaced.length} version(s) remplacée(s), conservée(s)</summary>
            <ul>
              {replaced.map((d) => (
                <li key={d.id}>{d.document.original_name} (v{d.document.version})</li>
              ))}
            </ul>
          </details>
        )}
      </section>

      <section className="card viewer" aria-label="Aperçu de la pièce">
        {selected ? <Viewer link={selected} page={page} /> : <p className="empty">Ajoutez une pièce pour l'afficher ici.</p>}
      </section>

      <section className="card" aria-labelledby="extracted-title">
        <h2 id="extracted-title" className="card-title">Données lues</h2>
        {selected ? (
          <ExtractedPanel link={selected} revision={revision} editable={editable} onChange={onChange} onPage={setPage} />
        ) : (
          <p className="empty">Aucune pièce sélectionnée.</p>
        )}
      </section>
    </div>
  );
}

function Upload({ caseId, onDone }: { caseId: string; onDone: (selectId: string | null) => Promise<void> }) {
  const [open, setOpen] = useState(false);
  const [limits, setLimits] = useState<{ max_bytes: number; accepted: string[] } | null>(null);
  const [file, setFile] = useState<File | null>(null);
  const [usage, setUsage] = useState("invoice");
  const [duplicate, setDuplicate] = useState<{ id: string; original_name: string; cases: string[] }[] | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (open && !limits) api.documentLimits().then(setLimits, () => setLimits(null));
  }, [open, limits]);

  async function send(action: "" | "keep_both" = "") {
    if (!file) return;
    setError(null);
    setMessage(null);
    try {
      const link = await api.uploadDocument(caseId, file, usage, action, crypto.randomUUID());
      setDuplicate(null);
      setMessage(
        link.document.readability === "ok"
          ? `« ${link.document.original_name} » ajouté.`
          : `« ${link.document.original_name} » conservé, mais ${link.document.readability_label.toLowerCase()}.`,
      );
      setFile(null);
      setOpen(false);
      await onDone(link.id);
    } catch (err) {
      if (err instanceof ApiError && err.code === "DUPLICATE_DOCUMENT") {
        setDuplicate((err.details.existing as { id: string; original_name: string; cases: string[] }[]) ?? []);
      } else {
        setError(errorText(err, "Dépôt impossible."));
      }
    }
  }

  async function reuse(id: string) {
    setError(null);
    try {
      const link = await api.reuseDocument(caseId, id, usage);
      setDuplicate(null);
      setOpen(false);
      setMessage("Pièce existante réutilisée, sans nouveau dépôt.");
      await onDone(link.id);
    } catch (err) {
      setError(errorText(err, "Réutilisation impossible."));
    }
  }

  return (
    <div className="upload">
      {!open ? (
        <button type="button" className="btn-primary btn-block" onClick={() => setOpen(true)}>
          <Icon name="plus" /> Ajouter un document
        </button>
      ) : (
        <form className="upload-form" onSubmit={(e) => { e.preventDefault(); void send(); }}>
          <label>
            Fichier
            <input type="file" accept=".pdf,.png,.jpg,.jpeg,.xlsx" onChange={(e) => setFile(e.target.files?.[0] ?? null)} required />
          </label>
          <label>
            Type de pièce
            <select value={usage} onChange={(e) => setUsage(e.target.value)}>
              {USAGES.map(([v, l]) => (
                <option key={v} value={v}>{l}</option>
              ))}
            </select>
          </label>
          {limits && (
            <p className="muted small">
              {limits.accepted.join(", ")} · {formatBytes(limits.max_bytes)} maximum. L'original est conservé tel quel.
            </p>
          )}
          <div className="actions-row">
            <button type="button" className="btn-secondary" onClick={() => setOpen(false)}>Annuler</button>
            <button type="submit" className="btn-primary">Ajouter la pièce</button>
          </div>
        </form>
      )}
      {duplicate && (
        <div className="note-amber small" role="alert">
          <p>Un fichier identique existe déjà dans votre société :</p>
          <ul>
            {duplicate.map((d) => (
              <li key={d.id}>
                {d.original_name} {d.cases.length > 0 && `(dossiers ${d.cases.join(", ")})`}{" "}
                <button type="button" className="btn-small" onClick={() => void reuse(d.id)}>Réutiliser cette pièce</button>
              </li>
            ))}
          </ul>
          <button type="button" className="btn-small" onClick={() => void send("keep_both")}>Conserver les deux</button>{" "}
          <button type="button" className="btn-small" onClick={() => setDuplicate(null)}>Annuler</button>
        </div>
      )}
      {message && <p role="status" className="small">{message}</p>}
      {error && <p role="alert" className="error">⚠ {error}</p>}
    </div>
  );
}

function Viewer({ link, page }: { link: CaseDocument; page: number | null }) {
  const [preview, setPreview] = useState<Preview | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setPreview(null);
    setError(null);
    if (!link.document.previewable) return;
    api.documentPreview(link.document.id).then(setPreview, (err) => setError(errorText(err, "Aperçu impossible.")));
  }, [link.document.id, link.document.previewable]);

  async function download() {
    const { url } = await api.documentLink(link.document.id);
    window.location.assign(url);
  }

  return (
    <>
      <div className="viewer-bar">
        <span className="viewer-name">{link.document.original_name}</span>
        {page && <span className="viewer-page">page {page}</span>}
        <button type="button" className="icon-button" onClick={() => void download()} title="Télécharger">
          <Icon name="download" />
          <span className="visually-hidden">Télécharger</span>
        </button>
      </div>
      <div className="viewer-body">
        {!link.document.previewable && (
          <p className="empty">
            Aperçu indisponible pour cette pièce ({link.document.readability_label.toLowerCase()}).
            {link.document.inspection_notes.map((n) => (
              <span key={n} className="block small">{n}</span>
            ))}
          </p>
        )}
        {error && <p className="error">{error}</p>}
        {preview?.kind === "pdf" && (
          <iframe key={page ?? 0} title={link.document.original_name} src={page ? `${preview.url}#page=${page}` : preview.url} className="preview" />
        )}
        {preview?.kind === "image" && <img alt={link.document.original_name} src={preview.url} className="preview-image" />}
        {preview?.kind === "unavailable" && <p className="note-amber">{preview.message}</p>}
        {preview?.kind === "sheet" && (
          <div className="sheet">
            <p className="muted small">{preview.note}</p>
            {preview.sheets.map((sheet) => (
              <div key={sheet.name}>
                <h3>Feuille « {sheet.name} »{sheet.truncated && " (extrait)"}</h3>
                <table className="small">
                  <tbody>
                    {sheet.rows.map((r) => (
                      <tr key={r.row}>
                        {r.cells.map((c) => (
                          <td key={c.ref} title={c.formula ?? undefined}>
                            <span className="muted code">{c.ref}</span> {c.value ?? (c.formula ? <em>{c.formula}</em> : "")}
                          </td>
                        ))}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ))}
          </div>
        )}
      </div>
    </>
  );
}

/** Statut affiché d'une valeur : inconnue, à vérifier, saisie ou lue. */
function fieldStatus(value: unknown, origin: string | undefined, flagged: boolean): { tone: Tone; label: string } {
  if (value === null || value === undefined || value === "") return { tone: "gray", label: "Inconnu" };
  if (flagged) return { tone: "amber", label: "À vérifier" };
  if (origin === "manual") return { tone: "blue", label: "Saisi" };
  return { tone: "green", label: "Lu" };
}

function SourceLink({ source, onPage }: { source?: FieldSource; onPage: (page: number) => void }) {
  const span = source?.span;
  if (!span) return null;
  if (span.sheet) return <span className="source-link">Source : {span.sheet}!{span.cell_range}</span>;
  if (span.page == null) return null;
  return (
    <button type="button" className="source-link" onClick={() => onPage(span.page!)} title={span.excerpt ? `Texte lu : « ${span.excerpt} »` : undefined}>
      Voir la source (p. {span.page}) <Icon name="external" size={13} />
    </button>
  );
}

function ExtractedPanel({
  link,
  revision,
  editable,
  onChange,
  onPage,
}: {
  link: CaseDocument;
  revision: Revision;
  editable: boolean;
  onChange: () => Promise<void>;
  onPage: (page: number) => void;
}) {
  const invoiceId = link.latest_extraction?.invoice_id;
  const invoice: Invoice | undefined =
    revision.invoices.find((i) => i.id === invoiceId) ?? revision.invoices.find((i) => i.document_id === link.id);
  const canRead = link.usage === "invoice" || Boolean(link.latest_extraction);

  return (
    <>
      {canRead ? (
        <ExtractionControls link={link} editable={editable} onDone={onChange} />
      ) : (
        <p className="muted small">La lecture automatique concerne les factures.</p>
      )}
      {invoice ? (
        <>
          <h3>Informations générales</h3>
          <dl className="field-list">
            {(
              [
                ["supplier_name", "Fournisseur", invoice.supplier_name],
                ["invoice_number", "N° facture", invoice.invoice_number],
                ["invoice_date", "Date de facture", invoice.invoice_date ? fmtDate(invoice.invoice_date) : ""],
                ["currency", "Devise", invoice.currency],
                ["declared_total", "Montant total", invoice.declared_total],
                ["incoterm", "Incoterm", invoice.incoterm],
              ] as [string, string, string | null][]
            ).map(([field, label, value]) => {
              const flagged = (invoice.review_flags ?? []).some((f) => f.field === field);
              const status = fieldStatus(value, invoice.field_origins?.[field], flagged);
              return (
                <div key={field} className="field-row">
                  <dt>{label}</dt>
                  <dd>
                    <span className="field-value">{value || "—"}</span>
                    <SourceLink source={invoice.field_sources?.[field]} onPage={onPage} />
                    <Flags flags={invoice.review_flags} field={field} />
                  </dd>
                  <Chip tone={status.tone}>{status.label}</Chip>
                </div>
              );
            })}
          </dl>
          <h3>Détail des marchandises ({invoice.lines.length} ligne{invoice.lines.length > 1 ? "s" : ""})</h3>
          <div className="table-wrap">
            <table className="data compact">
              <thead>
                <tr>
                  <th scope="col">#</th><th scope="col">Description</th><th scope="col">Code SH lu</th>
                  <th scope="col">Qté</th><th scope="col">Montant</th><th scope="col">Statut</th>
                </tr>
              </thead>
              <tbody>
                {invoice.lines.map((ln) => {
                  const status = fieldStatus(ln.description_raw || ln.amount, ln.entry_origin, (ln.review_flags ?? []).length > 0);
                  const code = ln.codes.find((c) => c.code_kind === "customs") ?? ln.codes[0];
                  return (
                    <tr key={ln.id}>
                      <td>{ln.ordinal}</td>
                      <td>{ln.description_raw || <em className="muted">inconnue</em>}</td>
                      <td className="code">{code?.raw_code ?? "—"}</td>
                      <td>{ln.quantity ?? "?"} {ln.unit}</td>
                      <td>{ln.amount ?? <em className="muted">inconnu</em>}</td>
                      <td><Chip tone={status.tone}>{status.label}</Chip></td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
          <TotalsPanel totals={invoice.totals_check} currency={invoice.currency} />
        </>
      ) : (
        link.latest_extraction?.status === "succeeded" && <p className="muted small">Aucune facture structurée dans cette lecture.</p>
      )}
    </>
  );
}

// ---- Données extraites : saisie, corrections, divergences --------------------------------------

const EMPTY_LINE = {
  description_raw: "",
  source_reference: "",
  customs_code: "",
  customs_code_label: "HS Code",
  quantity: "",
  unit: "",
  unit_price: "",
  amount: "",
  origin_country: "",
  evidence_document_id: "",
  evidence_page: "",
};

function Invoices({ revision, editable, act }: { revision: Revision; editable: boolean; act: Act }) {
  const [form, setForm] = useState({ supplier_name: "", invoice_number: "", invoice_date: "", currency: "", declared_total: "", document_id: "" });
  const invoiceDocs = revision.documents.filter((d) => !d.replaced_by_id);

  function add(event: FormEvent) {
    event.preventDefault();
    void act(async () => {
      await api.addInvoice(revision.id, {
        ...form,
        invoice_date: form.invoice_date || null,
        declared_total: decimalInput(form.declared_total),
        document_id: form.document_id || null,
      });
      setForm({ supplier_name: "", invoice_number: "", invoice_date: "", currency: "", declared_total: "", document_id: "" });
    });
  }

  return (
    <section className="card" aria-labelledby="invoices-title">
      <h2 id="invoices-title" className="card-title">Factures et lignes</h2>
      <p className="muted small">
        Chaque valeur indique si elle a été lue ou saisie. Une correction garde l'ancienne valeur, son auteur et son motif.
      </p>
      {revision.invoices.length === 0 && <p className="empty">Aucune facture. Lisez une pièce dans l'onglet Documents, ou saisissez-la ci-dessous.</p>}
      {revision.invoices.map((inv) => (
        <InvoiceBlock key={inv.id} invoice={inv} revision={revision} editable={editable} act={act} />
      ))}
      {editable && (
        <details className="subcard">
          <summary>Saisir une facture à la main</summary>
          <form className="form-grid" onSubmit={add} aria-label="Ajouter une facture">
            <label>Fournisseur<input value={form.supplier_name} onChange={(e) => setForm({ ...form, supplier_name: e.target.value })} /></label>
            <label>N° facture<input value={form.invoice_number} onChange={(e) => setForm({ ...form, invoice_number: e.target.value })} /></label>
            <label>Date<input type="date" value={form.invoice_date} onChange={(e) => setForm({ ...form, invoice_date: e.target.value })} /></label>
            <label>Devise<input value={form.currency} maxLength={3} onChange={(e) => setForm({ ...form, currency: e.target.value })} placeholder="EUR" /></label>
            <label>Total imprimé<input inputMode="decimal" value={form.declared_total} onChange={(e) => setForm({ ...form, declared_total: e.target.value })} /></label>
            <label>
              Pièce
              <select value={form.document_id} onChange={(e) => setForm({ ...form, document_id: e.target.value })}>
                <option value="">—</option>
                {invoiceDocs.map((d) => (
                  <option key={d.id} value={d.id}>{d.document.original_name}</option>
                ))}
              </select>
            </label>
            <div className="form-end"><button type="submit" className="btn-secondary">Ajouter une facture</button></div>
          </form>
        </details>
      )}
    </section>
  );
}

function InvoiceBlock({ invoice, revision, editable, act }: { invoice: Invoice; revision: Revision; editable: boolean; act: Act }) {
  const [line, setLine] = useState(EMPTY_LINE);
  const [editing, setEditing] = useState<string | null>(null);
  const docs = revision.documents.filter((d) => !d.replaced_by_id);
  const sources = invoice.field_sources ?? {};
  const origins = invoice.field_origins ?? {};
  const headerFields: [string, string, string | null][] = [
    ["supplier_name", "Fournisseur", invoice.supplier_name],
    ["invoice_number", "N°", invoice.invoice_number],
    ["invoice_date", "Date", invoice.invoice_date],
    ["currency", "Devise", invoice.currency],
    ["incoterm", "Incoterm", invoice.incoterm],
    ["declared_total", "Total imprimé", invoice.declared_total],
  ];

  function add(event: FormEvent) {
    event.preventDefault();
    void act(async () => {
      await api.addLine(invoice.id, {
        ...line,
        quantity: decimalInput(line.quantity),
        unit_price: decimalInput(line.unit_price),
        amount: decimalInput(line.amount),
        evidence_document_id: line.evidence_document_id || null,
        evidence_page: line.evidence_page ? Number(line.evidence_page) : null,
      });
      setLine(EMPTY_LINE);
    });
  }

  return (
    <div className="subcard">
      <h3>
        Facture {invoice.ordinal} · {invoice.supplier_name || <em className="muted">fournisseur ?</em>} ·{" "}
        {invoice.invoice_number || "n° ?"} · {invoice.currency || "devise ?"}
        {invoice.declared_total && ` · total imprimé ${invoice.declared_total}`}
      </h3>
      {invoice.latest_extraction_id && (
        <dl className="facts small" aria-label={`En-tête lu de la facture ${invoice.ordinal}`}>
          {headerFields.map(([field, label, value]) => (
            <div key={field} className="fact">
              <dt>{label}</dt>
              <dd>
                {value || <em className="muted">inconnu</em>} <OriginBadge origin={origins[field]} source={sources[field]} />
                <Flags flags={invoice.review_flags} field={field} />
              </dd>
            </div>
          ))}
        </dl>
      )}
      <TotalsPanel totals={invoice.totals_check} currency={invoice.currency} />
      <Divergences invoice={invoice} editable={editable} act={act} />
      {invoice.lines.length > 0 && (
        <div className="table-wrap">
          <table className="data compact">
            <thead>
              <tr>
                <th scope="col">N°</th><th scope="col">Désignation</th><th scope="col">Réf. fournisseur</th>
                <th scope="col">Code douanier lu</th><th scope="col">Qté</th><th scope="col">PU</th>
                <th scope="col">Montant</th><th scope="col">Origine</th><th scope="col">Marchandise</th>
              </tr>
            </thead>
            <tbody>
              {invoice.lines.map((ln) => (
                <Fragment key={ln.id}>
                  <tr>
                    <td>{ln.ordinal}</td>
                    <td>
                      {ln.description_raw || <em className="muted">?</em>}
                      <div className="muted">
                        {ln.entry_origin_label} <OriginBadge origin={ln.field_origins?.description_raw} source={ln.field_sources?.description_raw} />
                      </div>
                      <Flags flags={ln.review_flags} />
                      {(ln.corrections?.length ?? 0) > 0 && (
                        <details className="muted">
                          <summary>{ln.corrections?.length} correction(s)</summary>
                          <ul>
                            {ln.corrections?.map((c) => (
                              <li key={c.id}>
                                {c.field} : {String(c.previous.value ?? "—")} → {String(c.current.value ?? "—")} par {c.actor}
                                {c.reason && ` (${c.reason})`}
                              </li>
                            ))}
                          </ul>
                        </details>
                      )}
                    </td>
                    <td className="code">{ln.source_reference}</td>
                    <td>
                      {ln.codes.map((c) => (
                        <div key={c.id}>
                          <span className="code">{c.raw_code}</span>{" "}
                          <span className="muted">« {c.field_label} » · {c.code_kind_label}</span>
                        </div>
                      ))}
                      {ln.code_history.length > 0 && <div className="muted">{ln.code_history.length} valeur(s) antérieure(s)</div>}
                    </td>
                    <td>
                      {ln.quantity ?? <em className="muted">inconnue</em>} {ln.unit}{" "}
                      <OriginBadge origin={ln.field_origins?.quantity} source={ln.field_sources?.quantity} />
                    </td>
                    <td>{ln.unit_price ?? "—"}</td>
                    <td>
                      {ln.amount ?? <em className="muted">inconnu</em>}{" "}
                      <OriginBadge origin={ln.field_origins?.amount} source={ln.field_sources?.amount} />
                    </td>
                    <td>{ln.origin_country || "—"}</td>
                    <td>
                      {ln.goods_line_ids.length > 0 ? (
                        "rattachée"
                      ) : editable ? (
                        <button type="button" className="btn-small" onClick={() => void act(() => api.addGoods(revision.id, [ln.id]))}>Préparer</button>
                      ) : (
                        "—"
                      )}
                      {editable && (
                        <button type="button" className="link" onClick={() => setEditing(editing === ln.id ? null : ln.id)}>
                          Corriger
                        </button>
                      )}
                    </td>
                  </tr>
                  {editing === ln.id && (
                    <tr>
                      <td colSpan={9}>
                        <LineEditor line={ln} act={act} toDecimal={decimalInput} onClose={() => setEditing(null)} />
                      </td>
                    </tr>
                  )}
                </Fragment>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {editable && (
        <details>
          <summary>Ajouter une ligne à la main</summary>
          <form className="form-grid small" onSubmit={add} aria-label={`Ajouter une ligne à la facture ${invoice.ordinal}`}>
            <label>Désignation<input value={line.description_raw} onChange={(e) => setLine({ ...line, description_raw: e.target.value })} /></label>
            <label>Réf. article fournisseur<input value={line.source_reference} onChange={(e) => setLine({ ...line, source_reference: e.target.value })} /></label>
            <label>Code douanier lu<input className="code" value={line.customs_code} onChange={(e) => setLine({ ...line, customs_code: e.target.value })} placeholder="0101.10.00" /></label>
            <label>Intitulé du champ<input value={line.customs_code_label} onChange={(e) => setLine({ ...line, customs_code_label: e.target.value })} /></label>
            <label>Qté<input inputMode="decimal" value={line.quantity} onChange={(e) => setLine({ ...line, quantity: e.target.value })} /></label>
            <label>Unité<input value={line.unit} onChange={(e) => setLine({ ...line, unit: e.target.value })} /></label>
            <label>PU<input inputMode="decimal" value={line.unit_price} onChange={(e) => setLine({ ...line, unit_price: e.target.value })} /></label>
            <label>Montant<input inputMode="decimal" value={line.amount} onChange={(e) => setLine({ ...line, amount: e.target.value })} /></label>
            <label>Origine<input maxLength={2} value={line.origin_country} onChange={(e) => setLine({ ...line, origin_country: e.target.value })} placeholder="FR" /></label>
            <label>
              Pièce source
              <select value={line.evidence_document_id} onChange={(e) => setLine({ ...line, evidence_document_id: e.target.value })}>
                <option value="">—</option>
                {docs.map((d) => (
                  <option key={d.id} value={d.id}>{d.document.original_name}</option>
                ))}
              </select>
            </label>
            <label>Page<input type="number" min={1} value={line.evidence_page} onChange={(e) => setLine({ ...line, evidence_page: e.target.value })} /></label>
            <div className="form-end"><button type="submit" className="btn-secondary">Ajouter la ligne</button></div>
          </form>
        </details>
      )}
    </div>
  );
}

// ---- Marchandises : la liste à gauche, la proposition tarifaire à droite -----------------------

function GoodsTab({ revision, editions, editable, act }: { revision: Revision; editions: EditionOption[]; editable: boolean; act: Act }) {
  const goods = revision.goods_lines;
  const [selectedId, setSelectedId] = useState<string | null>(goods[0]?.id ?? null);
  const selected = goods.find((g) => g.id === selectedId) ?? goods[0] ?? null;
  const freeInvoices = revision.invoices.filter((i) => i.lines.some((ln) => ln.goods_line_ids.length === 0));
  const freeCount = freeInvoices.reduce((n, i) => n + i.lines.filter((ln) => ln.goods_line_ids.length === 0).length, 0);
  const statuses = goods.map(goodsStatus);
  const validated = statuses.filter((s) => s.label === "Validé").length;
  const toCheck = statuses.filter((s) => s.tone === "amber" || s.tone === "red").length;
  const noCode = statuses.filter((s) => s.label === "À contrôler").length;

  return (
    <>
      <div className="stats">
        <StatCard icon="box" tone="green" label="Marchandises" value={goods.length} hint={freeCount ? `${freeCount} ligne(s) de facture à préparer` : undefined} />
        <StatCard icon="checkCircle" tone="green" label="Codes validés" value={`${validated} / ${goods.length}`} />
        <StatCard icon="alert" tone="amber" label="À valider ou vérifier" value={toCheck} />
        <StatCard icon="search" tone="blue" label="Codes à contrôler" value={noCode} />
      </div>
      <div className="split-panel">
        <section className="card" aria-labelledby="goods-title">
          <div className="card-head">
            <h2 id="goods-title" className="card-title">Liste des marchandises ({goods.length})</h2>
            {editable && freeCount > 0 && (
              <button
                type="button"
                className="btn-primary"
                onClick={() => void act(async () => {
                  for (const inv of freeInvoices) await api.goodsFromInvoice(inv.id);
                })}
              >
                <Icon name="plus" /> Préparer les marchandises ({freeCount})
              </button>
            )}
          </div>
          <p className="muted small">
            Un code retrouvé dans le tarif n'est pas un classement validé : il attend votre confirmation motivée.
          </p>
          {goods.length === 0 ? (
            <p className="empty">Aucune marchandise. Elles se préparent à partir des lignes de facture.</p>
          ) : (
            <div className="table-wrap">
              <table className="data selectable">
                <thead>
                  <tr>
                    <th scope="col">#</th><th scope="col">Description</th><th scope="col">Valeur</th>
                    <th scope="col">Code</th><th scope="col">Statut</th>
                  </tr>
                </thead>
                <tbody>
                  {goods.map((g, i) => {
                    const s = statuses[i];
                    return (
                      <tr key={g.id} className={selected?.id === g.id ? "selected" : undefined} onClick={() => setSelectedId(g.id)}>
                        <td>{g.ordinal}</td>
                        <td>
                          <button type="button" className="row-button" onClick={() => setSelectedId(g.id)}>
                            {g.description || <em className="muted">désignation ?</em>}
                          </button>
                          <div className="muted small">
                            {g.sources.map((src) => `facture ${src.invoice_ordinal}, ligne ${src.line_ordinal}`).join(" · ")}
                            {g.origin_country && ` · origine ${g.origin_country}`}
                          </div>
                        </td>
                        <td>{g.sources.map((src) => src.assigned_value).filter(Boolean).join(" + ") || "—"}</td>
                        <td className="code">{s.code || "—"}</td>
                        <td><Chip tone={s.tone}>{s.label}</Chip></td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}
        </section>
        <section className="card side-panel" aria-label="Proposition tarifaire">
          <h2 className="card-title">Proposition tarifaire</h2>
          {selected ? (
            <GoodsCard key={selected.id} goods={selected} revision={revision} editions={editions} editable={editable} act={act} />
          ) : (
            <p className="empty">Sélectionnez une marchandise.</p>
          )}
          <p className="note-amber small">
            Droits et taxes : non affichés. Les taux du tarif 2016 ne sont pas vérifiés ; le calcul arrivera avec le moteur de calcul.
          </p>
        </section>
      </div>
    </>
  );
}

function GoodsCard({
  goods,
  revision,
  editions,
  editable,
  act,
}: {
  goods: GoodsLine;
  revision: Revision;
  editions: EditionOption[];
  editable: boolean;
  act: Act;
}) {
  const [edition, setEdition] = useState(revision.target_edition?.id ?? editions[0]?.id ?? "");
  const [reason, setReason] = useState("");
  const [subdivision, setSubdivision] = useState("");
  const check: CodeCheck | null = goods.latest_check;
  const decision = goods.decision;
  const subdivisions = check?.findings.find((f) => f.code === "SUBDIVISIONS_REQUIRED")?.details?.subdivisions ?? [];

  useEffect(() => {
    if (!edition && (revision.target_edition?.id || editions[0]?.id)) setEdition(revision.target_edition?.id ?? editions[0].id);
  }, [edition, editions, revision.target_edition]);

  function decide(action: "confirm" | "complete") {
    if (!check) return;
    void act(async () => {
      await api.decide(goods.id, {
        action,
        code_check_id: check.id,
        node_id: action === "complete" ? subdivision : null,
        reason,
        goods_line_version: goods.row_version,
      });
      setReason("");
    });
  }

  return (
    <div aria-label={`Marchandise ${goods.ordinal}`}>
      <div className="goods-head">
        <span className="goods-icon"><Icon name="box" size={26} /></span>
        <div>
          <strong>{goods.description || <em className="muted">désignation ?</em>}</strong>
          <div className="muted small">
            Marchandise {goods.ordinal} · issue de {goods.sources.map((s) => `facture ${s.invoice_ordinal} ligne ${s.line_ordinal}`).join(", ")} · origine{" "}
            {goods.origin_country || "?"}
          </div>
        </div>
      </div>
      {decision && (
        <div className={decision.is_current ? "decision" : "note-amber"}>
          <div className="decision-code">
            <span className="code big-code">{decision.selected_code_display}</span>
            <Chip tone={decision.is_current ? "green" : "red"}>{decision.is_current ? "Validé" : "À revoir"}</Chip>
          </div>
          <p className="small">
            {decision.action_label} : {decision.label} ({decision.edition.label}) par {decision.actor.email} le{" "}
            {new Date(decision.at).toLocaleString("fr-FR")}. Motif : {decision.reason}
            {!decision.is_current && " — Données modifiées depuis : décision à revoir."}
          </p>
          <p className="small muted">{decision.note}</p>
        </div>
      )}
      {editable && (
        <div className="check-row">
          <label>
            Contrôler contre
            <select value={edition} onChange={(e) => setEdition(e.target.value)}>
              {editions.map((e) => (
                <option key={e.id} value={e.id}>{e.label}</option>
              ))}
            </select>
          </label>
          <button type="button" className="btn-secondary" disabled={!edition} onClick={() => void act(() => api.checkCode(goods.id, edition))}>
            Contrôler le code présent
          </button>
        </div>
      )}
      {check && (
        <div className="check-result" aria-label="Résultat du contrôle">
          <div className="check-title">
            <strong>{check.recognition_label}</strong>
            <span className="muted small">{CONFIRMATION[check.human_confirmation]}</span>
          </div>
          {check.node ? (
            <>
              <span className="code big-code">{check.node.code_display}</span>
              <p className="small">{check.node.full_path}</p>
            </>
          ) : (
            check.observed_code && <span className="code big-code">{check.observed_code}</span>
          )}
          {check.observed_code && (
            <p className="muted small">
              Lu « {check.observed_code} » dans « {check.observed_field} » · {check.target_edition_label}
            </p>
          )}
          <ul className="finding-list small">
            {check.findings.map((f) => (
              <li key={f.code + f.message} className={f.severity === "info" ? "muted" : undefined}>
                {f.message}
              </li>
            ))}
          </ul>
          {editable && check.is_current && check.recognition_status === "recognized" && check.human_confirmation === "pending" && (
            <form className="decide-form" onSubmit={(e) => { e.preventDefault(); decide("confirm"); }}>
              <label>
                Motif de la confirmation
                <input required value={reason} onChange={(e) => setReason(e.target.value)} />
              </label>
              <button type="submit" className="btn-primary btn-block">
                <Icon name="check" /> Confirmer le code
              </button>
            </form>
          )}
          {editable && check.is_current && check.recognition_status === "incomplete" && subdivisions.length > 0 && (
            <form className="decide-form" onSubmit={(e) => { e.preventDefault(); decide("complete"); }}>
              <label>
                Subdivision
                <select required value={subdivision} onChange={(e) => setSubdivision(e.target.value)}>
                  <option value="">Choisir…</option>
                  {subdivisions.map((s) => (
                    <option key={s.id} value={s.id}>{s.code_display} {s.label}</option>
                  ))}
                </select>
              </label>
              <label>
                Motif
                <input required value={reason} onChange={(e) => setReason(e.target.value)} />
              </label>
              <button type="submit" className="btn-primary btn-block">Compléter le code</button>
            </form>
          )}
        </div>
      )}
      {(editable || goods.latest_check) && (
        <details open={Boolean(check && check.recognition_status !== "recognized")} className="proposals-box">
          <summary>Autres codes possibles (recherche dans le tarif, sans IA)</summary>
          <ProposalsPanel goods={goods} editionId={edition} editable={editable} act={act} />
        </details>
      )}
    </div>
  );
}

// ---- Calculs, validation, export : ce qui existe, et ce qui manque encore -----------------------

function Calculation({ revision, go }: { revision: Revision; go: (tab: string) => void }) {
  const totals = revision.invoices.map((i) => ({
    id: i.id,
    label: `Facture ${i.ordinal}${i.invoice_number ? ` (${i.invoice_number})` : ""}`,
    value: i.declared_total ? `${i.declared_total} ${i.currency}` : null,
    incoterm: i.incoterm,
  }));
  return (
    <section className="card" aria-labelledby="calc-title">
      <h2 id="calc-title" className="card-title">Détail du calcul en douane</h2>
      <div className="stats stats-4">
        <StatCard
          icon="box"
          tone="green"
          label="Valeur marchandise"
          value={totals.filter((t) => t.value).map((t) => t.value).join(" + ") || "inconnue"}
          hint="total imprimé des factures"
        />
        <StatCard icon="arrowRight" tone="blue" label="Transport (fret)" value="inconnu" hint="à saisir avec le calcul" />
        <StatCard icon="shield" tone="blue" label="Assurance" value="inconnue" hint="à saisir avec le calcul" />
        <StatCard icon="calculator" tone="gray" label="Base de calcul" value="non calculée" />
      </div>
      <div className="note-amber">
        <p><strong>Le moteur de calcul n'est pas encore construit.</strong></p>
        <p className="small">
          Aucun droit ni taxe n'est affiché : les taux du classeur 2016 sont des copies d'un fichier « 2015 » absent et ne sont pas
          vérifiés. Le calcul arrivera avec des règles datées et sourcées, d'abord marquées « démonstration ».
        </p>
      </div>
      {totals.length > 0 && (
        <table className="data compact">
          <thead>
            <tr><th scope="col">Facture</th><th scope="col">Total imprimé</th><th scope="col">Incoterm</th></tr>
          </thead>
          <tbody>
            {totals.map((t) => (
              <tr key={t.id}>
                <td>{t.label}</td>
                <td>{t.value ?? <em className="muted">inconnu</em>}</td>
                <td>{t.incoterm || <em className="muted">inconnu</em>}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
      <button type="button" className="link-arrow" onClick={() => go("controles")}>
        Voir les contrôles du dossier <Icon name="arrowRight" size={16} />
      </button>
    </section>
  );
}

function Finalisation({ detail, kind, go }: { detail: CaseDetail; kind: "validation" | "export"; go: (tab: string) => void }) {
  const rev = detail.revision;
  const docs = rev.documents.filter((d) => !d.replaced_by_id).length;
  const goods = rev.goods_lines.length;
  const decided = rev.goods_lines.filter((g) => g.decision?.is_current).length;
  const blocking = controlItems(detail).filter((c) => c.severity === "blocking").length;
  const rows: { ok: boolean | null; title: string; detail: string; value: string; tab: string }[] = [
    { ok: docs > 0, title: "Documents présents", detail: "Au moins une pièce rattachée au dossier.", value: String(docs), tab: "documents" },
    { ok: goods > 0 && decided === goods, title: "Classifications validées", detail: "Chaque marchandise a un code confirmé et motivé.", value: `${decided} / ${goods}`, tab: "marchandises" },
    { ok: null, title: "Calculs", detail: "Le moteur de calcul n'existe pas encore.", value: "à venir", tab: "calculs" },
    { ok: blocking === 0, title: "Contrôles résolus", detail: "Aucun point bloquant.", value: blocking ? `${blocking} bloquant(s)` : "aucun bloquant", tab: "controles" },
    { ok: rev.state === "validated", title: "Validation responsable", detail: "Validation interne par un validateur de la société.", value: rev.state_label, tab: "validation" },
  ];
  return (
    <div className="grid-2-1">
      <section className="card" aria-labelledby="final-title">
        <h2 id="final-title" className="card-title">{kind === "export" ? "Prérequis pour l'export" : "Prérequis pour la validation"}</h2>
        <ul className="prereq">
          {rows.map((r) => (
            <li key={r.title}>
              <span className={`prereq-icon ${r.ok === null ? "later" : r.ok ? "ok" : "ko"}`}>
                <Icon name={r.ok === null ? "clock" : r.ok ? "check" : "alert"} size={16} />
              </span>
              <span>
                <strong>{r.title}</strong>
                <small>{r.detail}</small>
              </span>
              <span className="prereq-value">{r.value}</span>
              <button type="button" className="link-arrow" onClick={() => go(r.tab)}>
                Voir <Icon name="arrowRight" size={14} />
              </button>
            </li>
          ))}
        </ul>
      </section>
      <section className="card">
        <h2 className="card-title">{kind === "export" ? "Actions d'export" : "Actions de validation"}</h2>
        <button type="button" className="btn-primary btn-block" disabled>
          {kind === "export" ? "Générer l'export" : "Envoyer en validation"}
        </button>
        <p className="muted small">
          {kind === "export"
            ? "L'export (récapitulatif PDF, détail Excel) arrive dans une prochaine version. Le format du logiciel douanier (SYDONIA ou autre) reste à confirmer : aucun fichier « importable directement » n'est promis avant."
            : "La soumission et l'approbation arrivent dans une prochaine version."}
        </p>
        <p className="note-blue small">« Validé » signifie validé en interne par votre société, jamais accepté par la Douane.</p>
      </section>
    </div>
  );
}

// ---- Historique --------------------------------------------------------------------------------

function History({ caseId, version }: { caseId: string; version: number }) {
  const [events, setEvents] = useState<AuditEntry[] | null>(null);
  useEffect(() => {
    api.caseAudit(caseId).then((r) => setEvents(r.results), () => setEvents([]));
  }, [caseId, version]);
  return (
    <section className="card" aria-labelledby="history-title">
      <h2 id="history-title" className="card-title">Historique du dossier ({events?.length ?? 0})</h2>
      {events === null ? (
        <p className="muted">Chargement…</p>
      ) : events.length === 0 ? (
        <p className="empty">Aucun événement.</p>
      ) : (
        <ol className="timeline">
          {events.map((e) => (
            <li key={e.id}>
              <span className="activity-icon"><Icon name={eventIcon(e.event_type)} size={16} /></span>
              <span>
                <strong>{eventLabel(e.event_type)}</strong>
                <small>{e.actor ?? "système"}</small>
              </span>
              <time dateTime={e.at}>{fmtDateTime(e.at)}</time>
            </li>
          ))}
        </ol>
      )}
    </section>
  );
}
