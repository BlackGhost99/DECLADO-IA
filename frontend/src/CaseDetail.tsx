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
  type NodeDetail,
  type Preview,
  type Revision,
} from "./api";
import { Controls, controlItems } from "./Controls";
import { Divergences, ExtractionControls, Flags, LineEditor, OriginBadge, TotalsPanel } from "./Extraction";
import { Icon, type IconName } from "./Icon";
import { PdfViewer, type Highlight } from "./PdfViewer";
import { ProposalsPanel } from "./Proposals";
import { navigate, rememberCase } from "./router";
import {
  caseSteps,
  Chip,
  errorText,
  eventIcon,
  eventLabel,
  fmtDate,
  addDecimals,
  fmtAmount,
  fmtDateTime,
  fmtQty,
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

/** Titre et sous-titre de chaque onglet, comme sur les écrans de référence. */
const TAB_HEADINGS: Record<string, (ref: string) => { title: string; subtitle: string }> = {
  apercu: () => ({ title: "Dossier", subtitle: "Informations du dossier, manques à compléter et prochaine étape." }),
  documents: () => ({ title: "Dossier", subtitle: "Les pièces reçues, leur aperçu et les données lues avec leur source." }),
  donnees: (r) => ({ title: `Données extraites du dossier ${r}`, subtitle: "Chaque valeur dit si elle a été lue ou saisie ; une correction garde l'ancienne valeur et son motif." }),
  marchandises: (r) => ({ title: `Marchandises du dossier ${r}`, subtitle: "Préparez les marchandises, contrôlez leur code et confirmez-le avec un motif." }),
  controles: (r) => ({ title: `Contrôles du dossier ${r}`, subtitle: "Vérifiez la conformité du dossier, identifiez les anomalies et suivez leur résolution." }),
  calculs: () => ({ title: "Calculs / Contrôles / Validation", subtitle: "Vérifiez les montants, contrôlez la conformité et validez le dossier pour export." }),
  validation: (r) => ({ title: `Validation du dossier ${r}`, subtitle: "Validation interne par un responsable de votre société, jamais acceptation par la Douane." }),
  export: (r) => ({ title: `Préparer l'export du dossier ${r}`, subtitle: "Générez les fichiers d'export et téléchargez les documents finaux du dossier." }),
  historique: (r) => ({ title: `Historique du dossier ${r}`, subtitle: "Toutes les actions, avec leur auteur et leur date. Rien n'est effacé." }),
};

/** Menu « Actions » de l'en-tête : seulement des actions qui existent. */
function CaseActions({ canTake, onTake, go }: { canTake: boolean; onTake: () => void; go: (tab: string) => void }) {
  const [open, setOpen] = useState(false);
  const pick = (f: () => void) => () => {
    setOpen(false);
    f();
  };
  return (
    <div className="menu-wrap">
      <button type="button" className="btn-secondary btn-small-pad" aria-haspopup="menu" aria-expanded={open} onClick={() => setOpen(!open)}>
        Actions <Icon name="chevronDown" size={16} />
      </button>
      {open && (
        <ul className="menu menu-right" role="menu" aria-label="Actions du dossier">
          {canTake && <li role="menuitem"><button type="button" onClick={pick(onTake)}><Icon name="user" size={16} /> Prendre le dossier</button></li>}
          <li role="menuitem"><button type="button" onClick={pick(() => go("apercu"))}><Icon name="eye" size={16} /> Aperçu du dossier</button></li>
          <li role="menuitem"><button type="button" onClick={pick(() => go("documents"))}><Icon name="upload" size={16} /> Ajouter un document</button></li>
          <li role="menuitem"><button type="button" onClick={pick(() => go("donnees"))}><Icon name="edit" size={16} /> Données extraites</button></li>
          <li role="menuitem"><button type="button" onClick={pick(() => go("controles"))}><Icon name="checkCircle" size={16} /> Voir les contrôles</button></li>
          <li role="menuitem"><button type="button" onClick={pick(() => go("historique"))}><Icon name="history" size={16} /> Voir l'historique</button></li>
        </ul>
      )}
    </div>
  );
}

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
  const tabInfo = CASE_TABS.find((t) => t.key === tab);
  const heading = TAB_HEADINGS[tab]?.(detail.reference) ?? TAB_HEADINGS.apercu(detail.reference);

  return (
    <div className={`case-detail case-detail-${tab}`}>
      <nav className="breadcrumb" aria-label="Fil d'Ariane">
        <button type="button" className="link" onClick={() => navigate("/dossiers")}>
          <Icon name="arrowLeft" size={16} /> Mes dossiers
        </button>
        <Icon name="chevronRight" size={14} />
        <button type="button" className="link code" onClick={() => go("apercu")}>{detail.reference}</button>
        {tabInfo && tab !== "apercu" && (
          <>
            <Icon name="chevronRight" size={14} />
            <span>{tabInfo.label}</span>
          </>
        )}
      </nav>
      <div className="case-header">
        <div className="case-heading">
          <h1 id="case-title">
            {heading.title}
            {heading.title === "Dossier" && (
              <>
                {" "}<span className="code">{detail.reference}</span>
                {detail.importer && <> — {detail.importer.name}</>}
              </>
            )}
          </h1>
          <p className="page-subtitle">{heading.subtitle}</p>
          <p className="case-meta">
            <span><Icon name="file" size={16} /> {detail.title || "Importation"}</span>
            <span><Icon name="layers" size={16} /> {rev.mode_label}</span>
            <span><Icon name="mapPin" size={16} /> {rev.territory === "GA" ? "Gabon" : rev.territory || "territoire ?"}</span>
            <span><Icon name="user" size={16} /> Créé le {fmtDate(detail.created_at)} par {personName(detail.created_by)}</span>
          </p>
        </div>
        <aside className="case-aside" aria-label="Résumé du dossier">
          <StateChip state={rev.state} label={rev.state_label} />
          <strong className="code">{detail.reference}</strong>
          <span>{detail.importer?.name ?? <em className="muted">importateur à renseigner</em>}</span>
          <small>
            Révision {rev.revision_no} · Agent : {personName(detail.assigned_to) || "non affecté"}
          </small>
          <CaseActions
            canTake={canEdit && !detail.assigned_to}
            onTake={() => act(() => api.assignCase(detail.id, me.id, detail.row_version))}
            go={go}
          />
        </aside>
      </div>
      {error && <p role="alert" className="error">⚠ {error}</p>}

      {/* La barre latérale sert de navigation entre les sections ; la frise ne reste que sur l'aperçu et l'export. */}
      {(tab === "apercu" || tab === "export") && (
        <section className={tab === "export" ? "stepper-card export-stepper" : "card stepper-card"} aria-label="Étapes du dossier">
          <Stepper steps={steps} onSelect={go} />
        </section>
      )}

      <div>
        {tab === "apercu" && (
          <Overview detail={detail} editions={editions} editable={editable} act={act} go={go} />
        )}
        {tab === "documents" && <DocumentsTab caseId={detail.id} revision={rev} editable={editable} onChange={reload} />}
        {tab === "donnees" && <Invoices revision={rev} editable={editable} act={act} />}
        {tab === "marchandises" && <GoodsTab revision={rev} editions={editions} editable={editable} act={act} />}
        {tab === "controles" && <Controls detail={detail} go={go} />}
        {tab === "calculs" && <Calculation detail={detail} go={go} />}
        {tab === "validation" && <ValidationPage detail={detail} go={go} />}
        {tab === "export" && <ExportPage detail={detail} go={go} />}
        {tab === "historique" && <History caseId={detail.id} version={tick} />}
      </div>
    </div>
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
  const [highlight, setHighlight] = useState<Highlight | null>(null);
  const selected = revision.documents.find((d) => d.id === selectedId) ?? active[0] ?? null;
  const present = new Set(active.map((d) => d.usage));
  const missing = EXPECTED.filter(([usage]) => !present.has(usage));

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
                  onClick={() => { setSelectedId(link.id); setHighlight(null); }}
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
                  {link.latest_extraction?.status === "succeeded" && <Icon name="checkCircle" size={16} className="doc-ok" />}
                </button>
              </li>
            ))}
          </ul>
        )}
        {missing.length > 0 && (
          <>
            <h3 className="small-heading">Pièces attendues</h3>
            <ul className="doc-items">
              {missing.map(([usage, label, hint]) => (
                <li key={usage} className="doc-missing">
                  <span className="doc-type doc-none"><Icon name="file" size={16} /></span>
                  <span className="doc-text">
                    <strong>{label}</strong>
                    <small>{hint}</small>
                  </span>
                  <Chip tone="gray">Manquant</Chip>
                </li>
              ))}
            </ul>
          </>
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
        {selected ? <Viewer link={selected} highlight={highlight} /> : <p className="empty">Ajoutez une pièce pour l'afficher ici.</p>}
      </section>

      <section className="card" aria-labelledby="extracted-title">
        {selected ? (
          <ExtractedPanel link={selected} revision={revision} editable={editable} onChange={onChange} onSource={setHighlight} />
        ) : (
          <>
            <h2 id="extracted-title" className="card-title">Données extraites</h2>
            <p className="empty">Aucune pièce sélectionnée.</p>
          </>
        )}
      </section>
    </div>
  );
}

/** Pièces habituelles d'un dossier d'importation : celles qui manquent sont montrées, jamais inventées. */
const EXPECTED: [string, string, string][] = [
  ["invoice", "Facture commerciale", "valeur, devise, lignes"],
  ["transport", "Connaissement (B/L) ou LTA", "transport, poids, colis"],
  ["packing_list", "Liste de colisage", "poids et nombre de colis"],
  ["origin", "Certificat d'origine", "pays d'origine"],
];

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

function Viewer({ link, highlight }: { link: CaseDocument; highlight: Highlight | null }) {
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

  if (preview?.kind === "pdf") {
    return <PdfViewer url={preview.url} name={link.document.original_name} highlight={highlight} onDownload={() => void download()} />;
  }

  return (
    <>
      <div className="viewer-bar">
        <span className="viewer-name">{link.document.original_name}</span>
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

function SourceLink({ source, onSource }: { source?: FieldSource; onSource: (h: Highlight) => void }) {
  const span = source?.span;
  if (!span) return null;
  if (span.sheet) return <span className="source-link">Source : {span.sheet}!{span.cell_range}</span>;
  if (span.page == null) return null;
  return (
    <button type="button" className="source-link" onClick={() => onSource({ page: span.page!, bbox: span.bbox })} title={span.excerpt ? `Texte lu : « ${span.excerpt} »` : undefined}>
      Voir la source (p. {span.page}) <Icon name="external" size={13} />
    </button>
  );
}

function ExtractedPanel({
  link,
  revision,
  editable,
  onChange,
  onSource,
}: {
  link: CaseDocument;
  revision: Revision;
  editable: boolean;
  onChange: () => Promise<void>;
  onSource: (h: Highlight) => void;
}) {
  const invoiceId = link.latest_extraction?.invoice_id;
  const invoice: Invoice | undefined =
    revision.invoices.find((i) => i.id === invoiceId) ?? revision.invoices.find((i) => i.document_id === link.id);
  const canRead = link.usage === "invoice" || Boolean(link.latest_extraction);
  const run = link.latest_extraction;
  const done = run?.status === "succeeded";

  return (
    <>
      <div className="card-head">
        <h2 id="extracted-title" className="card-title">{link.usage === "invoice" ? "Données extraites de la facture" : `Données extraites · ${link.usage_label}`}</h2>
        {run && (
          <Chip tone={done ? "green" : run.status === "failed" ? "red" : "blue"} icon={done ? "checkCircle" : run.status === "failed" ? "alert" : "clock"}>
            {done ? "Extraction terminée" : run.status_label}
          </Chip>
        )}
      </div>
      {done && run.finished_at && (
        <p className="muted small processed">
          <Icon name="checkCircle" size={16} /> Traité le {fmtDateTime(run.finished_at)} · lecture {run.attempt} ·{" "}
          {run.parser === "ocr" ? "OCR" : "texte du PDF"}
          {run.warnings.length > 0 && ` · ${run.warnings.length} avertissement(s)`}
        </p>
      )}
      {canRead ? (
        done ? (
          <details className="read-options small">
            <summary>Options de lecture</summary>
            <ExtractionControls link={link} editable={editable} onDone={onChange} />
          </details>
        ) : (
          <ExtractionControls link={link} editable={editable} onDone={onChange} />
        )
      ) : (
        <p className="muted small">La lecture automatique concerne les factures. Cette pièce est conservée telle quelle.</p>
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
                ["declared_total", "Montant total", fmtAmount(invoice.declared_total)],
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
                    <SourceLink source={invoice.field_sources?.[field]} onSource={onSource} />
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
                  <th scope="col">Qté</th><th scope="col" className="num">PU</th><th scope="col" className="num">Montant</th><th scope="col">Statut</th>
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
                      <td className="nowrap">{fmtQty(ln.quantity) || "?"} {ln.unit}</td>
                      <td className="num">{ln.unit_price ? fmtAmount(ln.unit_price) : "—"}</td>
                      <td className="num">{ln.amount ? fmtAmount(ln.amount) : <em className="muted">inconnu</em>}</td>
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

type LineInfo = { quantity: string | null; unit: string; amount: string | null; currency: string; reference: string };

/** Quantité, valeur et devise d'une marchandise, reprises des lignes de facture d'où elle vient. */
function goodsFigures(g: GoodsLine, lines: Map<string, LineInfo>) {
  const src = g.sources.map((s) => ({ s, line: lines.get(s.invoice_line_id) }));
  const qty = src.map(({ s, line }) => fmtQty(s.assigned_quantity ?? line?.quantity)).filter(Boolean);
  const value = src.map(({ s, line }) => fmtAmount(s.assigned_value ?? line?.amount)).filter(Boolean);
  const currency = src.find(({ line }) => line?.currency)?.line?.currency ?? "";
  const unit = src.find(({ line }) => line?.unit)?.line?.unit ?? "";
  const reference = src.map(({ line }) => line?.reference).filter(Boolean).join(", ");
  return { qty: qty.join(" + "), unit, value: value.join(" + "), currency, reference };
}

function lineIndex(revision: Revision): Map<string, LineInfo> {
  const map = new Map<string, LineInfo>();
  for (const inv of revision.invoices)
    for (const ln of inv.lines)
      map.set(ln.id, { quantity: ln.quantity, unit: ln.unit, amount: ln.amount, currency: inv.currency, reference: ln.source_reference });
  return map;
}

const STATUS_FILTERS = ["Tous", "Validé", "À valider", "À vérifier", "À contrôler", "À recontrôler", "À revoir"];

function GoodsTab({ revision, editions, editable, act }: { revision: Revision; editions: EditionOption[]; editable: boolean; act: Act }) {
  const goods = revision.goods_lines;
  const lines = lineIndex(revision);
  const [selectedId, setSelectedId] = useState<string | null>(goods[0]?.id ?? null);
  const [checked, setChecked] = useState<Set<string>>(new Set());
  const [search, setSearch] = useState("");
  const [filter, setFilter] = useState("Tous");
  const selected = goods.find((g) => g.id === selectedId) ?? goods[0] ?? null;
  const freeInvoices = revision.invoices.filter((i) => i.lines.some((ln) => ln.goods_line_ids.length === 0));
  const freeCount = freeInvoices.reduce((n, i) => n + i.lines.filter((ln) => ln.goods_line_ids.length === 0).length, 0);
  const statuses = new Map(goods.map((g) => [g.id, goodsStatus(g)]));
  const all = [...statuses.values()];
  const validated = all.filter((s) => s.label === "Validé").length;
  const toValidate = all.filter((s) => s.label === "À valider").length;
  const toCheck = all.filter((s) => s.tone === "amber" || s.tone === "red").length - toValidate;
  const noCheck = all.filter((s) => s.label === "À contrôler").length;
  const editionId = revision.target_edition?.id ?? editions[0]?.id ?? "";
  const shown = goods.filter((g) => {
    const s = statuses.get(g.id)!;
    if (filter !== "Tous" && s.label !== filter) return false;
    const q = search.trim().toLowerCase();
    return !q || g.description.toLowerCase().includes(q) || s.code.includes(q);
  });
  const targets = checked.size ? goods.filter((g) => checked.has(g.id)) : goods;

  function toggle(id: string) {
    const next = new Set(checked);
    if (next.has(id)) next.delete(id);
    else next.add(id);
    setChecked(next);
  }

  return (
    <>
      {editable && (
        <div className="action-bar">
          {freeCount > 0 && (
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
          <button
            type="button"
            className="btn-secondary"
            disabled={!goods.length || !editionId}
            onClick={() => void act(async () => {
              for (const g of targets) await api.checkCode(g.id, editionId);
            })}
          >
            <Icon name="search" /> Contrôler {checked.size ? `la sélection (${checked.size})` : "tous les codes"}
          </button>
          <button type="button" className="btn-secondary" onClick={() => navigate("/recherche")}>
            <Icon name="book" /> Consulter le tarif
          </button>
        </div>
      )}
      <div className="split-panel">
        <div>
          <section className="card" aria-labelledby="goods-title">
            <div className="card-head">
              <h2 id="goods-title" className="card-title">Liste des marchandises ({goods.length})</h2>
              <div className="table-tools">
                <label className="search-mini">
                  <Icon name="search" size={16} />
                  <input aria-label="Rechercher une marchandise" placeholder="Rechercher un article…" value={search} onChange={(e) => setSearch(e.target.value)} />
                </label>
                <label className="filter-mini">
                  <Icon name="filter" size={16} />
                  <select aria-label="Filtrer par statut" value={filter} onChange={(e) => setFilter(e.target.value)}>
                    {STATUS_FILTERS.map((f) => (
                      <option key={f}>{f}</option>
                    ))}
                  </select>
                </label>
              </div>
            </div>
            <p className="muted small">
              Un code retrouvé dans le tarif n'est pas un classement validé : il attend votre confirmation motivée.
            </p>
            {goods.length === 0 ? (
              <p className="empty">
                Aucune marchandise. {freeCount ? `${freeCount} ligne(s) de facture peuvent être préparées.` : "Elles se préparent à partir des lignes de facture."}
              </p>
            ) : (
              <div className="table-wrap">
                <table className="data selectable">
                  <thead>
                    <tr>
                      <th scope="col">
                        <input
                          type="checkbox"
                          aria-label="Tout sélectionner"
                          checked={checked.size === goods.length && goods.length > 0}
                          onChange={(e) => setChecked(e.target.checked ? new Set(goods.map((g) => g.id)) : new Set())}
                        />
                      </th>
                      <th scope="col">#</th><th scope="col">Description</th><th scope="col">Quantité</th>
                      <th scope="col">Valeur</th><th scope="col">Code</th><th scope="col">Statut</th>
                    </tr>
                  </thead>
                  <tbody>
                    {shown.map((g) => {
                      const s = statuses.get(g.id)!;
                      const f = goodsFigures(g, lines);
                      return (
                        <tr key={g.id} className={selected?.id === g.id ? "selected" : undefined} onClick={() => setSelectedId(g.id)}>
                          <td onClick={(e) => e.stopPropagation()}>
                            <input type="checkbox" aria-label={`Sélectionner la marchandise ${g.ordinal}`} checked={checked.has(g.id)} onChange={() => toggle(g.id)} />
                          </td>
                          <td>{g.ordinal}</td>
                          <td>
                            <div className="goods-cell">
                              <span className="goods-thumb"><Icon name="box" size={20} /></span>
                              <span>
                                <button type="button" className="row-button" onClick={() => setSelectedId(g.id)}>
                                  {g.description || <em className="muted">désignation ?</em>}
                                </button>
                                <span className="block muted small">
                                  {g.sources.map((src) => `facture ${src.invoice_ordinal}, ligne ${src.line_ordinal}`).join(" · ")}
                                  {f.reference && ` · réf. ${f.reference}`}
                                  {` · origine ${g.origin_country || "?"}`}
                                </span>
                              </span>
                            </div>
                          </td>
                          <td className="nowrap">{f.qty ? <>{f.qty}<span className="block muted small">{f.unit || "unité ?"}</span></> : <em className="muted">inconnue</em>}</td>
                          <td className="nowrap">{f.value ? <>{f.value}<span className="block muted small">{f.currency}</span></> : <em className="muted">inconnue</em>}</td>
                          <td className="code nowrap">{s.code || "—"}</td>
                          <td><Chip tone={s.tone}>{s.label}</Chip></td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            )}
          </section>
          <section className="card" aria-labelledby="goods-summary">
            <h2 id="goods-summary" className="card-title">Résumé de la classification</h2>
            <div className="stats stats-4 flat">
              <StatCard icon="box" tone="green" label="Marchandises" value={goods.length} hint={`${validated} validée(s) · ${freeCount} ligne(s) à préparer`} />
              <StatCard icon="search" tone="blue" label="Codes à contrôler" value={noCheck} hint="aucun contrôle contre le tarif" />
              <StatCard icon="alert" tone="amber" label="À vérifier ou valider" value={toCheck + toValidate} hint={`${toValidate} code(s) retrouvé(s) à confirmer`} />
              <StatCard icon="checkCircle" tone="green" label="Codes validés" value={`${validated} / ${goods.length}`} hint="confirmés avec un motif" />
            </div>
          </section>
        </div>
        <section className="card side-panel" aria-label="Proposition tarifaire">
          <h2 className="card-title">Proposition tarifaire</h2>
          {selected ? (
            <GoodsCard key={selected.id} goods={selected} revision={revision} lines={lines} editions={editions} editable={editable} act={act} />
          ) : (
            <p className="empty">Sélectionnez une marchandise.</p>
          )}
        </section>
      </div>
    </>
  );
}

/** Taux bruts lus dans le tarif pour le code contrôlé : affichés tels quels, jamais appliqués. */
function TariffRates({ nodeId }: { nodeId: string }) {
  const [detail, setDetail] = useState<NodeDetail | null>(null);
  useEffect(() => {
    api.tariffNode(nodeId).then(setDetail, () => setDetail(null));
  }, [nodeId]);
  if (!detail) return null;
  const items = detail.rate_observations.items;
  return (
    <div className="rates">
      <div className="card-head">
        <h3>Droits et taxes lus dans le tarif</h3>
        <Chip tone="amber">non vérifiés</Chip>
      </div>
      {items.length === 0 ? (
        <p className="muted small">Aucune colonne de taux dans cette édition.</p>
      ) : (
        <table className="data compact">
          <tbody>
            {items.map((r) => (
              <tr key={r.column}>
                <td>{r.column}</td>
                <td className="num">{r.raw_value || <em className="muted">vide (inconnu)</em>}</td>
              </tr>
            ))}
            <tr className="total-row">
              <td>Total estimé</td>
              <td className="num">non calculé</td>
            </tr>
          </tbody>
        </table>
      )}
      <p className="muted small">{detail.rate_observations.warning}</p>
    </div>
  );
}

function GoodsCard({
  goods,
  revision,
  lines,
  editions,
  editable,
  act,
}: {
  goods: GoodsLine;
  revision: Revision;
  lines: Map<string, LineInfo>;
  editions: EditionOption[];
  editable: boolean;
  act: Act;
}) {
  const [edition, setEdition] = useState(revision.target_edition?.id ?? editions[0]?.id ?? "");
  const [reason, setReason] = useState("");
  const [subdivision, setSubdivision] = useState("");
  const [copied, setCopied] = useState(false);
  const check: CodeCheck | null = goods.latest_check;
  const decision = goods.decision;
  const subdivisions = check?.findings.find((f) => f.code === "SUBDIVISIONS_REQUIRED")?.details?.subdivisions ?? [];
  const f = goodsFigures(goods, lines);
  const status = goodsStatus(goods);
  const shownCode = decision?.selected_code_display ?? check?.node?.code_display ?? check?.observed_code ?? "";

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

  function copy() {
    void navigator.clipboard?.writeText(shownCode).then(() => setCopied(true), () => undefined);
  }

  return (
    <div aria-label={`Marchandise ${goods.ordinal}`}>
      <div className="goods-head">
        <span className="goods-icon"><Icon name="box" size={30} /></span>
        <div>
          <strong>{goods.description || <em className="muted">désignation ?</em>}</strong>
          <dl className="mini-facts">
            <div><dt>Quantité</dt><dd>{f.qty ? `${f.qty} ${f.unit}` : "inconnue"}</dd></div>
            <div><dt>Valeur</dt><dd>{f.value ? `${f.value} ${f.currency}` : "inconnue"}</dd></div>
            <div><dt>Origine</dt><dd>{goods.origin_country || "inconnue"}</dd></div>
            <div><dt>Source</dt><dd>{goods.sources.map((s) => `facture ${s.invoice_ordinal}, ligne ${s.line_ordinal}`).join(", ")}</dd></div>
          </dl>
        </div>
      </div>

      <div className="code-box">
        <div className="card-head">
          <span className="muted small">{decision ? "Code validé" : check?.node ? "Code retrouvé dans le tarif" : "Code présent"}</span>
          <Chip tone={status.tone}>{status.label}</Chip>
        </div>
        {shownCode ? (
          <div className="code-line">
            <span className="code big-code">{shownCode}</span>
            <button type="button" className="icon-button" onClick={copy} title="Copier le code">
              <Icon name="copy" size={18} />
              <span className="visually-hidden">Copier le code</span>
            </button>
            {copied && <span className="muted small">copié</span>}
          </div>
        ) : (
          <p className="big-line muted">Aucun code douanier</p>
        )}
        {check?.node && <p className="small">{check.node.full_path}</p>}
        {decision && (
          <p className="small">
            {decision.action_label} ({decision.edition.label}) par {decision.actor.email} le {new Date(decision.at).toLocaleString("fr-FR")}.
            Motif : {decision.reason}
            {!decision.is_current && " Données modifiées depuis : décision à revoir."}
          </p>
        )}
      </div>

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
          {check.observed_code && (
            <p className="muted small">
              Lu « {check.observed_code} » dans « {check.observed_field} » · {check.target_edition_label} · contrôlé le {fmtDateTime(check.checked_at)}
            </p>
          )}
          <h3>Points relevés</h3>
          <ul className="check-list small">
            {check.findings.map((x) => (
              <li key={x.code + x.message} className={`sev-${x.severity}`}>
                <Icon name={x.severity === "info" ? "info" : x.severity === "error" || x.severity === "blocking" ? "alert" : "checkCircle"} size={16} />
                {x.message}
              </li>
            ))}
          </ul>
          <p className="note-amber small">
            Un code retrouvé dans le tarif doit être confirmé par un agent, avec un motif. Vérifiez la désignation et les notes avant de confirmer.
          </p>
          {editable && check.is_current && check.recognition_status === "recognized" && check.human_confirmation === "pending" && (
            <form className="decide-form" onSubmit={(e) => { e.preventDefault(); decide("confirm"); }}>
              <label>
                Motif de la confirmation
                <input required value={reason} onChange={(e) => setReason(e.target.value)} placeholder="ex. conforme à la désignation de la facture" />
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
      <div className="actions-row two">
        <button type="button" className="btn-secondary" onClick={() => document.getElementById(`proposals-${goods.id}`)?.setAttribute("open", "")}>
          <Icon name="edit" size={18} /> Changer le code
        </button>
        <button type="button" className="btn-secondary" onClick={() => navigate(`/recherche?q=${encodeURIComponent(shownCode || goods.description)}`)}>
          <Icon name="external" size={18} /> Consulter le tarif
        </button>
      </div>
      {(editable || goods.latest_check) && (
        <details id={`proposals-${goods.id}`} open={Boolean(check && check.recognition_status !== "recognized")} className="proposals-box">
          <summary>Autres codes possibles (recherche dans le tarif, sans IA)</summary>
          <ProposalsPanel goods={goods} editionId={edition} editable={editable} act={act} />
        </details>
      )}
      {check?.node && <TariffRates nodeId={check.node.id} />}
    </div>
  );
}

// ---- Calculs, validation, export : ce qui existe, et ce qui manque encore -----------------------

/** Taxes habituelles d'une importation au Gabon : leurs taux ne sont affichés qu'une fois vérifiés. */
const TAXES: [string, string][] = [
  ["DD", "Droit de douane (TEC)"],
  ["TCI", "Taxe communautaire d'intégration"],
  ["CCI", "Contribution communautaire d'intégration"],
  ["RS", "Redevance statistique"],
  ["TVA", "Taxe sur la valeur ajoutée"],
];

const unknown = (text = "inconnu") => <em className="muted">{text}</em>;

/** Montant par devise, sur toutes les factures ; null si une facture ne fournit pas la valeur. */
function invoiceSum(revision: Revision, pick: (i: Revision["invoices"][number]) => string | null | undefined): string | null {
  if (!revision.invoices.length) return null;
  const byCurrency = new Map<string, string[]>();
  for (const i of revision.invoices) {
    const v = pick(i);
    if (v === null || v === undefined) return null;
    byCurrency.set(i.currency || "?", [...(byCurrency.get(i.currency || "?") ?? []), v]);
  }
  return [...byCurrency.entries()].map(([cur, vals]) => `${fmtAmount(addDecimals(vals))} ${cur}`).join(" · ");
}

function invoiceTotals(revision: Revision) {
  return invoiceSum(revision, (i) => i.declared_total);
}

function SideAlerts({ detail, go }: { detail: CaseDetail; go: (tab: string) => void }) {
  const items = controlItems(detail).slice(0, 5);
  const tone = { blocking: "red", review: "amber", ok: "green", info: "blue" } as const;
  const label = { blocking: "Bloquant", review: "À vérifier", ok: "Conforme", info: "Information" } as const;
  return (
    <section className="card" aria-labelledby="alerts-title">
      <div className="card-head">
        <h2 id="alerts-title" className="card-title">Contrôles et alertes</h2>
        <button type="button" className="link-arrow" onClick={() => go("controles")}>Tous <Icon name="arrowRight" size={14} /></button>
      </div>
      {items.length === 0 ? (
        <p className="empty">Aucun contrôle.</p>
      ) : (
        <ul className="alert-list">
          {items.map((i) => (
            <li key={i.id} className={`alert-${tone[i.severity]}`}>
              <span className={`cat cat-${tone[i.severity]}`}><Icon name={i.severity === "ok" ? "checkCircle" : i.severity === "info" ? "info" : "alert"} size={18} /></span>
              <span>
                <strong>{i.category}</strong>
                <small>{i.title}</small>
                <button type="button" className="link-arrow small" onClick={() => go(i.tab)}>Voir le détail <Icon name="arrowRight" size={14} /></button>
              </span>
              <Chip tone={tone[i.severity]}>{label[i.severity]}</Chip>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}

function Calculation({ detail, go }: { detail: CaseDetail; go: (tab: string) => void }) {
  const revision = detail.revision;
  const total = invoiceTotals(revision);
  const goodsValue = invoiceSum(revision, (i) => i.totals_check?.components.goods);
  const fees = invoiceSum(revision, (i) => i.totals_check?.components.fees);
  const incoterms = [...new Set(revision.invoices.map((i) => i.incoterm).filter(Boolean))].join(", ");
  const goods = revision.goods_lines;
  const codes = goods.map((g) => g.decision?.is_current ? g.decision.selected_code_display : null).filter(Boolean);
  const origins = [...new Set(goods.map((g) => g.origin_country).filter(Boolean))].join(", ");
  const units = [...new Set(revision.invoices.flatMap((i) => i.lines.map((l) => l.unit)).filter(Boolean))].join(", ");
  return (
    <div className="grid-2-1">
      <div>
        <section className="card" aria-labelledby="calc-title">
          <div className="card-head">
            <h2 id="calc-title" className="card-title">Détail du calcul en douane</h2>
            <span className="chip chip-gray">Montants en devise de facture</span>
          </div>
          <div className="stats stats-4 flat">
            <StatCard icon="box" tone="green" label="Valeur marchandise" value={goodsValue || "inconnue"} hint="somme des lignes de facture" />
            <StatCard icon="truck" tone="blue" label="Frais facturés" value={fees || "inconnus"} hint="fret, assurance, emballage… lus sur la facture, non répartis" />
            <StatCard icon="file" tone="blue" label="Total facture" value={total || "inconnu"} hint={incoterms ? `imprimé · ${incoterms}` : "total imprimé"} />
            <StatCard icon="calculator" tone="gray" label="Base de calcul" value="non calculée" hint="valeur en douane (CIF)" />
          </div>
          <h3>Droits et taxes applicables</h3>
          <div className="table-wrap">
            <table className="data">
              <thead>
                <tr><th scope="col">Code</th><th scope="col">Libellé</th><th scope="col">Taux</th><th scope="col">Base de calcul</th><th scope="col" className="num">Montant</th></tr>
              </thead>
              <tbody>
                {TAXES.map(([code, label]) => (
                  <tr key={code}>
                    <td><strong>{code}</strong></td>
                    <td>{label}</td>
                    <td>{unknown("non vérifié")}</td>
                    <td>{unknown("non calculée")}</td>
                    <td className="num">—</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <div className="total-band">
            <span>Total des droits et taxes</span>
            <strong>non calculé</strong>
          </div>
          <p className="note-amber small">
            Le moteur de calcul n'est pas encore construit. Les taux du classeur 2016 sont des copies d'un fichier « 2015 » absent et
            ne sont pas vérifiés : aucun montant n'est calculé avec eux. Le calcul arrivera avec des règles datées et sourcées.
          </p>
        </section>
        <div className="grid-1-1">
          <section className="card" aria-labelledby="recap-title">
            <h2 id="recap-title" className="card-title">Récapitulatif</h2>
            <dl className="recap">
              <div><dt>Valeur marchandise (lignes)</dt><dd>{goodsValue || unknown()}</dd></div>
              <div><dt>Frais facturés</dt><dd>{fees || unknown()}</dd></div>
              <div><dt>Total facture imprimé</dt><dd>{total || unknown()}</dd></div>
              <div><dt>Fret et assurance retenus</dt><dd>{unknown("à confirmer")}</dd></div>
              <div><dt>Valeur en douane (CIF)</dt><dd>{unknown("non calculée")}</dd></div>
              <div><dt>Total droits et taxes</dt><dd>{unknown("non calculé")}</dd></div>
            </dl>
            <div className="total-band">
              <span>Montant total à payer</span>
              <strong>non calculé</strong>
            </div>
          </section>
          <section className="card" aria-labelledby="more-title">
            <h2 id="more-title" className="card-title">Informations complémentaires</h2>
            <dl className="recap icons">
              <div><dt><Icon name="tag" size={16} /> Position tarifaire</dt><dd>{codes.length ? codes.join(", ") : unknown(goods.length ? "à valider" : "aucune marchandise")}</dd></div>
              <div><dt><Icon name="file" size={16} /> Régime douanier</dt><dd>{revision.regime || unknown("à renseigner")}</dd></div>
              <div><dt><Icon name="mapPin" size={16} /> Pays d'origine</dt><dd>{origins || unknown()}</dd></div>
              <div><dt><Icon name="ship" size={16} /> Pays d'expédition</dt><dd>{unknown()}</dd></div>
              <div><dt><Icon name="scale" size={16} /> Unité</dt><dd>{units || unknown()}</dd></div>
              <div><dt><Icon name="box" size={16} /> Articles</dt><dd>{goods.length}</dd></div>
              <div><dt><Icon name="layers" size={16} /> Nombre de colis</dt><dd>{unknown("liste de colisage non lue")}</dd></div>
            </dl>
          </section>
        </div>
      </div>
      <div>
        <SideAlerts detail={detail} go={go} />
        <ValidationActions detail={detail} go={go} />
      </div>
    </div>
  );
}

function ValidationActions({ detail, go }: { detail: CaseDetail; go: (tab: string) => void }) {
  return (
    <section className="card" aria-labelledby="val-actions">
      <h2 id="val-actions" className="card-title">Actions de validation</h2>
      <div className="action-stack">
        <button type="button" className="btn-primary btn-block btn-row" disabled>
          <Icon name="check" /> <span>Valider le dossier</span> <Icon name="arrowRight" />
        </button>
        <button type="button" className="btn-secondary btn-block btn-row" disabled>
          <Icon name="message" /> <span>Demander une correction</span> <Icon name="arrowRight" />
        </button>
        <button type="button" className="btn-secondary btn-block btn-row" onClick={() => go("export")}>
          <Icon name="upload" /> <span>Préparer l'export<small>prérequis et fichiers</small></span> <Icon name="arrowRight" />
        </button>
      </div>
      <p className="muted small">
        La soumission et l'approbation arrivent avec le circuit de validation ({detail.revision.state_label.toLowerCase()} aujourd'hui).
      </p>
      <p className="note-blue small">« Validé » signifie validé en interne par votre société, jamais accepté par la Douane.</p>
    </section>
  );
}

function prerequisites(detail: CaseDetail) {
  const rev = detail.revision;
  const docs = rev.documents.filter((d) => !d.replaced_by_id).length;
  const goods = rev.goods_lines.length;
  const decided = rev.goods_lines.filter((g) => g.decision?.is_current).length;
  const blocking = controlItems(detail).filter((c) => c.severity === "blocking").length;
  return [
    { ok: docs > 0, title: "Documents présents", detail: "Au moins une pièce rattachée au dossier.", value: `${docs} pièce(s)`, tab: "documents", link: "Voir les documents" },
    { ok: goods > 0 && decided === goods, title: "Classifications validées", detail: "Chaque marchandise a un code confirmé et motivé.", value: `${decided} / ${goods}`, tab: "marchandises", link: "Voir la classification" },
    { ok: null, title: "Calculs validés", detail: "Le moteur de calcul n'existe pas encore.", value: "à venir", tab: "calculs", link: "Voir le calcul" },
    { ok: blocking === 0, title: "Contrôles résolus", detail: "Aucun point bloquant.", value: blocking ? `${blocking} bloquant(s)` : "Conforme", tab: "controles", link: "Voir les contrôles" },
    { ok: rev.state === "validated", title: "Validation responsable", detail: "Validation interne par un validateur de la société.", value: rev.state_label, tab: "historique", link: "Voir l'historique" },
  ] as { ok: boolean | null; title: string; detail: string; value: string; tab: string; link: string }[];
}

function Prerequisites({ detail, kind, go }: { detail: CaseDetail; kind: "validation" | "export"; go: (tab: string) => void }) {
  const rows = prerequisites(detail);
  const ready = rows.every((r) => r.ok);
  return (
    <section className="card" aria-labelledby="final-title">
      <div className="card-head">
        <h2 id="final-title" className="card-title">{kind === "export" ? "Prérequis pour l'export" : "Prérequis pour la validation"}</h2>
        <Chip tone={ready ? "green" : "amber"} icon={ready ? "checkCircle" : "clock"}>
          {ready ? "Dossier prêt" : `${rows.filter((r) => r.ok).length} / ${rows.length} prérequis remplis`}
        </Chip>
      </div>
      <p className="muted small">
        {ready ? "Tous les éléments requis sont remplis." : "Chaque prérequis renvoie vers la section où il se règle."}
      </p>
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
            <span className={`prereq-value ${r.ok ? "ok" : ""}`}>{r.value}</span>
            <button type="button" className="link-arrow" onClick={() => go(r.tab)}>
              {r.link} <Icon name="arrowRight" size={14} />
            </button>
          </li>
        ))}
      </ul>
    </section>
  );
}

function auditCsv(events: AuditEntry[]): string {
  const esc = (v: string) => `"${v.replace(/"/g, '""')}"`;
  const rows = events.map((e) => [e.at, eventLabel(e.event_type), e.event_type, e.actor ?? "système"].map(esc).join(";"));
  return ["date;action;type;auteur", ...rows].join("\n");
}

function saveFile(name: string, content: string, type: string) {
  const url = URL.createObjectURL(new Blob(["﻿" + content], { type }));
  const a = document.createElement("a");
  a.href = url;
  a.download = name;
  a.click();
  URL.revokeObjectURL(url);
}

function ExportPage({ detail, go }: { detail: CaseDetail; go: (tab: string) => void }) {
  const rev = detail.revision;
  const docs = rev.documents.filter((d) => !d.replaced_by_id);
  const currencies = [...new Set(rev.invoices.map((i) => i.currency).filter(Boolean))].join(", ");

  async function downloadAudit() {
    const r = await api.caseAudit(detail.id);
    saveFile(`${detail.reference}_journal.csv`, auditCsv(r.results), "text/csv;charset=utf-8");
  }
  async function downloadDoc(id: string) {
    const { url } = await api.documentLink(id);
    window.location.assign(url);
  }

  return (
    <div className="grid-2-1">
      <div>
        <Prerequisites detail={detail} kind="export" go={go} />
        <section className="card" aria-labelledby="file-title">
          <div className="card-head">
            <h2 id="file-title" className="card-title">Fichier d'export</h2>
            <Chip tone="gray" icon="clock">À venir</Chip>
          </div>
          <div className="export-file">
            <span className="export-icon"><Icon name="fileSheet" size={34} /></span>
            <dl className="recap">
              <div><dt>Nom du fichier</dt><dd>{unknown("généré à l'export")}</dd></div>
              <div><dt>Format</dt><dd>{unknown("à confirmer avec la Douane (SYDONIA ou autre)")}</dd></div>
              <div><dt>Généré le</dt><dd>—</dd></div>
              <div><dt>Généré par</dt><dd>—</dd></div>
            </dl>
          </div>
          <p className="muted small">Aucun fichier « importable directement » n'est promis tant que le format n'est pas confirmé.</p>
        </section>
        <section className="card" aria-labelledby="final-docs">
          <h2 id="final-docs" className="card-title">Documents finaux à télécharger</h2>
          <p className="muted small">Récupérez les documents du dossier pour archivage ou transmission.</p>
          <div className="final-docs">
            <div className="final-doc">
              <span className="doc-type doc-pdf">PDF</span>
              <strong>Récapitulatif du dossier</strong>
              <small>{detail.reference}.pdf · à venir</small>
              <button type="button" className="btn-secondary btn-block" disabled><Icon name="download" size={16} /> Télécharger</button>
            </div>
            <div className="final-doc">
              <span className="doc-type doc-xls">XLS</span>
              <strong>Calcul détaillé des droits</strong>
              <small>{detail.reference}_calcul.xlsx · à venir</small>
              <button type="button" className="btn-secondary btn-block" disabled><Icon name="download" size={16} /> Télécharger</button>
            </div>
            <div className="final-doc">
              <span className="doc-type doc-img">CSV</span>
              <strong>Journal d'audit</strong>
              <small>{detail.reference}_journal.csv</small>
              <button type="button" className="btn-secondary btn-block" onClick={() => void downloadAudit()}><Icon name="download" size={16} /> Télécharger</button>
            </div>
            <div className="final-doc">
              <span className="doc-type doc-none"><Icon name="archive" size={16} /></span>
              <strong>Pièces du dossier</strong>
              <small>{docs.length} pièce(s) originale(s)</small>
              {docs.length === 0 ? (
                <button type="button" className="btn-secondary btn-block" disabled>Aucune pièce</button>
              ) : (
                <select aria-label="Télécharger une pièce" defaultValue="" onChange={(e) => e.target.value && void downloadDoc(e.target.value)}>
                  <option value="">Télécharger une pièce…</option>
                  {docs.map((d) => (
                    <option key={d.id} value={d.document.id}>{d.document.original_name}</option>
                  ))}
                </select>
              )}
            </div>
          </div>
        </section>
      </div>
      <div>
        <section className="card" aria-labelledby="export-actions">
          <h2 id="export-actions" className="card-title">Actions d'export</h2>
          <div className="action-stack">
            <button type="button" className="btn-primary btn-block btn-row" disabled>
              <Icon name="upload" /> <span>Générer l'export</span> <Icon name="arrowRight" />
            </button>
            <button type="button" className="btn-secondary btn-block btn-row" disabled>
              <Icon name="download" /> <span>Télécharger le dossier complet</span> <Icon name="arrowRight" />
            </button>
            <button type="button" className="btn-secondary btn-block btn-row" disabled>
              <Icon name="check" /> <span>Marquer comme exporté</span> <Icon name="arrowRight" />
            </button>
          </div>
          <p className="note-blue small">
            L'export (récapitulatif PDF, détail Excel, fichier pour le logiciel douanier) arrive dans une prochaine version.
          </p>
        </section>
        <section className="card" aria-labelledby="export-history">
          <h2 id="export-history" className="card-title">Historique des exports</h2>
          <p className="empty">Aucun export généré pour ce dossier.</p>
        </section>
        <section className="card" aria-labelledby="export-info">
          <h2 id="export-info" className="card-title">Informations complémentaires</h2>
          <dl className="recap">
            <div><dt>Système cible</dt><dd>{unknown("à confirmer")}</dd></div>
            <div><dt>Type de déclaration</dt><dd>Importation</dd></div>
            <div><dt>Territoire</dt><dd>{rev.territory === "GA" ? "Gabon" : rev.territory}</dd></div>
            <div><dt>Bureau de douane</dt><dd>{unknown("à renseigner")}</dd></div>
            <div><dt>Régime douanier</dt><dd>{rev.regime || unknown("à renseigner")}</dd></div>
            <div><dt>Devise</dt><dd>{currencies || unknown()}</dd></div>
            <div><dt>Nombre d'articles</dt><dd>{rev.goods_lines.length}</dd></div>
            <div><dt>Poids total (brut)</dt><dd>{unknown()}</dd></div>
          </dl>
        </section>
      </div>
    </div>
  );
}

function ValidationPage({ detail, go }: { detail: CaseDetail; go: (tab: string) => void }) {
  return (
    <div className="grid-2-1">
      <div>
        <Prerequisites detail={detail} kind="validation" go={go} />
        <section className="card" aria-labelledby="circuit-title">
          <h2 id="circuit-title" className="card-title">Circuit de validation</h2>
          <ol className="circuit">
            {[
              ["Préparation", "L'agent complète le dossier et classe les marchandises.", ["draft", "in_preparation", "to_correct"]],
              ["Soumission", "L'agent envoie le dossier à un validateur de la société.", ["to_validate"]],
              ["Validation interne", "Le validateur approuve ou demande une correction motivée.", ["validated", "archived"]],
            ].map(([title, text, states]) => (
              <li key={title as string} className={(states as string[]).includes(detail.revision.state) ? "current" : undefined}>
                <strong>{title as string}</strong>
                <small>{text as string}</small>
              </li>
            ))}
          </ol>
          <p className="muted small">État actuel : {detail.revision.state_label}. La soumission et l'approbation arrivent avec le circuit de validation.</p>
        </section>
      </div>
      <div>
        <ValidationActions detail={detail} go={go} />
        <SideAlerts detail={detail} go={go} />
      </div>
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
