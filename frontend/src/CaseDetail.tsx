import { Fragment, useCallback, useEffect, useState, type FormEvent, type ReactNode } from "react";
import {
  api,
  ApiError,
  type AuditEntry,
  type CaseCalculation,
  type CaseDetail,
  type CaseExport,
  type AIProposal,
  type AIState,
  type CaseDocument,
  type CodeCheck,
  type DocumentField,
  type FieldSource,
  type GoodsLine,
  type Importer,
  type Invoice,
  type Me,
  type Membership,
  type NodeDetail,
  type PieceType,
  type Preview,
  type Revision,
} from "./api";
import { Controls, controlItems } from "./Controls";
import { Divergences, ExtractionControls, Flags, LineEditor, OriginBadge, TotalsPanel } from "./Extraction";
import { Icon, type IconName } from "./Icon";
import { PdfViewer, type Highlight } from "./PdfViewer";
import { CalcLinesTable, CalcTaxesTable, useCaseCalculation, xaf } from "./Taxes";
import { DocumentChecklist } from "./DocumentChecklist";
import { DocumentIntelligencePanel } from "./DocumentIntelligencePanel";
import { ProposalsPanel } from "./Proposals";
import { AUTO, PieceTypeSelect, uploadChoice } from "./PieceTypeSelect";
import { confirmReason, fieldLabel, readerOf, typeLabel } from "./pieceTypes";
import { tr, useI18n, type MessageKey } from "./i18n";
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
  stateLabel,
  Stepper,
  type EditionOption,
  type Tone,
} from "./ui";

export const USAGES: [string, MessageKey][] = [
  ["invoice", "usage.invoice"],
  ["packing_list", "usage.packing"],
  ["transport", "usage.transport"],
  ["insurance", "usage.insurance"],
  ["freight", "usage.freight"],
  ["origin", "usage.origin"],
  ["other", "usage.other"],
];

const CONFIRMATION: Record<string, MessageKey> = {
  pending: "confirm.pending",
  confirmed: "confirm.confirmed",
  stale: "confirm.stale",
};

export const CASE_TABS: { key: string; label: MessageKey; icon: IconName }[] = [
  { key: "apercu", label: "tab.overview", icon: "eye" },
  { key: "documents", label: "tab.documents", icon: "file" },
  { key: "donnees", label: "tab.data", icon: "edit" },
  { key: "marchandises", label: "tab.goods", icon: "box" },
  { key: "controles", label: "tab.controls", icon: "checkCircle" },
  { key: "calculs", label: "tab.calculations", icon: "calculator" },
  { key: "validation", label: "tab.validation", icon: "shield" },
  { key: "export", label: "tab.export", icon: "upload" },
  { key: "historique", label: "tab.history", icon: "history" },
];

/** Onglets de la fiche dossier (en-tête « Dossier … — importateur »), comme sur la maquette Documents. */
const DOSSIER_TABS: { key: string; label: MessageKey; icon: IconName }[] = [
  { key: "apercu", label: "tab.overview", icon: "eye" },
  { key: "documents", label: "tab.documents", icon: "file" },
  { key: "donnees", label: "tab.data", icon: "edit" },
  { key: "controles", label: "tab.checks", icon: "checkCircle" },
  { key: "historique", label: "tab.history", icon: "history" },
];

type Act = (a: () => Promise<unknown>) => Promise<void>;

/** Titre et sous-titre de chaque onglet, comme sur les écrans de référence. */
const TAB_HEADINGS: Record<string, (ref: string) => { title: string; subtitle: string }> = {
  apercu: () => ({ title: tr("head.case"), subtitle: tr("head.overviewSub") }),
  documents: () => ({ title: tr("head.case"), subtitle: tr("head.documentsSub") }),
  donnees: (ref) => ({ title: tr("head.dataTitle", { ref }), subtitle: tr("head.dataSub") }),
  marchandises: (ref) => ({ title: tr("head.goodsTitle", { ref }), subtitle: tr("head.goodsSub") }),
  controles: (ref) => ({ title: tr("head.controlsTitle", { ref }), subtitle: tr("head.controlsSub") }),
  calculs: () => ({ title: tr("head.calcTitle"), subtitle: tr("head.calcSub") }),
  validation: (ref) => ({ title: tr("head.validationTitle", { ref }), subtitle: tr("head.validationSub") }),
  export: (ref) => ({ title: tr("head.exportTitle", { ref }), subtitle: tr("head.exportSub") }),
  historique: (ref) => ({ title: tr("head.historyTitle", { ref }), subtitle: tr("head.historySub") }),
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
        {tr("actions.button")} <Icon name="chevronDown" size={16} />
      </button>
      {open && (
        <ul className="menu menu-right" role="menu" aria-label={tr("actions.menu")}>
          {canTake && <li role="menuitem"><button type="button" onClick={pick(onTake)}><Icon name="user" size={16} /> {tr("actions.take")}</button></li>}
          <li role="menuitem"><button type="button" onClick={pick(() => go("apercu"))}><Icon name="eye" size={16} /> {tr("actions.overview")}</button></li>
          <li role="menuitem"><button type="button" onClick={pick(() => go("documents"))}><Icon name="upload" size={16} /> {tr("actions.addDocument")}</button></li>
          <li role="menuitem"><button type="button" onClick={pick(() => go("donnees"))}><Icon name="edit" size={16} /> {tr("tab.data")}</button></li>
          <li role="menuitem"><button type="button" onClick={pick(() => go("controles"))}><Icon name="checkCircle" size={16} /> {tr("actions.seeControls")}</button></li>
          <li role="menuitem"><button type="button" onClick={pick(() => go("historique"))}><Icon name="history" size={16} /> {tr("actions.seeHistory")}</button></li>
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
  return n > 1024 * 1024 ? tr("size.mb", { n: (n / 1024 / 1024).toFixed(1) }) : tr("size.kb", { n: Math.max(1, Math.round(n / 1024)) });
}

const territory = (code: string) => (code === "GA" ? tr("country.gabon") : code || tr("case.unknownTerritory"));

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
      setError(errorText(err, tr("case.notFound")));
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
      setError(errorText(err, tr("common.actionFailed")));
    }
    await reload();
  }

  if (!detail) return <p className="muted">{error ?? tr("loading")}</p>;
  const rev = detail.revision;
  const editable = canEdit && rev.is_editable;
  const steps = caseSteps(rev);
  const go = (key: string) => navigate(`/dossiers/${detail.id}/${key}`);
  const tabInfo = CASE_TABS.find((t) => t.key === tab);
  const heading = TAB_HEADINGS[tab]?.(detail.reference) ?? TAB_HEADINGS.apercu(detail.reference);
  const dossierView = DOSSIER_TABS.some((t) => t.key === tab && t.key !== "controles");

  return (
    <div className={`case-detail case-detail-${tab}`}>
      {tab !== "marchandises" && (<>
      <nav className="breadcrumb" aria-label={tr("nav.breadcrumb")}>
        <button type="button" className="link" onClick={() => navigate("/dossiers")}>
          {dossierView && <Icon name="arrowLeft" size={14} />} {tr("nav.myCases")}
        </button>
        <Icon name="chevronRight" size={14} />
        <button type="button" className="link" onClick={() => go("apercu")}>{detail.reference}</button>
        {tabInfo && !dossierView && (
          <>
            <Icon name="chevronRight" size={14} />
            <span>{tr(tabInfo.label)}</span>
          </>
        )}
      </nav>
      {dossierView ? (
        <div className="case-head case-head-dossier">
          <div>
            <h1 id="case-title">
              {tr("case.titleRef", { ref: detail.reference })}
              {detail.importer && <> — {detail.importer.name}</>}
              <StateChip state={rev.state} label={rev.state_label} />
            </h1>
            <p className="case-meta">
              <span><Icon name="file" size={17} /> {tr("case.importation")}</span>
              <span><Icon name="layers" size={17} /> {rev.mode_label}</span>
              <span><Icon name="mapPin" size={17} /> {territory(rev.territory)}</span>
              <span><Icon name="user" size={17} /> {tr("case.createdBy", { date: fmtDate(detail.created_at), name: personName(detail.created_by) })}</span>
            </p>
          </div>
          <CaseActions canTake={canEdit && !detail.assigned_to} onTake={() => act(() => api.assignCase(detail.id, me.id, detail.row_version))} go={go} />
        </div>
      ) : (
        <div className="case-head case-head-section">
          <div className="case-head-main">
            <h1 id="case-title">{heading.title}</h1>
            <p className="page-subtitle">{heading.subtitle}</p>
            {(tab === "calculs" || tab === "export" || tab === "validation") && (
              <div className="head-stepper" aria-label={tr("case.steps")}>
                <Stepper steps={steps} onSelect={go} />
              </div>
            )}
          </div>
          <aside className="case-aside" aria-label={tr("case.summary")}>
            <StateChip state={rev.state} label={rev.state_label} />
            <strong>{detail.reference}</strong>
            <span>{detail.importer?.name ?? <em className="muted">{tr("case.importerToFill")}</em>}</span>
            <small>{rev.transport_mode_label ? <>{rev.transport_mode_label} <i /> </> : null}{tr("case.importation")} <i /> {territory(rev.territory)}</small>
            <CaseActions canTake={canEdit && !detail.assigned_to} onTake={() => act(() => api.assignCase(detail.id, me.id, detail.row_version))} go={go} />
          </aside>
        </div>
      )}
      {error && <p role="alert" className="error">⚠ {error}</p>}
      </>)}

      {dossierView && (
        <div role="tablist" className="tabs case-tabs" aria-label={tr("case.sections")}>
          {DOSSIER_TABS.map((t) => (
            <button key={t.key} type="button" role="tab" aria-selected={tab === t.key} onClick={() => go(t.key)}>
              <Icon name={t.icon} size={19} />
              {tr(t.label)}
            </button>
          ))}
        </div>
      )}
      {tab === "apercu" && (
        <section className="card stepper-card" aria-label={tr("case.steps")}>
          <Stepper steps={steps} onSelect={go} />
        </section>
      )}

      <div>
        {tab === "apercu" && (
          <Overview detail={detail} editions={editions} editable={editable} act={act} go={go} />
        )}
        {tab === "documents" && (
          <DocumentsTab caseId={detail.id} caseVersion={detail.row_version} revision={rev} importer={detail.importer?.name ?? null} editable={editable} onChange={reload} go={go} />
        )}
        {tab === "donnees" && <Invoices revision={rev} editable={editable} act={act} />}
        {tab === "marchandises" && (
          <GoodsTab
            revision={rev}
            editions={editions}
            editable={editable}
            act={act}
            head={
              <>
                <nav className="breadcrumb" aria-label={tr("nav.breadcrumb")}>
                  <button type="button" className="link" onClick={() => go("apercu")}>{detail.reference}</button>
                  <Icon name="chevronRight" size={14} />
                  <span>{tr("tab.goods")}</span>
                </nav>
                <h1 id="case-title" className="goods-title">{tr("tab.goods")}</h1>
                <p className="goods-sub">{tr("goods.classifyTitle", { ref: detail.reference })}</p>
                <p className="goods-text">{tr("goods.classifyText")}</p>
                {error && <p role="alert" className="error">⚠ {error}</p>}
              </>
            }
          />
        )}
        {tab === "controles" && <Controls detail={detail} go={go} />}
        {tab === "calculs" && <Calculation detail={detail} membership={membership} act={act} go={go} />}
        {tab === "validation" && <ValidationPage detail={detail} membership={membership} act={act} go={go} />}
        {tab === "export" && <ExportPage detail={detail} act={act} go={go} />}
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
          <h2 id="info-title" className="card-title">{tr("overview.info")}</h2>
          <p className="muted small">{rev.status_note}</p>
          {rev.target_edition?.warning && <p className="note-amber small" role="note">ⓘ {rev.target_edition.warning}</p>}
          <RevisionForm revision={rev} editions={editions} editable={editable} onSave={(data) => act(() => api.updateRevision(rev.id, data))} />
        </section>
        <Completeness revision={rev} />
      </div>
      <section className="card">
        <h2 className="card-title">{tr("overview.next")}</h2>
        {next ? (
          <>
            <p className="big-line">{next.label}</p>
            <p className="muted">{next.detail}</p>
            <button type="button" className="btn-primary" onClick={() => go(next.key)}>
              {tr("common.continue")} <Icon name="arrowRight" />
            </button>
          </>
        ) : (
          <p>{tr("overview.allDone")}</p>
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
          {tr("form.plannedDate")}
          <input type="date" value={form.planned_declaration_date} onChange={(e) => setForm({ ...form, planned_declaration_date: e.target.value })} />
        </label>
        <label>
          {tr("form.regime")}
          <input value={form.regime} onChange={(e) => setForm({ ...form, regime: e.target.value })} />
        </label>
        <label>
          {tr("form.tariffUsed")}
          <select value={form.target_edition_id} onChange={(e) => setForm({ ...form, target_edition_id: e.target.value })}>
            <option value="">{tr("form.toChoose")}</option>
            {editions.map((e) => (
              <option key={e.id} value={e.id}>{e.label}</option>
            ))}
          </select>
        </label>
        <div className="form-end">
          <button type="submit" className="btn-secondary">{tr("common.save")}</button>
        </div>
      </fieldset>
    </form>
  );
}

function Completeness({ revision }: { revision: Revision }) {
  const { blocking, warnings } = revision.completeness;
  return (
    <section className="card" aria-labelledby="completeness-title">
      <h2 id="completeness-title" className="card-title">{tr("complete.title")}</h2>
      {blocking.length === 0 ? (
        <p className="ok-line"><Icon name="checkCircle" size={18} /> {tr("complete.none")}</p>
      ) : (
        <>
          <p className="muted small">{tr("complete.count", { n: blocking.length })}</p>
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
          <h3>{tr("complete.toExamine")}</h3>
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

/** Pictogramme de pièce, coloré selon son rôle dans le dossier. */
const DOC_TONES: Record<string, string> = { invoice: "red", packing_list: "red", transport: "blue", insurance: "blue", origin: "green" };

function DocGlyph({ usage, mime }: { usage: string; mime: string }) {
  const tone = DOC_TONES[usage] ?? "gray";
  const sheet = !mime.includes("pdf") && !mime.startsWith("image/");
  return (
    <svg className={`doc-glyph doc-glyph-${tone}`} viewBox="0 0 26 32" width={26} height={32} aria-hidden="true">
      <path d="M3 0h14l9 9v20a3 3 0 0 1-3 3H3a3 3 0 0 1-3-3V3a3 3 0 0 1 3-3z" fill="currentColor" />
      <path d="M17 0v6a3 3 0 0 0 3 3h6z" fill="#fff" fillOpacity=".45" />
      {usage === "insurance" ? (
        <path d="M13 12l6 2.2v4.3c0 3.6-2.6 5.7-6 6.5-3.4-.8-6-2.9-6-6.5v-4.3z" fill="#fff" />
      ) : usage === "origin" || sheet ? (
        <path d="M7.5 14h11M7.5 18h11M7.5 22h7" stroke="#fff" strokeWidth="2" strokeLinecap="round" fill="none" />
      ) : (
        <path d="M13 12c1.2 0 1.2 2.5 0 6-1 3-3.5 6.2-5.2 6.2-1.4 0-.7-2.2 2.6-3.3 2.6-.9 6.3-1.3 7.8-.4 1.4.8.5 2-1 1.2-1.6-.8-3.3-3.2-4.6-6-.9-2-.8-3.7.4-3.7z" stroke="#fff" strokeWidth="1.5" fill="none" strokeLinejoin="round" />
      )}
    </svg>
  );
}

function DocumentsTab({
  caseId,
  caseVersion,
  revision,
  importer,
  editable,
  onChange,
  go,
}: {
  caseId: string;
  caseVersion: number;
  revision: Revision;
  importer: string | null;
  editable: boolean;
  onChange: () => Promise<void>;
  go: (tab: string) => void;
}) {
  const { t } = useI18n();
  const active = revision.documents.filter((d) => !d.replaced_by_id);
  const replaced = revision.documents.filter((d) => d.replaced_by_id);
  const [selectedId, setSelectedId] = useState<string | null>(
    (active.find((d) => d.usage === "invoice") ?? active[0])?.id ?? null,
  );
  const [highlight, setHighlight] = useState<Highlight | null>(null);
  const selected = revision.documents.find((d) => d.id === selectedId) ?? active[0] ?? null;

  useEffect(() => {
    if (!selectedId && active[0]) setSelectedId(active[0].id);
  }, [active, selectedId]);

  return (
    <>
      <div className="doc-layout">
        <section className="card doc-list" aria-labelledby="docs-title">
          <h2 id="docs-title" className="card-title">{tr("docs.title")}</h2>
          {editable && <Upload caseId={caseId} onDone={async (id) => { await onChange(); if (id) setSelectedId(id); }} />}
          {active.length === 0 ? (
            <p className="empty">{tr("docs.none")}</p>
          ) : (
            <ul className="doc-items">
              {active.map((link) => (
                <li key={link.id}>
                  <button
                    type="button"
                    className={`doc-item${selected?.id === link.id ? " selected" : ""}`}
                    onClick={() => { setSelectedId(link.id); setHighlight(null); }}
                  >
                    <DocGlyph usage={link.usage} mime={link.document.mime} />
                    <span className="doc-text">
                      <strong>{link.document_type ? typeLabel(link.document_type) : usageLabel(link.usage, link.usage_label)}</strong>
                      <span>{link.document.original_name}</span>
                      <small>
                        {fmtDate(link.created_at)} • {formatBytes(link.document.bytes)}
                        {link.document.readability !== "ok" && ` · ${link.document.readability_label}`}
                        {" · "}{tr("docs.language", { lang: LOCALE_NAMES[link.document.detected_locale ?? ""] ?? tr("docs.undetermined") })}
                      </small>
                    </span>
                  </button>
                  {link.document.language_detection?.pages && (
                    <details className="small doc-languages">
                      <summary>{t("languagesByPage")}</summary>
                      <ul>
                        {link.document.language_detection.pages.map((page, i) => (
                          <li key={i}>{tr("docs.pageLang", { n: page.page ?? i + 1, lang: page.locale || tr("docs.undetermined"), status: page.status })}</li>
                        ))}
                      </ul>
                    </details>
                  )}
                </li>
              ))}
            </ul>
          )}
          {replaced.length > 0 && (
            <details className="small">
              <summary>{tr("docs.replaced", { n: replaced.length })}</summary>
              <ul>
                {replaced.map((d) => (
                  <li key={d.id}>{d.document.original_name} (v{d.document.version})</li>
                ))}
              </ul>
            </details>
          )}
        </section>

        <section className="card viewer" aria-label={tr("docs.preview")}>
          {selected ? <Viewer link={selected} highlight={highlight} /> : <p className="empty">{tr("docs.addToShow")}</p>}
        </section>

        <div className="doc-side">
          {selected ? (
            <ExtractedPanel link={selected} caseId={caseId} caseVersion={caseVersion} revision={revision} importer={importer} editable={editable} onChange={onChange} onSource={setHighlight} go={go} />
          ) : (
            <section className="card" aria-labelledby="extracted-title">
              <h2 id="extracted-title" className="card-title">{tr("tab.data")}</h2>
              <p className="empty">{tr("docs.noneSelected")}</p>
            </section>
          )}
        </div>
      </div>
      <div className="doc-rules">
        <DocumentChecklist revisionId={revision.id} />
        <DocumentIntelligencePanel revision={revision} editable={editable} />
      </div>
    </>
  );
}

const LOCALE_NAMES: Record<string, string> = { fr: "Français", en: "English", es: "Español", ar: "العربية" };

/** Rôle d'une pièce dans la langue affichée ; libellé du serveur pour un rôle inconnu ici. */
export function usageLabel(usage: string, fallback: string): string {
  const key = USAGES.find(([v]) => v === usage)?.[1];
  return key ? tr(key) : fallback;
}

function Upload({ caseId, onDone }: { caseId: string; onDone: (selectId: string | null) => Promise<void> }) {
  const [open, setOpen] = useState(false);
  const [limits, setLimits] = useState<{ max_bytes: number; accepted: string[] } | null>(null);
  const [file, setFile] = useState<File | null>(null);
  const [choice, setChoice] = useState(AUTO);
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
      const { usage, documentType } = uploadChoice(choice);
      const link = await api.uploadDocument(caseId, file, usage, action, crypto.randomUUID(), documentType);
      setDuplicate(null);
      setMessage(
        link.document.readability === "ok"
          ? tr("upload.added", { name: link.document.original_name })
          : tr("upload.keptBut", { name: link.document.original_name, state: link.document.readability_label.toLowerCase() }),
      );
      setFile(null);
      setOpen(false);
      await startReading(link);
      await onDone(link.id);
    } catch (err) {
      if (err instanceof ApiError && err.code === "DUPLICATE_DOCUMENT") {
        setDuplicate((err.details.existing as { id: string; original_name: string; cases: string[] }[]) ?? []);
      } else {
        setError(errorText(err, tr("upload.failed")));
      }
    }
  }

  /** Lecture lancée dès le dépôt pour une pièce qui a une lecture automatique ; un échec n'annule pas le dépôt. */
  async function startReading(link: CaseDocument) {
    if (!readerOf(link) || link.document.readability !== "ok" || link.latest_extraction) return;
    await api.extract(link.id, { ocr: link.document.mime.startsWith("image/") }).catch(() => undefined);
  }

  async function reuse(id: string) {
    setError(null);
    try {
      const { usage, documentType } = uploadChoice(choice);
      const link = await api.reuseDocument(caseId, id, usage, documentType);
      setDuplicate(null);
      setOpen(false);
      setMessage(tr("upload.reused"));
      await onDone(link.id);
    } catch (err) {
      setError(errorText(err, tr("upload.reuseFailed")));
    }
  }

  return (
    <div className="upload">
      {!open ? (
        <>
          <button type="button" className="btn-primary btn-block" onClick={() => setOpen(true)}>
            <Icon name="plus" /> {tr("actions.addDocument")}
          </button>
          <button type="button" className="btn-secondary btn-block scan-entry" onClick={() => navigate(`/dossiers/${caseId}/numerisation`)}>
            <Icon name="layers" /> {tr("scan.entry")}
          </button>
        </>
      ) : (
        <form className="upload-form" onSubmit={(e) => { e.preventDefault(); void send(); }}>
          <label>
            {tr("upload.file")}
            <input type="file" accept=".pdf,.png,.jpg,.jpeg,.xlsx" onChange={(e) => setFile(e.target.files?.[0] ?? null)} required />
          </label>
          <label>
            {tr("upload.type")}
            <PieceTypeSelect value={choice} onChange={setChoice} />
          </label>
          {limits && (
            <p className="muted small">
              {tr("upload.limits", { formats: limits.accepted.join(", "), size: formatBytes(limits.max_bytes) })}
            </p>
          )}
          <div className="actions-row">
            <button type="button" className="btn-secondary" onClick={() => setOpen(false)}>{tr("common.cancel")}</button>
            <button type="submit" className="btn-primary">{tr("upload.submit")}</button>
          </div>
        </form>
      )}
      {duplicate && (
        <div className="note-amber small" role="alert">
          <p>{tr("upload.duplicate")}</p>
          <ul>
            {duplicate.map((d) => (
              <li key={d.id}>
                {d.original_name} {d.cases.length > 0 && tr("upload.inCases", { list: d.cases.join(", ") })}{" "}
                <button type="button" className="btn-small" onClick={() => void reuse(d.id)}>{tr("upload.reuse")}</button>
              </li>
            ))}
          </ul>
          <button type="button" className="btn-small" onClick={() => void send("keep_both")}>{tr("upload.keepBoth")}</button>{" "}
          <button type="button" className="btn-small" onClick={() => setDuplicate(null)}>{tr("common.cancel")}</button>
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
    api.documentPreview(link.document.id).then(setPreview, (err) => setError(errorText(err, tr("viewer.previewFailed"))));
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
        <button type="button" className="icon-button" onClick={() => void download()} title={tr("common.download")}>
          <Icon name="download" />
          <span className="visually-hidden">{tr("common.download")}</span>
        </button>
      </div>
      <div className="viewer-body">
        {!link.document.previewable && (
          <p className="empty">
            {tr("viewer.unavailable", { state: link.document.readability_label.toLowerCase() })}
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
                <h3>{tr("viewer.sheet", { name: sheet.name })}{sheet.truncated && tr("viewer.excerpt")}</h3>
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
  if (value === null || value === undefined || value === "") return { tone: "gray", label: tr("field.unknown") };
  if (flagged) return { tone: "amber", label: tr("field.toVerify") };
  if (origin === "manual") return { tone: "blue", label: tr("field.typed") };
  if (origin === "confirmed") return { tone: "green", label: tr("field.confirmed") };
  return { tone: "green", label: tr("field.extracted") };
}

function SourceLink({ source, onSource }: { source?: FieldSource; onSource: (h: Highlight) => void }) {
  const span = source?.span;
  if (!span) return null;
  if (span.sheet) return <span className="source-link">{tr("source.cell", { ref: `${span.sheet}!${span.cell_range}` })}</span>;
  if (span.page == null) return null;
  return (
    <button type="button" className="source-link" onClick={() => onSource({ page: span.page!, bbox: span.bbox })} title={span.excerpt ? tr("source.textRead", { text: span.excerpt }) : undefined}>
      {tr("source.see", { page: span.page })} <Icon name="external" size={13} />
    </button>
  );
}

const PREVIEW_LINES = 3;

const AMOUNT_FIELDS = new Set(["insured_value", "premium_total", "freight_total"]);

/** Nom comparé sans casse, accents ni ponctuation : « Société Alpha SARL » = « SOCIETE ALPHA S.A.R.L ». */
const nameKey = (v: string) =>
  v.normalize("NFD").replace(/[\u0300-\u036f]/g, "").toLocaleLowerCase().replace(/[^\p{L}\p{N}]+/gu, "");
const sameName = (a: string, b: string) => nameKey(a) === nameKey(b);
/** Nom de l'acheteur sans l'adresse qui suit souvent sur la facture (« Alpha SA, BP 12 Libreville »). */
const buyerShortName = (v: string) => v.split(/[,\n]/)[0].trim();

/** Valeur lue affichée : date et montant mis en forme, texte tel qu'imprimé sinon. */
function shownValue(field: DocumentField): string {
  const parsed = typeof field.parsed === "string" ? field.parsed : "";
  if (/^\d{4}-\d{2}-\d{2}$/.test(parsed)) return fmtDate(parsed);
  if (AMOUNT_FIELDS.has(field.field) && /^-?\d+(\.\d+)?$/.test(parsed)) return fmtAmount(parsed);
  return field.raw ?? "";
}

/** Proposition de l'IA en ligne : valeur, extrait cité et lien vers la page, toujours à vérifier. */
function AIProposalLine({ proposal, onSource }: { proposal: AIProposal; onSource: (h: Highlight) => void }) {
  return (
    <>
      <span className="field-value">{proposal.raw}</span>
      <span className="block small muted">
        {tr("ai.excerpt", { text: proposal.excerpt })} <SourceLink source={{ span: proposal.span } as FieldSource} onSource={onSource} />
      </span>
    </>
  );
}

function AIChips() {
  return (
    <span className="ia-chips">
      <span className="ia-tag">{tr("ai.proposed")}</span>
      <Chip tone="amber" icon="alert">{tr("field.toVerify")}</Chip>
    </span>
  );
}

/** Informations lues sur un titre de transport, une assurance ou une facture de fret. */
export function DocumentFields({
  fields,
  onSource,
  runId,
  editable = false,
  onChange,
}: {
  fields: DocumentField[];
  onSource: (h: Highlight) => void;
  runId?: string;
  editable?: boolean;
  onChange?: () => Promise<void>;
}) {
  const [entering, setEntering] = useState<string | null>(null);
  const [draft, setDraft] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const canDecide = editable && Boolean(runId) && !busy;

  async function decide(field: string, action: "accept" | "set", value = "") {
    if (!runId) return;
    setBusy(true);
    setError(null);
    try {
      await api.decideField(runId, field, action, value);
      setEntering(null);
      await onChange?.();
    } catch (err) {
      setError(errorText(err, tr("ai.decisionFailed")));
    } finally {
      setBusy(false);
    }
  }

  function startEntry(field: string, value: string) {
    setEntering(field);
    setDraft(value);
    setError(null);
  }

  return (
    <>
      <h3 className="extracted-sub">{tr("extract.docRead")}</h3>
      <dl className="field-list">
        {fields.map((f) => {
          const label = fieldLabel(f.field, f.label);
          const read = f.status === "missing" ? "" : shownValue(f);
          const flagged = f.status !== "ok" || f.origin === "inferred";
          const proposal = !read && !f.entered ? f.proposal : null;
          const status = f.entered ? { tone: "blue" as Tone, label: tr("field.typed") } : fieldStatus(read, f.origin, flagged);
          const entry = entering === f.field && (
            <form className="ia-entry" onSubmit={(e) => { e.preventDefault(); void decide(f.field, "set", draft); }}>
              <input aria-label={`${tr("ai.value")} : ${label}`} value={draft} maxLength={500} required onChange={(e) => setDraft(e.target.value)} />
              <button type="submit" className="btn-small" disabled={busy || !draft.trim()}>{tr("save")}</button>
              <button type="button" className="btn-small" onClick={() => setEntering(null)}>{tr("cancel")}</button>
            </form>
          );
          return (
            <div key={f.field} className="field-row">
              <dt>{label}</dt>
              <dd>
                {f.entered ? (
                  <>
                    <span className="field-value">{f.entered.raw || "—"}</span>
                    <span className="block small muted">{tr(f.entered.from_ai ? "ai.retainedAI" : "ai.typedBy", { name: f.entered.by })}</span>
                  </>
                ) : proposal ? (
                  <>
                    <AIProposalLine proposal={proposal} onSource={onSource} />
                    {canDecide && !entry && (
                      <span className="ia-note-row">
                        <button type="button" className="btn-small" onClick={() => void decide(f.field, "accept")}>{tr("ai.accept")}</button>
                        <button type="button" className="source-link" onClick={() => startEntry(f.field, proposal.raw ?? "")}><Icon name="edit" size={13} /> {tr("ai.correct")}</button>
                      </span>
                    )}
                  </>
                ) : (
                  <>
                    <span className="field-value" title={f.notes.join(" ") || undefined}>{read || "—"}</span>
                    <SourceLink source={{ span: f.span } as FieldSource} onSource={onSource} />
                    {read && flagged && f.notes.map((n) => <span key={n} className="block small muted">⚠ {n}</span>)}
                    {!read && canDecide && !entry && (
                      <span className="ia-note-row">
                        <button type="button" className="source-link" onClick={() => startEntry(f.field, "")}><Icon name="edit" size={13} /> {tr("ai.enter")}</button>
                      </span>
                    )}
                  </>
                )}
                {entry}
              </dd>
              {proposal ? <AIChips /> : (
                <Chip tone={status.tone} icon={status.tone === "amber" ? "alert" : status.tone === "green" ? "checkCircle" : undefined}>{status.label}</Chip>
              )}
            </div>
          );
        })}
      </dl>
      {error && <p role="alert" className="error small">⚠ {error}</p>}
    </>
  );
}

/** État de l'IA en ligne sur la pièce : complément fait, refusé, plafond, échec, et bouton « Compléter ». */
export function AINote({ linkId, ai, editable, onChange }: { linkId: string; ai?: AIState; editable: boolean; onChange: () => Promise<void> }) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  if (!ai) return null;
  const last = ai.last;

  async function complete() {
    setBusy(true);
    setError(null);
    try {
      await api.completeWithAI(linkId);
      await onChange();
    } catch (err) {
      setError(errorText(err, tr("ai.decisionFailed")));
    } finally {
      setBusy(false);
    }
  }

  let note: ReactNode = null;
  if (last?.status === "sent") {
    note = (
      <div className="note-blue small ia-panel-note" role="note">
        <p><strong>{tr("ai.completedOn", { date: fmtDateTime(last.created_at) })}</strong></p>
        <p>{tr("ai.completedDetail", { asked: last.requested, found: last.found })}</p>
        {last.free_tier && <p>{tr("ai.freeNote")}</p>}
      </div>
    );
  } else if (last?.status === "client_refused") {
    note = <p className="note-blue small ia-panel-note" role="note">{tr("ai.refusedNote")}</p>;
  } else if (last?.status === "cap_reached") {
    note = <p className="note-amber small ia-panel-note" role="note">{tr("ai.capNote")}</p>;
  } else if (last?.status === "failed") {
    note = <p className="note-amber small ia-panel-note" role="note">{tr("ai.failedNote", { error: last.error_message ?? "" })}</p>;
  }
  const canComplete = editable && ai.can_complete;
  if (!note && !canComplete && !error) return null;
  return (
    <>
      {note}
      {canComplete && (
        <div className="ia-note-row ia-panel-note">
          <button type="button" className="btn-small" disabled={busy} onClick={() => void complete()}>
            <Icon name="shield" size={14} /> {busy ? tr("ai.completing") : tr("ai.complete")}
          </button>
          <span className="muted small">{tr("ai.completeHint", { n: ai.missing.length })}</span>
        </div>
      )}
      {error && <p role="alert" className="error small">⚠ {error}</p>}
    </>
  );
}

/** Type reconnu d'après le titre ou contredit par lui : proposé à l'agent, jamais appliqué sans lui. */
export function TypeNote({ link, editable, onChange }: { link: CaseDocument; editable: boolean; onChange: () => Promise<void> }) {
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const type = link.document_type;
  const mismatch = link.type_mismatch?.evidence.method === "title" ? link.type_mismatch : null;

  async function confirm(chosen: Pick<PieceType, "code" | "evidence">) {
    setError(null);
    setBusy(true);
    try {
      await api.confirmDocumentType(link.id, chosen.code, confirmReason(chosen, link.document.original_name));
      await onChange();
    } catch (err) {
      setError(errorText(err, tr("doc.typeFailed")));
    } finally {
      setBusy(false);
    }
  }

  const canConfirm = editable && !link.replaced_by_id && !busy;
  let note: ReactNode = null;
  if (mismatch) {
    note = (
      <div className="note-amber small" role="note">
        {tr("doc.mismatch", { title: mismatch.evidence.excerpt ?? "", type: typeLabel(mismatch), usage: usageLabel(link.usage, link.usage_label) })}{" "}
        {canConfirm && <button type="button" className="btn-small" onClick={() => void confirm(mismatch)}>{tr("doc.useType")}</button>}
      </div>
    );
  } else if (type?.source === "detected") {
    const text = type.evidence.method === "title"
      ? tr("doc.detected", { title: type.evidence.excerpt ?? "", type: typeLabel(type) })
      : tr("doc.detectedFile", { type: typeLabel(type) });
    note = (
      <p className="muted small">
        {text}{" "}
        {canConfirm && <button type="button" className="btn-small" onClick={() => void confirm(type)}>{tr("doc.confirmType")}</button>}
      </p>
    );
  } else if (type?.source === "confirmed") {
    note = <p className="muted small">{tr("doc.confirmedType", { type: typeLabel(type) })}</p>;
  }
  if (!note && !error) return null;
  return (
    <>
      {note}
      {error && <p role="alert" className="error small">⚠ {error}</p>}
    </>
  );
}

export function ExtractedPanel({
  link,
  caseId,
  caseVersion,
  revision,
  importer,
  editable,
  onChange,
  onSource,
  go,
}: {
  link: CaseDocument;
  caseId: string;
  caseVersion: number;
  revision: Revision;
  importer: string | null;
  editable: boolean;
  onChange: () => Promise<void>;
  onSource: (h: Highlight) => void;
  go: (tab: string) => void;
}) {
  const invoiceId = link.latest_extraction?.invoice_id;
  const invoice: Invoice | undefined =
    revision.invoices.find((i) => i.id === invoiceId) ?? revision.invoices.find((i) => i.document_id === link.id);
  const reader = readerOf(link);
  const canRead = Boolean(reader) || Boolean(link.latest_extraction);
  const run = link.latest_extraction;
  const done = run?.status === "succeeded";
  const currency = invoice?.currency ? ` (${invoice.currency})` : "";
  const pieceName = link.document_type ? typeLabel(link.document_type) : usageLabel(link.usage, link.usage_label);
  const buyer = invoice?.buyer_name ?? "";
  const buyerName = buyerShortName(buyer);
  const proposals = new Map((run?.ai?.proposals ?? []).map((p) => [p.field === "buyer_name" ? "importer" : p.field, p]));
  const [aiError, setAiError] = useState<string | null>(null);
  const [entering, setEntering] = useState<string | null>(null);
  const [draft, setDraft] = useState("");
  const [busy, setBusy] = useState(false);
  const [linking, setLinking] = useState(false);
  const [importers, setImporters] = useState<Importer[]>([]);
  const [importerId, setImporterId] = useState("");

  async function save(action: () => Promise<unknown>) {
    setBusy(true);
    setAiError(null);
    try {
      await action();
      setEntering(null);
      setLinking(false);
      await onChange();
    } catch (err) {
      setAiError(errorText(err, tr("ai.decisionFailed")));
    } finally {
      setBusy(false);
    }
  }

  /** Valeur saisie au format de l'API : date ISO, montant décimal, devise en majuscules. */
  function entered(field: string): Record<string, unknown> {
    if (field === "declared_total") return { declared_total: decimalInput(draft) };
    if (field === "currency") return { currency: draft.trim().toUpperCase() };
    return { [field]: draft.trim() || (field === "invoice_date" ? null : "") };
  }

  function startLink() {
    setLinking(true);
    setAiError(null);
    api.importers().then(
      (p) => {
        setImporters(p.results);
        // L'importateur dont le nom correspond à l'acheteur lu est proposé d'office.
        const match = p.results.find((i) => sameName(i.name, buyerName));
        if (match) setImporterId(match.id);
      },
      () => setImporters([]),
    );
  }

  async function linkImporter() {
    const id = importerId === "new" ? (await api.createImporter({ name: buyerName })).id : importerId;
    await api.updateCase(caseId, { importer_id: id }, caseVersion);
  }

  async function acceptProposal(field: string) {
    if (!run) return;
    setAiError(null);
    try {
      await api.decideField(run.id, field, "accept");
      await onChange();
    } catch (err) {
      setAiError(errorText(err, tr("ai.decisionFailed")));
    }
  }

  return (
    <>
      <section className="card extracted-card" aria-labelledby="extracted-title">
        <div className="extracted-head">
          <div className="card-head">
            <h2 id="extracted-title" className="card-title">{reader === "invoice" ? tr("extract.invoiceTitle") : tr("extract.docTitle", { usage: pieceName })}</h2>
            {run && (
              <Chip tone={done ? "green" : run.status === "failed" ? "red" : "blue"} icon={done ? "checkCircle" : run.status === "failed" ? "alert" : "clock"}>
                {done ? tr("extract.done") : run.status_label}
              </Chip>
            )}
          </div>
          {canRead && done && run.finished_at ? (
            <details className="read-options">
              <summary>
                <span className="processed">
                  <span className="processed-dot"><Icon name="check" size={15} /></span>
                  <span title={tr("extract.runInfo", { n: run.attempt, parser: run.parser === "ocr" ? tr("extract.ocr") : tr("extract.pdfText") }) + (run.warnings.length ? tr("extract.warnings", { n: run.warnings.length }) : "")}>
                    {tr("extract.processedOn", { date: fmtDateTime(run.finished_at) })}
                  </span>
                </span>
                <span className="btn-outline-small"><Icon name="settings" size={14} /> {tr("extract.options")}</span>
              </summary>
              <ExtractionControls link={link} editable={editable} onDone={onChange} />
            </details>
          ) : canRead ? (
            <ExtractionControls link={link} editable={editable} onDone={onChange} />
          ) : (
            <p className="muted small">{tr("extract.noReader")}</p>
          )}
          <TypeNote link={link} editable={editable} onChange={onChange} />
        </div>
        {done && <AINote linkId={link.id} ai={run.ai} editable={editable} onChange={onChange} />}
        {invoice ? (
          <>
            <h3 className="extracted-sub">{tr("extract.general")}</h3>
            <dl className="field-list">
              {(
                [
                  ["supplier_name", tr("field.supplier"), invoice.supplier_name],
                  ["importer", tr("field.importer"), importer || buyer],
                  ["invoice_number", tr("field.invoiceNo"), invoice.invoice_number],
                  ["invoice_date", tr("field.invoiceDate"), invoice.invoice_date ? fmtDate(invoice.invoice_date) : ""],
                  ["currency", tr("field.currency"), invoice.currency],
                  ["declared_total", tr("field.total"), fmtAmount(invoice.declared_total)],
                  ["incoterm", tr("field.incoterm"), invoice.incoterm],
                ] as [string, string, string | null][]
              ).map(([field, label, value]) => {
                const flagged = (invoice.review_flags ?? []).some((f) => f.field === field);
                // L'importateur vient de la fiche du dossier ; l'acheteur lu sur la facture reste à rattacher.
                const status = field === "importer"
                  ? importer ? { tone: "green" as Tone, label: tr("field.confirmed") }
                    : buyer ? { tone: "amber" as Tone, label: tr("field.toLink") }
                    : { tone: "gray" as Tone, label: tr("field.unknown") }
                  : fieldStatus(value, invoice.field_origins?.[field], flagged);
                const proposal = !value ? proposals.get(field) : undefined;
                if (proposal) {
                  return (
                    <div key={field} className="field-row">
                      <dt>{label}</dt>
                      <dd>
                        <AIProposalLine proposal={proposal} onSource={onSource} />
                        {editable && (
                          <span className="ia-note-row">
                            <button type="button" className="btn-small" onClick={() => void acceptProposal(proposal.field)}>{tr("ai.accept")}</button>
                            <span className="muted small">{tr("ai.invoiceHint")}</span>
                          </span>
                        )}
                      </dd>
                      <AIChips />
                    </div>
                  );
                }
                const canFix = editable && invoice && field !== "importer" && !busy && entering !== field;
                const raw = invoice ? String((invoice as unknown as Record<string, unknown>)[field] ?? "") : "";
                return (
                  <div key={field} className="field-row">
                    <dt>{label}</dt>
                    <dd>
                      <span className="field-value">{value || "—"}</span>
                      {field === "importer" ? (
                        importer ? (
                          <>
                            <span className="source-link source-static">{tr("field.caseRecord")}</span>
                            {buyer && !sameName(buyerName, importer) && <span className="block small muted">{tr("field.buyerDiffers", { name: buyer })}</span>}
                          </>
                        ) : buyer && (
                          <>
                            <SourceLink source={invoice.field_sources?.buyer_name} onSource={onSource} />
                            <span className="block small muted">{tr("field.buyerRead")}</span>
                          </>
                        )
                      ) : (
                        <SourceLink source={invoice.field_sources?.[field]} onSource={onSource} />
                      )}
                      <Flags flags={invoice.review_flags} field={field} />
                      {canFix && (flagged || !value) && (
                        <span className="ia-note-row">
                          {value && (
                            <button type="button" className="btn-small" onClick={() => void save(() => api.confirmInvoiceField(invoice.id, field, invoice.row_version))}>
                              {tr("field.confirm")}
                            </button>
                          )}
                          <button type="button" className="source-link" onClick={() => { setEntering(field); setDraft(raw); setAiError(null); }}>
                            <Icon name="edit" size={13} /> {value ? tr("ai.correct") : tr("ai.enter")}
                          </button>
                        </span>
                      )}
                      {entering === field && (
                        <form className="ia-entry" onSubmit={(e) => { e.preventDefault(); void save(() => api.updateInvoice(invoice.id, entered(field), invoice.row_version)); }}>
                          <input
                            aria-label={`${tr("ai.value")} : ${label}`}
                            type={field === "invoice_date" ? "date" : "text"}
                            inputMode={field === "declared_total" ? "decimal" : undefined}
                            maxLength={field === "currency" ? 3 : 200}
                            value={draft}
                            required
                            onChange={(e) => setDraft(e.target.value)}
                          />
                          <button type="submit" className="btn-small" disabled={busy || !draft.trim()}>{tr("save")}</button>
                          <button type="button" className="btn-small" onClick={() => setEntering(null)}>{tr("cancel")}</button>
                        </form>
                      )}
                      {field === "importer" && !importer && editable && (linking ? (
                        <form className="ia-entry" onSubmit={(e) => { e.preventDefault(); void save(linkImporter); }}>
                          <select aria-label={tr("field.linkChoose")} value={importerId} required onChange={(e) => setImporterId(e.target.value)}>
                            <option value="">{tr("field.linkChoose")}</option>
                            {buyerName && !importers.some((i) => sameName(i.name, buyerName)) && <option value="new">{tr("field.linkCreate", { name: buyerName })}</option>}
                            {importers.map((i) => <option key={i.id} value={i.id}>{i.name}</option>)}
                          </select>
                          <button type="submit" className="btn-small" disabled={busy || !importerId}>{tr("save")}</button>
                          <button type="button" className="btn-small" onClick={() => setLinking(false)}>{tr("cancel")}</button>
                        </form>
                      ) : (
                        <span className="ia-note-row">
                          <button type="button" className="btn-small" onClick={startLink}>{tr("field.link")}</button>
                        </span>
                      ))}
                    </dd>
                    <Chip tone={status.tone} icon={status.tone === "amber" ? "alert" : status.tone === "green" ? "checkCircle" : undefined}>{status.label}</Chip>
                  </div>
                );
              })}
            </dl>
            {aiError && <p role="alert" className="error small">⚠ {aiError}</p>}
          </>
        ) : done && run.fields && run.fields.length > 0 ? (
          <DocumentFields
            fields={run.fields}
            onSource={onSource}
            runId={run.id}
            editable={editable}
            onChange={onChange}
          />
        ) : (
          done && reader === "invoice" && <p className="muted small">{tr("extract.noInvoice")}</p>
        )}
      </section>
      {invoice && (
        <section className="card goods-preview" aria-labelledby="goods-preview-title">
          <div className="card-head">
            <h2 id="goods-preview-title" className="card-title">
              {tr("extract.goodsDetail")} <span>{tr("extract.lineCount", { n: invoice.lines.length })}</span>
            </h2>
            <button type="button" className="btn-secondary btn-small" onClick={() => go("donnees")}>{tr("extract.allLines")}</button>
          </div>
          <table className="data compact goods-mini">
            <thead>
              <tr>
                <th scope="col">#</th><th scope="col">{tr("col.description")}</th><th scope="col">{tr("col.hsCode")}</th>
                <th scope="col" className="num">{tr("col.qty")}</th><th scope="col" className="num">{tr("col.unitPrice", { cur: currency })}</th>
                <th scope="col" className="num">{tr("col.amount", { cur: currency })}</th><th scope="col">{tr("col.status")}</th>
              </tr>
            </thead>
            <tbody>
              {invoice.lines.slice(0, PREVIEW_LINES).map((ln) => {
                // Une fois la marchandise décidée (code confirmé), c'est cette décision qui fait foi.
                const goods = ln.goods_line_ids.map((id) => revision.goods_lines.find((g) => g.id === id));
                const decided = goods.length > 0 && goods.every((g) => g?.decision?.is_current);
                const status = decided
                  ? { tone: "green" as Tone, label: tr("field.confirmed") }
                  : fieldStatus(ln.description_raw || ln.amount, ln.entry_origin, (ln.review_flags ?? []).length > 0);
                const code = ln.codes.find((c) => c.code_kind === "customs") ?? ln.codes[0];
                return (
                  <tr key={ln.id}>
                    <td>{ln.ordinal}</td>
                    <td title={ln.description_raw}><span className="line-desc">{ln.description_raw || <em className="muted">{tr("value.unknownF")}</em>}</span></td>
                    <td className="code">{code?.raw_code ?? "—"}</td>
                    <td className="num">{fmtQty(ln.quantity) || "?"}</td>
                    <td className="num">{ln.unit_price ? fmtAmount(ln.unit_price) : "—"}</td>
                    <td className="num">{ln.amount ? fmtAmount(ln.amount) : <em className="muted">{tr("value.unknownM")}</em>}</td>
                    <td><Chip tone={status.tone}>{status.label}</Chip></td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </section>
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
      <h2 id="invoices-title" className="card-title">{tr("inv.title")}</h2>
      <p className="muted small">{tr("inv.intro")}</p>
      {revision.invoices.length === 0 && <p className="empty">{tr("inv.none")}</p>}
      {revision.invoices.map((inv) => (
        <InvoiceBlock key={inv.id} invoice={inv} revision={revision} editable={editable} act={act} />
      ))}
      {editable && (
        <details className="subcard">
          <summary>{tr("inv.manual")}</summary>
          <form className="form-grid" onSubmit={add} aria-label={tr("inv.add")}>
            <label>{tr("field.supplier")}<input value={form.supplier_name} onChange={(e) => setForm({ ...form, supplier_name: e.target.value })} /></label>
            <label>{tr("field.invoiceNo")}<input value={form.invoice_number} onChange={(e) => setForm({ ...form, invoice_number: e.target.value })} /></label>
            <label>{tr("field.date")}<input type="date" value={form.invoice_date} onChange={(e) => setForm({ ...form, invoice_date: e.target.value })} /></label>
            <label>{tr("field.currency")}<input value={form.currency} maxLength={3} onChange={(e) => setForm({ ...form, currency: e.target.value })} placeholder="EUR" /></label>
            <label>{tr("field.printedTotal")}<input inputMode="decimal" value={form.declared_total} onChange={(e) => setForm({ ...form, declared_total: e.target.value })} /></label>
            <label>
              {tr("field.piece")}
              <select value={form.document_id} onChange={(e) => setForm({ ...form, document_id: e.target.value })}>
                <option value="">—</option>
                {invoiceDocs.map((d) => (
                  <option key={d.id} value={d.id}>{d.document.original_name}</option>
                ))}
              </select>
            </label>
            <div className="form-end"><button type="submit" className="btn-secondary">{tr("inv.add")}</button></div>
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
    ["supplier_name", tr("field.supplier"), invoice.supplier_name],
    ["invoice_number", tr("field.number"), invoice.invoice_number],
    ["invoice_date", tr("field.date"), invoice.invoice_date],
    ["currency", tr("field.currency"), invoice.currency],
    ["incoterm", "Incoterm", invoice.incoterm],
    ["declared_total", tr("field.printedTotal"), invoice.declared_total],
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
        {tr("inv.heading", { n: invoice.ordinal })} · {invoice.supplier_name || <em className="muted">{tr("inv.supplierQ")}</em>} ·{" "}
        {invoice.invoice_number || tr("inv.numberQ")} · {invoice.currency || tr("inv.currencyQ")}
        {invoice.declared_total && tr("inv.printedTotalIs", { total: invoice.declared_total })}
      </h3>
      {invoice.latest_extraction_id && (
        <dl className="facts small" aria-label={tr("inv.headerRead", { n: invoice.ordinal })}>
          {headerFields.map(([field, label, value]) => (
            <div key={field} className="fact">
              <dt>{label}</dt>
              <dd>
                {value || <em className="muted">{tr("value.unknownM")}</em>} <OriginBadge origin={origins[field]} source={sources[field]} />
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
                <th scope="col">{tr("col.no")}</th><th scope="col">{tr("col.designation")}</th><th scope="col">{tr("col.supplierRef")}</th>
                <th scope="col">{tr("col.customsCodeRead")}</th><th scope="col">{tr("col.qty")}</th><th scope="col">{tr("col.up")}</th>
                <th scope="col">{tr("col.amountPlain")}</th><th scope="col">{tr("col.origin")}</th><th scope="col">{tr("col.goods")}</th>
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
                          <summary>{tr("inv.corrections", { n: ln.corrections?.length ?? 0 })}</summary>
                          <ul>
                            {ln.corrections?.map((c) => (
                              <li key={c.id}>
                                {tr("inv.correctionBy", { field: c.field, before: String(c.previous.value ?? "—"), after: String(c.current.value ?? "—"), actor: c.actor })}
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
                      {ln.code_history.length > 0 && <div className="muted">{tr("inv.previousValues", { n: ln.code_history.length })}</div>}
                    </td>
                    <td>
                      {ln.quantity ?? <em className="muted">{tr("value.unknownF")}</em>} {ln.unit}{" "}
                      <OriginBadge origin={ln.field_origins?.quantity} source={ln.field_sources?.quantity} />
                    </td>
                    <td>{ln.unit_price ?? "—"}</td>
                    <td>
                      {ln.amount ?? <em className="muted">{tr("value.unknownM")}</em>}{" "}
                      <OriginBadge origin={ln.field_origins?.amount} source={ln.field_sources?.amount} />
                    </td>
                    <td>{ln.origin_country || "—"}</td>
                    <td>
                      {ln.goods_line_ids.length > 0 ? (
                        tr("inv.linked")
                      ) : editable ? (
                        <button type="button" className="btn-small" onClick={() => void act(() => api.addGoods(revision.id, [ln.id]))}>{tr("inv.prepare")}</button>
                      ) : (
                        "—"
                      )}
                      {editable && (
                        <button type="button" className="link" onClick={() => setEditing(editing === ln.id ? null : ln.id)}>
                          {tr("inv.correct")}
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
          <summary>{tr("inv.addLineManual")}</summary>
          <form className="form-grid small" onSubmit={add} aria-label={tr("inv.addLineTo", { n: invoice.ordinal })}>
            <label>{tr("col.designation")}<input value={line.description_raw} onChange={(e) => setLine({ ...line, description_raw: e.target.value })} /></label>
            <label>{tr("field.supplierItemRef")}<input value={line.source_reference} onChange={(e) => setLine({ ...line, source_reference: e.target.value })} /></label>
            <label>{tr("col.customsCodeRead")}<input className="code" value={line.customs_code} onChange={(e) => setLine({ ...line, customs_code: e.target.value })} placeholder="0101.10.00" /></label>
            <label>{tr("field.fieldTitle")}<input value={line.customs_code_label} onChange={(e) => setLine({ ...line, customs_code_label: e.target.value })} /></label>
            <label>{tr("col.qty")}<input inputMode="decimal" value={line.quantity} onChange={(e) => setLine({ ...line, quantity: e.target.value })} /></label>
            <label>{tr("field.unit")}<input value={line.unit} onChange={(e) => setLine({ ...line, unit: e.target.value })} /></label>
            <label>{tr("col.up")}<input inputMode="decimal" value={line.unit_price} onChange={(e) => setLine({ ...line, unit_price: e.target.value })} /></label>
            <label>{tr("col.amountPlain")}<input inputMode="decimal" value={line.amount} onChange={(e) => setLine({ ...line, amount: e.target.value })} /></label>
            <label>{tr("col.origin")}<input maxLength={2} value={line.origin_country} onChange={(e) => setLine({ ...line, origin_country: e.target.value })} placeholder="FR" /></label>
            <label>
              {tr("field.sourcePiece")}
              <select value={line.evidence_document_id} onChange={(e) => setLine({ ...line, evidence_document_id: e.target.value })}>
                <option value="">—</option>
                {docs.map((d) => (
                  <option key={d.id} value={d.id}>{d.document.original_name}</option>
                ))}
              </select>
            </label>
            <label>{tr("field.page")}<input type="number" min={1} value={line.evidence_page} onChange={(e) => setLine({ ...line, evidence_page: e.target.value })} /></label>
            <div className="form-end"><button type="submit" className="btn-secondary">{tr("inv.addLine")}</button></div>
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

/** Filtres de statut : comparés au libellé de goodsStatus, dans la langue affichée. */
const STATUS_FILTERS: MessageKey[] = ["common.all", "goods.validated", "goods.toValidate", "goods.toVerify", "goods.toCheck", "goods.toRecheck", "goods.toReview"];

/** Résultat du contrôle, en deux mots sous le code : jamais un taux de confiance inventé. */
function checkBadge(g: GoodsLine): { tone: Tone; text: string } | null {
  const check = g.latest_check;
  if (g.decision?.is_current) return { tone: "green", text: tr("check.confirmed") };
  if (!check) return null;
  if (check.recognition_status === "recognized") return { tone: "green", text: tr("check.inTariff") };
  if (check.recognition_status === "incomplete") return { tone: "amber", text: tr("check.incomplete") };
  return { tone: "red", text: tr("check.notFound") };
}

function GoodsTab({
  revision,
  editions,
  editable,
  act,
  head,
}: {
  revision: Revision;
  editions: EditionOption[];
  editable: boolean;
  act: Act;
  head: ReactNode;
}) {
  const goods = revision.goods_lines;
  const lines = lineIndex(revision);
  const [selectedId, setSelectedId] = useState<string | null>(goods[0]?.id ?? null);
  const [panel, setPanel] = useState(true);
  const [checked, setChecked] = useState<Set<string>>(new Set());
  const [search, setSearch] = useState("");
  const [filter, setFilter] = useState<MessageKey>("common.all");
  const [menu, setMenu] = useState<string | null>(null);
  const [more, setMore] = useState(false);
  const selected = goods.find((g) => g.id === selectedId) ?? goods[0] ?? null;
  const freeInvoices = revision.invoices.filter((i) => i.lines.some((ln) => ln.goods_line_ids.length === 0));
  const freeCount = freeInvoices.reduce((n, i) => n + i.lines.filter((ln) => ln.goods_line_ids.length === 0).length, 0);
  const statuses = new Map(goods.map((g) => [g.id, goodsStatus(g)]));
  const all = [...statuses.values()];
  const validated = all.filter((s) => s.label === tr("goods.validated")).length;
  const toValidate = all.filter((s) => s.label === tr("goods.toValidate")).length;
  const toCheck = all.filter((s) => s.tone === "amber" || s.tone === "red").length - toValidate;
  const noCheck = all.filter((s) => s.label === tr("goods.toCheck")).length;
  const recognized = goods.filter((g) => g.latest_check?.recognition_status === "recognized" || g.decision?.is_current).length;
  const editionId = revision.target_edition?.id ?? editions[0]?.id ?? "";
  const currencies = [...new Set([...lines.values()].map((l) => l.currency).filter(Boolean))];
  const shown = goods.filter((g) => {
    const s = statuses.get(g.id)!;
    if (filter !== "common.all" && s.label !== tr(filter)) return false;
    const q = search.trim().toLowerCase();
    return !q || g.description.toLowerCase().includes(q) || s.code.includes(q);
  });
  const targets = checked.size ? goods.filter((g) => checked.has(g.id)) : goods;
  const checkAll = () => act(async () => {
    for (const g of targets) await api.checkCode(g.id, editionId);
  });

  function toggle(id: string) {
    const next = new Set(checked);
    if (next.has(id)) next.delete(id);
    else next.add(id);
    setChecked(next);
  }

  return (
    <div className={`goods-page${panel ? "" : " goods-page-full"}`}>
      <div className="goods-main">
        {head}
        <div className="goods-actions">
          {editable && (
            <button
              type="button"
              className="btn-primary"
              disabled={freeCount === 0}
              title={freeCount === 0 ? tr("goods.allHaveGoods") : undefined}
              onClick={() => void act(async () => {
                for (const inv of freeInvoices) await api.goodsFromInvoice(inv.id);
              })}
            >
              <Icon name="plus" size={18} /> {tr("goods.prepareAll")}{freeCount ? ` (${freeCount})` : ""}
            </button>
          )}
          {editable && (
            <button type="button" className="btn-secondary" disabled={!goods.length || !editionId} onClick={() => void checkAll()}>
              <Icon name="search" size={18} /> {checked.size ? tr("goods.checkSelection", { n: checked.size }) : tr("goods.checkAll")}
            </button>
          )}
          <button type="button" className="btn-secondary" onClick={() => navigate("/recherche")}>
            <Icon name="book" size={18} /> {tr("goods.consultTariff")}
          </button>
          <span className="menu-wrap">
            <button type="button" className="btn-secondary goods-more" aria-label={tr("goods.moreActions")} aria-expanded={more} onClick={() => setMore(!more)}>
              <Icon name="more" size={18} className="rotate-90" />
            </button>
            {more && (
              <ul className="menu" role="menu">
                <li role="menuitem"><button type="button" onClick={() => { setMore(false); setPanel(!panel); }}>{panel ? tr("goods.hideProposal") : tr("goods.showProposal")}</button></li>
                <li role="menuitem"><button type="button" onClick={() => { setMore(false); setChecked(new Set()); setFilter("common.all"); setSearch(""); }}>{tr("goods.resetList")}</button></li>
              </ul>
            )}
          </span>
        </div>

        <section className="card goods-list" aria-labelledby="goods-title">
          <div className="card-head">
            <h2 id="goods-title" className="card-title">{tr("goods.listTitle", { n: goods.length })}</h2>
            <div className="table-tools">
              <label className="search-mini">
                <Icon name="search" size={15} />
                <input aria-label={tr("goods.searchLabel")} placeholder={tr("goods.searchPlaceholder")} value={search} onChange={(e) => setSearch(e.target.value)} />
              </label>
              <label className="filter-mini">
                <Icon name="filter" size={15} />
                <select aria-label={tr("goods.filterLabel")} value={filter} onChange={(e) => setFilter(e.target.value as MessageKey)}>
                  {STATUS_FILTERS.map((f) => (
                    <option key={f} value={f}>{f === "common.all" ? tr("goods.filter") : tr(f)}</option>
                  ))}
                </select>
              </label>
            </div>
          </div>
          {goods.length === 0 ? (
            <p className="empty">
              {tr("goods.none")} {freeCount ? tr("goods.linesCanPrepare", { n: freeCount }) : tr("goods.fromLines")}
            </p>
          ) : (
            <div className="goods-scroll">
              <table className="data selectable goods-table">
                <thead>
                  <tr>
                    <th scope="col">
                      <input
                        type="checkbox"
                        aria-label={tr("goods.selectAll")}
                        checked={checked.size === goods.length && goods.length > 0}
                        onChange={(e) => setChecked(e.target.checked ? new Set(goods.map((g) => g.id)) : new Set())}
                      />
                    </th>
                    <th scope="col">#</th>
                    <th scope="col">{tr("col.description")}</th>
                    <th scope="col">{tr("col.quantity")}</th>
                    <th scope="col">{tr("col.value", { cur: currencies.length === 1 ? ` (${currencies[0]})` : "" })}</th>
                    <th scope="col">{tr("col.code")}</th>
                    <th scope="col">{tr("col.status")}</th>
                    <th scope="col"><span className="visually-hidden">{tr("col.actions")}</span></th>
                  </tr>
                </thead>
                <tbody>
                  {shown.map((g) => {
                    const s = statuses.get(g.id)!;
                    const f = goodsFigures(g, lines);
                    const badge = checkBadge(g);
                    return (
                      <tr key={g.id} className={selected?.id === g.id ? "selected" : undefined} onClick={() => { setSelectedId(g.id); setPanel(true); }}>
                        <td onClick={(e) => e.stopPropagation()}>
                          <input type="checkbox" aria-label={tr("goods.selectOne", { n: g.ordinal })} checked={checked.has(g.id)} onChange={() => toggle(g.id)} />
                        </td>
                        <td>{g.ordinal}</td>
                        <td>
                          <div className="goods-cell">
                            <span className="goods-thumb"><Icon name="box" size={24} /></span>
                            <span className="goods-desc">
                              <button type="button" className="row-button" onClick={() => setSelectedId(g.id)}>
                                {g.description || <em className="muted">{tr("goods.designationQ")}</em>}
                              </button>
                              {f.reference && <small>{tr("goods.ref", { ref: f.reference })}</small>}
                              <small>{tr("goods.originIs", { origin: g.origin_country || tr("value.unknownF") })}</small>
                            </span>
                          </div>
                        </td>
                        <td className="goods-qty">{f.qty ? <>{f.qty}<small>{f.unit || tr("goods.unitQ")}</small></> : <em className="muted">{tr("value.unknownF")}</em>}</td>
                        <td className="goods-value">
                          {f.value ? <>{f.value}{currencies.length !== 1 && <small>{f.currency}</small>}</> : <em className="muted">{tr("value.unknownF")}</em>}
                        </td>
                        <td className="goods-code">
                          <span className="code">{s.code || "—"}</span>
                          {badge && <Chip tone={badge.tone} icon={badge.tone === "green" ? "checkCircle" : "alert"}>{badge.text}</Chip>}
                        </td>
                        <td><Chip tone={s.tone} icon={s.tone === "amber" ? "alert" : s.tone === "green" ? "check" : undefined}>{s.label}</Chip></td>
                        <td className="menu-wrap" onClick={(e) => e.stopPropagation()}>
                          <button type="button" className="kebab" aria-label={tr("goods.actionsFor", { n: g.ordinal })} onClick={() => setMenu(menu === g.id ? null : g.id)}>
                            <Icon name="more" size={18} />
                          </button>
                          {menu === g.id && (
                            <ul className="menu menu-right" role="menu">
                              <li role="menuitem"><button type="button" onClick={() => { setMenu(null); setSelectedId(g.id); setPanel(true); }}>{tr("goods.seeProposal")}</button></li>
                              {editable && editionId && (
                                <li role="menuitem"><button type="button" onClick={() => { setMenu(null); void act(() => api.checkCode(g.id, editionId)); }}>{tr("goods.checkCode")}</button></li>
                              )}
                              <li role="menuitem"><button type="button" onClick={() => navigate(`/recherche?q=${encodeURIComponent(s.code || g.description)}`)}>{tr("goods.consultTariff")}</button></li>
                            </ul>
                          )}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}
          <p className="goods-note">{tr("goods.note")}</p>
        </section>

        <section className="card goods-summary" aria-labelledby="goods-summary">
          <h2 id="goods-summary" className="card-title">{tr("goods.summary")}</h2>
          <div className="goods-tiles">
            <div className="goods-tile">
              <span className="tile-icon tile-green"><Icon name="box" size={20} /></span>
              <span><strong>{goods.length}</strong><b>{tr("goods.tileGoods")}</b><small>{tr("goods.tileGoodsSub", { v: validated, f: freeCount })}</small></span>
            </div>
            <div className="goods-tile">
              <span className="tile-icon tile-blue"><Icon name="search" size={20} /></span>
              <span><strong>{goods.length ? `${recognized} / ${goods.length}` : "—"}</strong><b>{tr("goods.tileCodes")}</b><small>{tr("goods.tileCodesSub", { n: noCheck })}</small></span>
            </div>
            <div className="goods-tile">
              <span className="tile-icon tile-amber"><Icon name="alert" size={20} /></span>
              <span><strong>{toCheck + toValidate}</strong><b>{tr("goods.tileToVerify")}</b><small>{tr("goods.tileToVerifySub", { n: toValidate })}</small></span>
            </div>
            <div className="goods-tile">
              <span className="tile-icon tile-green-solid"><Icon name="check" size={20} /></span>
              <span><strong>{validated}</strong><b>{tr("goods.tileValidated")}</b><small>{tr("goods.tileValidatedSub")}</small></span>
            </div>
          </div>
        </section>
      </div>
      {panel && (
        <section className="card goods-panel" aria-label={tr("goods.proposal")}>
          <div className="card-head">
            <h2 className="card-title">{tr("goods.proposal")}</h2>
            <button type="button" className="icon-button" aria-label={tr("goods.closeProposal")} onClick={() => setPanel(false)}>
              <Icon name="x" size={18} />
            </button>
          </div>
          {selected ? (
            <GoodsCard key={selected.id} goods={selected} revision={revision} lines={lines} editions={editions} editable={editable} act={act} />
          ) : (
            <p className="empty">{tr("goods.selectPrompt")}</p>
          )}
        </section>
      )}
    </div>
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
        <h3>{tr("rates.title")}</h3>
        <span title={tr("rates.raw")}><Icon name="info" size={17} /></span>
      </div>
      {items.length === 0 ? (
        <p className="muted small">{tr("rates.none")}</p>
      ) : (
        <table className="data compact">
          <tbody>
            {items.map((r) => (
              <tr key={r.column}>
                <td>{r.column}</td>
                <td className="num">{r.raw_value || <em className="muted">{tr("rates.empty")}</em>}</td>
              </tr>
            ))}
            <tr className="total-row">
              <td>{tr("rates.total")}</td>
              <td className="num">{tr("rates.notCalculated")}</td>
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

  const recheck = editable && (
    <div className="check-row">
      <label>
        {tr("gc.checkAgainst")}
        <select value={edition} onChange={(e) => setEdition(e.target.value)}>
          {editions.map((e) => (
            <option key={e.id} value={e.id}>{e.label}</option>
          ))}
        </select>
      </label>
      <button type="button" className="btn-secondary" disabled={!edition} onClick={() => void act(() => api.checkCode(goods.id, edition))}>
        {tr("gc.checkPresent")}
      </button>
    </div>
  );

  return (
    <div className="goods-card" aria-label={tr("gc.goods", { n: goods.ordinal })}>
      <div className="goods-head">
        <span className="goods-photo"><Icon name="box" size={34} /></span>
        <div>
          <strong>{goods.description || <em className="muted">{tr("goods.designationQ")}</em>}</strong>
          <dl className="mini-facts">
            <div><dt>{tr("col.quantity", {})}</dt><dd>{f.qty ? `${f.qty} ${f.unit}` : tr("value.unknownF")}</dd></div>
            <div><dt>{tr("gc.value")}</dt><dd>{f.value ? `${f.value} ${f.currency}` : tr("value.unknownF")}</dd></div>
            <div><dt>{tr("col.origin")}</dt><dd>{goods.origin_country || tr("value.unknownF")}</dd></div>
            <div><dt>{tr("gc.source")}</dt><dd>{goods.sources.map((s) => tr("gc.invoiceLine", { i: s.invoice_ordinal, l: s.line_ordinal })).join(", ")}</dd></div>
          </dl>
        </div>
      </div>

      <div className="code-box">
        <div className="card-head">
          <span>{decision ? tr("gc.codeValidated") : check?.node ? tr("gc.codeInTariff") : tr("gc.codeOnInvoice")}</span>
          <Chip tone={status.tone}>{status.label}</Chip>
        </div>
        {shownCode ? (
          <div className="code-line">
            <span className="code big-code">{shownCode}</span>
            <button type="button" className="icon-button" onClick={copy} title={tr("gc.copy")}>
              <Icon name="copy" size={17} />
              <span className="visually-hidden">{tr("gc.copy")}</span>
            </button>
            {copied && <span className="muted small">{tr("gc.copied")}</span>}
          </div>
        ) : (
          <p className="big-line muted">{tr("gc.noCode")}</p>
        )}
        {check?.node && <p className="code-path">{check.node.full_path}</p>}
        {decision && (
          <p className="code-path">
            {tr("gc.decisionBy", { action: decision.action_label, edition: decision.edition.label, who: decision.actor.email, date: fmtDateTime(decision.at) })}{" "}
            {tr("gc.reasonIs", { reason: decision.reason })}
            {!decision.is_current && tr("gc.decisionStale")}
          </p>
        )}
      </div>

      {check ? (
        <details className="check-result" open aria-label={tr("gc.checkResult")}>
          <summary>
            <span>{tr("gc.findings")}</span>
            <Icon name="chevronDown" size={16} />
          </summary>
          <div className="check-title">
            <strong>{check.recognition_label}</strong>
            <span className="muted small">{CONFIRMATION[check.human_confirmation] ? tr(CONFIRMATION[check.human_confirmation]) : check.human_confirmation}</span>
          </div>
          {check.observed_code && (
            <p className="muted small">
              {tr("gc.readIn", { code: check.observed_code, field: check.observed_field ?? "", edition: check.target_edition_label, date: fmtDateTime(check.checked_at) })}
            </p>
          )}
          <ul className="check-list">
            {check.findings.map((x) => (
              <li key={x.code + x.message} className={`sev-${x.severity}`}>
                <Icon name={x.severity === "info" ? "info" : x.severity === "error" || x.severity === "blocking" ? "alert" : "checkCircle"} size={16} />
                {x.message}
              </li>
            ))}
          </ul>
        </details>
      ) : (
        recheck
      )}
      <p className="goods-warning">
        <Icon name="alert" size={20} />
        {tr("gc.warning")}
      </p>
      {check && editable && check.is_current && check.recognition_status === "recognized" && check.human_confirmation === "pending" && (
        <form className="decide-form" onSubmit={(e) => { e.preventDefault(); decide("confirm"); }}>
          <label>
            {tr("gc.confirmReason")}
            <input required value={reason} onChange={(e) => setReason(e.target.value)} placeholder={tr("gc.confirmPlaceholder")} />
          </label>
          <button type="submit" className="btn-primary btn-block">
            <Icon name="check" size={18} /> {tr("gc.validate")}
          </button>
        </form>
      )}
      {check && editable && check.is_current && check.recognition_status === "incomplete" && subdivisions.length > 0 && (
        <form className="decide-form" onSubmit={(e) => { e.preventDefault(); decide("complete"); }}>
          <label>
            {tr("gc.subdivision")}
            <select required value={subdivision} onChange={(e) => setSubdivision(e.target.value)}>
              <option value="">{tr("gc.choose")}</option>
              {subdivisions.map((s) => (
                <option key={s.id} value={s.id}>{s.code_display} {s.label}</option>
              ))}
            </select>
          </label>
          <label>
            {tr("gc.reason")}
            <input required value={reason} onChange={(e) => setReason(e.target.value)} />
          </label>
          <button type="submit" className="btn-primary btn-block">{tr("gc.complete")}</button>
        </form>
      )}
      <div className="actions-row two">
        <button type="button" className="btn-secondary" onClick={() => document.getElementById(`proposals-${goods.id}`)?.setAttribute("open", "")}>
          <Icon name="edit" size={17} /> {tr("gc.change")}
        </button>
        <button type="button" className="btn-secondary" onClick={() => navigate(`/recherche?q=${encodeURIComponent(shownCode || goods.description)}`)}>
          <Icon name="external" size={17} /> {tr("goods.consultTariff")}
        </button>
      </div>
      {check?.node && <TariffRates nodeId={check.node.id} />}
      {check && recheck}
      {(editable || goods.latest_check) && (
        <details id={`proposals-${goods.id}`} open={Boolean(check && check.recognition_status !== "recognized")} className="proposals-box">
          <summary>{tr("gc.otherCodes")}</summary>
          <ProposalsPanel goods={goods} editionId={edition} editable={editable} act={act} />
        </details>
      )}
    </div>
  );
}

// ---- Calculs, validation, export : ce qui existe, et ce qui manque encore -----------------------

const unknown = (text = tr("value.unknownM")) => <em className="muted">{text}</em>;

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
  const label = { blocking: tr("sev.blocking"), review: tr("sev.review"), ok: tr("sev.ok"), info: tr("sev.info") };
  return (
    <section className="card" aria-labelledby="alerts-title">
      <div className="card-head">
        <h2 id="alerts-title" className="card-title">{tr("alerts.title")}</h2>
        <button type="button" className="link-arrow" onClick={() => go("controles")}>{tr("alerts.all")} <Icon name="arrowRight" size={14} /></button>
      </div>
      {items.length === 0 ? (
        <p className="empty">{tr("alerts.none")}</p>
      ) : (
        <ul className="alert-list">
          {items.map((i) => (
            <li key={i.id} className={`alert-${tone[i.severity]}`}>
              <span className={`cat cat-${tone[i.severity]}`}><Icon name={i.severity === "ok" ? "checkCircle" : i.severity === "info" ? "info" : "alert"} size={18} /></span>
              <span>
                <strong>{i.category}</strong>
                <small>{i.title}</small>
                <button type="button" className="link-arrow small" onClick={() => go(i.tab)}>{tr("alerts.detail")} <Icon name="arrowRight" size={14} /></button>
              </span>
              <Chip tone={tone[i.severity]}>{label[i.severity]}</Chip>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}

function Calculation({ detail, membership, act, go }: { detail: CaseDetail; membership: Membership; act: Act; go: (tab: string) => void }) {
  const revision = detail.revision;
  const { data: calc, failed } = useCaseCalculation(detail.id, detail);
  const totalTaxes = calc?.totals.total ?? null;
  const knownTotal = calc?.totals.known_total && calc.totals.known_total !== "0" ? calc.totals.known_total : null;
  const freightInsurance = calc ? sumPieces(calc) : null;
  const total = invoiceTotals(revision);
  const goodsValue = invoiceSum(revision, (i) => i.totals_check?.components.goods);
  const fees = invoiceSum(revision, (i) => i.totals_check?.components.fees);
  const incoterms = [...new Set(revision.invoices.map((i) => i.incoterm).filter(Boolean))].join(", ");
  const goods = revision.goods_lines;
  const codes = goods.map((g) => g.decision?.is_current ? g.decision.selected_code_display : null).filter(Boolean);
  const origins = [...new Set(goods.map((g) => g.origin_country).filter(Boolean))].join(", ");
  const units = [...new Set(revision.invoices.flatMap((i) => i.lines.map((l) => l.unit)).filter(Boolean))].join(", ");
  return (
    <div className="section-layout">
      <div>
        <section className="card calc-card" aria-labelledby="calc-title">
          <div className="card-head">
            <h2 id="calc-title" className="card-title">{tr("calc.title")}</h2>
            <span className="calc-currency">{tr("calc.currencyNote", { cur: "" })}<strong>{calc ? "FCFA" : tr("calc.invoiceCurrency")}</strong></span>
          </div>
          {calc?.frozen && calc.frozen_at && <p className="note-blue small">{tr("val.frozen", { date: fmtDateTime(calc.frozen_at) })}</p>}
          <div className="stats stats-4 flat calc-stats">
            <StatCard icon="box" tone="green" label={tr("calc.goodsValue")} value={goodsValue || tr("calc.unknownF")} hint={tr("calc.goodsValueHint")} />
            <StatCard icon="truck" tone="blue" label={tr("calc.fees")} value={fees || tr("calc.unknownPl")} hint={tr("calc.feesHint")} />
            <StatCard icon="file" tone="blue" label={tr("calc.invoiceTotal")} value={total || tr("value.unknownM")} hint={incoterms ? tr("calc.printedWith", { inc: incoterms }) : tr("calc.printedTotal")} />
            <StatCard
              icon="calculator"
              tone={calc?.total_value ? "green" : "gray"}
              label={tr("calc.base")}
              value={calc?.total_value ? `${xaf(calc.total_value)} FCFA` : tr("calc.notCalculatedF")}
              hint={calc?.provisional && calc.total_value ? tr("fx.provisionalValue") : tr("calc.customsValue")}
            />
          </div>
          <h3 className="calc-h3">{tr("calc.taxesTitle")}</h3>
          {calc ? <CalcTaxesTable calc={calc} /> : <p className="muted">{failed ? tr("fx.loadError") : tr("loading")}</p>}
          <div className="total-band">
            <span>{tr("calc.totalTaxes")}</span>
            <strong>
              {totalTaxes !== null ? `${xaf(totalTaxes)} FCFA` : knownTotal ? `${xaf(knownTotal)} FCFA` : tr("calc.notCalculatedM")}
              {totalTaxes === null && knownTotal && <span className="tx-prov small"> {tr("fx.incomplete")}</span>}
              {totalTaxes !== null && calc?.provisional && <span className="tx-prov small"> {tr("fx.provisional")}</span>}
            </strong>
          </div>
          {calc && <CalcNotes calc={calc} />}
          {calc && calc.articles.length > 0 && <CalcLinesTable calc={calc} />}
          <div className="calc-bottom">
          <section aria-labelledby="recap-title">
            <h2 id="recap-title" className="calc-h3">{tr("calc.recap")}</h2>
            <dl className="recap">
              <div><dt>{tr("calc.goodsValueLines")}</dt><dd>{goodsValue || unknown()}</dd></div>
              <div><dt>{tr("calc.fees")}</dt><dd>{fees || unknown()}</dd></div>
              <div><dt>{tr("calc.printedInvoiceTotal")}</dt><dd>{total || unknown()}</dd></div>
              <div><dt>{tr("calc.freightInsurance")}</dt><dd>{freightInsurance ? `${xaf(freightInsurance)} FCFA` : unknown(tr("calc.toConfirm"))}</dd></div>
              <div><dt>{tr("calc.customsValueCap")}</dt><dd>{calc?.total_value ? `${xaf(calc.total_value)} FCFA` : unknown(tr("calc.notCalculatedF"))}</dd></div>
              <div><dt>{tr("calc.totalTaxesShort")}</dt><dd>{totalTaxes !== null ? `${xaf(totalTaxes)} FCFA` : unknown(tr("calc.notCalculatedM"))}</dd></div>
              {calc?.totals.other_accounts && "TCI" in calc.totals.other_accounts && (
                <div>
                  <dt>{tr("calc.tciAccount2")}</dt>
                  <dd>{calc.totals.other_accounts.TCI !== null ? `${xaf(calc.totals.other_accounts.TCI)} FCFA` : unknown(tr("calc.notCalculatedF"))}</dd>
                </div>
              )}
            </dl>
            <div className="total-band">
              <span>{tr("calc.totalToPay")}</span>
              <strong>{totalTaxes !== null ? `${xaf(totalTaxes)} FCFA` : tr("calc.notCalculatedM")}</strong>
            </div>
          </section>
          <section className="calc-more" aria-labelledby="more-title">
            <h2 id="more-title">{tr("calc.more")}</h2>
            <dl className="recap icons">
              <div><dt><Icon name="tag" size={16} /> {tr("calc.tariffPosition")}</dt><dd>{codes.length ? codes.join(", ") : unknown(goods.length ? tr("calc.toValidate") : tr("calc.noGoods"))}</dd></div>
              <div><dt><Icon name="file" size={16} /> {tr("calc.regime")}</dt><dd>{revision.regime || unknown(tr("case.toFill"))}</dd></div>
              <div><dt><Icon name="mapPin" size={16} /> {tr("calc.originCountry")}</dt><dd>{origins || revision.origin_country || unknown()}</dd></div>
              <div><dt><Icon name="ship" size={16} /> {tr("calc.shipCountry")}</dt><dd>{revision.provenance_country || unknown()}</dd></div>
              <div><dt><Icon name="scale" size={16} /> {tr("calc.unit")}</dt><dd>{units || unknown()}</dd></div>
              <div><dt><Icon name="box" size={16} /> {tr("calc.items")}</dt><dd>{goods.length}</dd></div>
              <div><dt><Icon name="layers" size={16} /> {tr("calc.packages")}</dt><dd>{unknown(tr("calc.packingNotRead"))}</dd></div>
            </dl>
          </section>
          </div>
        </section>
      </div>
      <div className="section-side">
        <SideAlerts detail={detail} go={go} />
        <ValidationActions detail={detail} membership={membership} act={act} go={go} />
      </div>
    </div>
  );
}

/** Fret et assurance ajoutés à la valeur, en FCFA ; null si rien n'est ajouté. */
function sumPieces(calc: CaseCalculation): string | null {
  const parts = calc.articles.flatMap((a) => [a.value.freight, a.value.insurance]).filter((v): v is string => !!v);
  return parts.length ? String(parts.reduce((a, v) => a + Number(v), 0)) : null;
}

function CalcNotes({ calc }: { calc: CaseCalculation }) {
  const complete = calc.totals.total !== null;
  return (
    <div className="calc-note-stack">
      {calc.provisional && (
        <p className="note-amber small" role="note">
          <Icon name="info" size={15} /> <strong>{tr("fx.provisionalCap")}</strong> : {calc.provisional_reasons.join(" ")}{" "}
          {calc.articles.some((a) => a.value.notes.length) && tr("fx.seeLines")}
        </p>
      )}
      {!complete && calc.totals.known_total && calc.totals.known_total !== "0" && (
        <p className="note-amber small" role="note">
          {tr("fx.partial", { amount: `${xaf(calc.totals.known_total)} FCFA` })}
        </p>
      )}
      <p className="calc-note">
        <Icon name="info" size={15} />{" "}
        {tr("fx.calcNote", {
          version: calc.taxes_version,
          schedule: calc.schedule?.label ?? tr("fx.noSchedule"),
          date: fmtDate(calc.date),
        })}{" "}
        {calc.notes.TCI && tr("fx.tciNote")} {tr("fx.internalNote")}
      </p>
    </div>
  );
}

export function ValidationActions({ detail, membership, act, go }: { detail: CaseDetail; membership: Membership; act: Act; go: (tab: string) => void }) {
  const rev = detail.revision;
  const [reason, setReason] = useState("");
  const canSubmit = rev.is_editable && membership.roles.some((r) => r === "declarant" || r === "validator" || r === "org_admin");
  const canDecide = rev.state === "to_validate" && membership.roles.some((r) => r === "validator" || r === "org_admin");
  const canRevise = membership.roles.some((r) => r === "declarant" || r === "validator" || r === "org_admin");
  const blocking = rev.completeness.blocking.length;
  const run = (action: "submit" | "return" | "validate") =>
    void act(async () => {
      await api.workflow(detail.id, action, rev.row_version, reason.trim());
      setReason("");
    });
  return (
    <section className="card" aria-labelledby="val-actions">
      <h2 id="val-actions" className="card-title">{tr("val.actions")}</h2>
      <div className="action-stack">
        {canSubmit && (
          <button type="button" className="btn-primary btn-block btn-row" disabled={blocking > 0} onClick={() => run("submit")}>
            <Icon name="upload" /> <span>{tr("val.submit")}<small>{blocking > 0 ? tr("pre.blockingN", { n: blocking }) : tr("val.submitHint")}</small></span> <Icon name="arrowRight" />
          </button>
        )}
        {rev.state === "to_validate" && (canDecide ? (
          <>
            <label className="block small">
              {tr("val.comment")}
              <textarea rows={2} value={reason} maxLength={2000} onChange={(e) => setReason(e.target.value)} />
            </label>
            <button type="button" className="btn-primary btn-block btn-row" onClick={() => run("validate")}>
              <Icon name="check" /> <span>{tr("val.validateCase")}</span> <Icon name="arrowRight" />
            </button>
            <button type="button" className="btn-secondary btn-block btn-row" disabled={!reason.trim()} onClick={() => run("return")}>
              <Icon name="message" /> <span>{tr("val.requestCorrection")}<small>{tr("val.returnReason")}</small></span> <Icon name="arrowRight" />
            </button>
          </>
        ) : (
          <p className="muted small">{tr("val.waiting")} {tr("val.onlyValidator")}</p>
        ))}
        {rev.state === "validated" && <p className="note-blue small">{tr("val.done")}</p>}
        {rev.state === "validated" && canRevise && (
          <>
            <label className="block small">
              {tr("val.revisionReason")}
              <textarea rows={2} value={reason} maxLength={2000} onChange={(e) => setReason(e.target.value)} />
            </label>
            <button
              type="button"
              className="btn-secondary btn-block btn-row"
              disabled={!reason.trim()}
              onClick={() =>
                void act(async () => {
                  await api.createRevision(detail.id, reason.trim());
                  setReason("");
                })
              }
            >
              <Icon name="edit" /> <span>{tr("val.newRevision")}<small>{tr("val.newRevisionHint")}</small></span> <Icon name="arrowRight" />
            </button>
          </>
        )}
        <button type="button" className="btn-secondary btn-block btn-row" onClick={() => go("export")}>
          <Icon name="upload" /> <span>{tr("val.prepareExport")}<small>{tr("val.prereqFiles")}</small></span> <Icon name="arrowRight" />
        </button>
      </div>
      {(rev.decisions?.length ?? 0) > 0 && (
        <>
          <h3 className="extracted-sub">{tr("val.decisions")}</h3>
          <ul className="small">
            {rev.decisions!.map((d) => (
              <li key={d.created_at + d.kind}>
                {tr("val.decisionBy", { kind: d.kind_label, name: d.actor.full_name || d.actor.email, date: fmtDateTime(d.created_at) })}
                {d.reason && <> : « {d.reason} »</>}
              </li>
            ))}
          </ul>
        </>
      )}
      <p className="muted small">{tr("val.circuit", { state: stateLabel(rev.state, rev.state_label) })}</p>
      <p className="note-blue small">{tr("val.internalOnly")}</p>
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
    { ok: docs > 0, title: tr("pre.docs"), detail: tr("pre.docsDetail"), value: tr("step.pieces", { n: docs }), tab: "documents", link: tr("pre.seeDocs") },
    { ok: goods > 0 && decided === goods, title: tr("pre.classif"), detail: tr("pre.classifDetail"), value: `${decided} / ${goods}`, tab: "marchandises", link: tr("pre.seeClassif") },
    { ok: rev.state === "validated" ? true : null, title: tr("pre.calc"), detail: tr("pre.calcDetail"), value: rev.state === "validated" ? tr("val.frozenShort") : tr("val.upToDate"), tab: "calculs", link: tr("pre.seeCalc") },
    { ok: blocking === 0, title: tr("pre.controls"), detail: tr("pre.controlsDetail"), value: blocking ? tr("pre.blockingN", { n: blocking }) : tr("sev.ok"), tab: "controles", link: tr("actions.seeControls") },
    { ok: rev.state === "validated", title: tr("pre.manager"), detail: tr("pre.managerDetail"), value: stateLabel(rev.state, rev.state_label), tab: "historique", link: tr("actions.seeHistory") },
  ] as { ok: boolean | null; title: string; detail: string; value: string; tab: string; link: string }[];
}

function Prerequisites({ detail, kind, go }: { detail: CaseDetail; kind: "validation" | "export"; go: (tab: string) => void }) {
  const rows = prerequisites(detail);
  const ready = rows.every((r) => r.ok);
  return (
    <section className="card" aria-labelledby="final-title">
      <div className="card-head">
        <h2 id="final-title" className="card-title">{kind === "export" ? tr("pre.exportTitle") : tr("pre.validationTitle")}</h2>
        <Chip tone={ready ? "green" : "amber"} icon={ready ? "checkCircle" : "clock"}>
          {ready ? tr("pre.ready") : tr("pre.count", { done: rows.filter((r) => r.ok).length, total: rows.length })}
        </Chip>
      </div>
      <p className="muted small">
        {ready ? tr("pre.allMet") : tr("pre.eachLinks")}
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
  // Une cellule commençant par =, +, - ou @ serait lue comme une formule par un tableur.
  const esc = (v: string) => `"${(/^[=+\-@\t\r]/.test(v) ? `'${v}` : v).replace(/"/g, '""')}"`;
  const rows = events.map((e) => [e.at, eventLabel(e.event_type), e.event_type, e.actor ?? tr("activity.system")].map(esc).join(";"));
  return [tr("csv.header"), ...rows].join("\n");
}

function saveFile(name: string, content: string | Blob, type: string) {
  const blob = typeof content === "string" ? new Blob(["﻿" + content], { type }) : content;
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = name;
  a.click();
  URL.revokeObjectURL(url);
}

function ExportPage({ detail, act, go }: { detail: CaseDetail; act: Act; go: (tab: string) => void }) {
  const rev = detail.revision;
  const docs = rev.documents.filter((d) => !d.replaced_by_id);
  const currencies = [...new Set(rev.invoices.map((i) => i.currency).filter(Boolean))].join(", ");
  const [exports, setExports] = useState<CaseExport[] | null>(null);
  const validated = rev.state === "validated" || rev.state === "archived";
  const stem = `${detail.reference}_r${rev.revision_no}${validated ? "" : "_brouillon"}`;

  const loadExports = useCallback(() => {
    api.caseExports(detail.id).then((r) => setExports(r.results), () => setExports([]));
  }, [detail.id]);
  useEffect(loadExports, [loadExports, rev.row_version]);

  async function downloadAudit() {
    const r = await api.caseAudit(detail.id);
    saveFile(`${detail.reference}_journal.csv`, auditCsv(r.results), "text/csv;charset=utf-8");
  }
  async function downloadDoc(id: string) {
    const { url } = await api.documentLink(id);
    window.location.assign(url);
  }
  async function downloadExport(e: CaseExport) {
    saveFile(e.filename, await api.exportFile(detail.id, e.id), "");
  }
  const generate = (formats: ("pdf" | "xlsx")[]) =>
    void act(async () => {
      for (const f of formats) await downloadExport(await api.createExport(detail.id, f));
      loadExports();
    });

  return (
    <div className="grid-2-1">
      <div>
        <Prerequisites detail={detail} kind="export" go={go} />
        <section className="card" aria-labelledby="file-title">
          <div className="card-head">
            <h2 id="file-title" className="card-title">{tr("export.file")}</h2>
            <Chip tone="gray" icon="clock">{tr("export.soon")}</Chip>
          </div>
          <div className="export-file">
            <span className="export-icon"><Icon name="fileSheet" size={34} /></span>
            <dl className="recap">
              <div><dt>{tr("export.fileName")}</dt><dd>{unknown(tr("export.generatedAtExport"))}</dd></div>
              <div><dt>{tr("export.format")}</dt><dd>{unknown(tr("export.formatToConfirm"))}</dd></div>
              <div><dt>{tr("export.generatedOn")}</dt><dd>—</dd></div>
              <div><dt>{tr("export.generatedBy")}</dt><dd>—</dd></div>
            </dl>
          </div>
          <p className="muted small">{tr("export.noPromise")}</p>
        </section>
        <section className="card" aria-labelledby="final-docs">
          <h2 id="final-docs" className="card-title">{tr("export.finalDocs")}</h2>
          <p className="muted small">{tr("export.finalDocsHelp")}</p>
          <div className="final-docs">
            <div className="final-doc">
              <span className="doc-type doc-pdf">PDF</span>
              <strong>{tr("export.summary")}</strong>
              <small>{stem}.pdf</small>
              <button type="button" className="btn-secondary btn-block" onClick={() => generate(["pdf"])}><Icon name="download" size={16} /> {tr("common.download")}</button>
            </div>
            <div className="final-doc">
              <span className="doc-type doc-xls">XLS</span>
              <strong>{tr("export.dutyDetail")}</strong>
              <small>{stem}.xlsx</small>
              <button type="button" className="btn-secondary btn-block" onClick={() => generate(["xlsx"])}><Icon name="download" size={16} /> {tr("common.download")}</button>
            </div>
            <div className="final-doc">
              <span className="doc-type doc-img">CSV</span>
              <strong>{tr("export.auditLog")}</strong>
              <small>{detail.reference}_journal.csv</small>
              <button type="button" className="btn-secondary btn-block" onClick={() => void downloadAudit()}><Icon name="download" size={16} /> {tr("common.download")}</button>
            </div>
            <div className="final-doc">
              <span className="doc-type doc-none"><Icon name="archive" size={16} /></span>
              <strong>{tr("export.caseDocs")}</strong>
              <small>{tr("export.originals", { count: docs.length })}</small>
              {docs.length === 0 ? (
                <button type="button" className="btn-secondary btn-block" disabled>{tr("export.noDoc")}</button>
              ) : (
                <select aria-label={tr("export.downloadDoc")} defaultValue="" onChange={(e) => e.target.value && void downloadDoc(e.target.value)}>
                  <option value="">{tr("export.downloadDoc")}…</option>
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
          <h2 id="export-actions" className="card-title">{tr("export.actions")}</h2>
          <div className="action-stack">
            <button type="button" className="btn-primary btn-block btn-row" onClick={() => generate(["pdf", "xlsx"])}>
              <Icon name="upload" /> <span>{tr("export.generate")}<small>{tr("export.generateHint", { n: rev.revision_no })}</small></span> <Icon name="arrowRight" />
            </button>
            <button type="button" className="btn-secondary btn-block btn-row" disabled>
              <Icon name="download" /> <span>{tr("export.downloadAll")}</span> <Icon name="arrowRight" />
            </button>
            <button type="button" className="btn-secondary btn-block btn-row" disabled>
              <Icon name="check" /> <span>{tr("export.markExported")}</span> <Icon name="arrowRight" />
            </button>
          </div>
          <p className={validated ? "note-blue small" : "note-amber small"}>{tr(validated ? "export.validatedNote" : "export.draftNote")}</p>
          <p className="note-blue small">{tr("export.nextVersion")}</p>
        </section>
        <section className="card" aria-labelledby="export-history">
          <h2 id="export-history" className="card-title">{tr("export.history")}</h2>
          {exports === null ? (
            <p className="muted">{tr("loading")}</p>
          ) : exports.length === 0 ? (
            <p className="empty">{tr("export.noExport")}</p>
          ) : (
            <ul className="export-history">
              {exports.map((e) => (
                <li key={e.id}>
                  <button type="button" className="link-arrow" onClick={() => void act(() => downloadExport(e))}>
                    <Icon name="download" size={14} /> {e.filename}
                  </button>
                  <small>
                    {tr("export.revisionN", { n: e.revision_no })} · {e.marking_label} · {fmtDateTime(e.created_at)} · {e.created_by}
                  </small>
                </li>
              ))}
            </ul>
          )}
        </section>
        <section className="card" aria-labelledby="export-info">
          <h2 id="export-info" className="card-title">{tr("export.moreInfo")}</h2>
          <dl className="recap">
            <div><dt>{tr("export.targetSystem")}</dt><dd>{unknown(tr("calc.toConfirm"))}</dd></div>
            <div><dt>{tr("export.declType")}</dt><dd>{tr("export.import")}</dd></div>
            <div><dt>{tr("export.territory")}</dt><dd>{territory(rev.territory)}</dd></div>
            <div><dt>{tr("export.office")}</dt><dd>{rev.entry_office || unknown(tr("case.toFill"))}</dd></div>
            <div><dt>{tr("export.transport")}</dt><dd>{rev.transport_mode_label || unknown(tr("case.toFill"))}</dd></div>
            <div><dt>{tr("calc.regime")}</dt><dd>{rev.regime || unknown(tr("case.toFill"))}</dd></div>
            <div><dt>{tr("field.currency")}</dt><dd>{currencies || unknown()}</dd></div>
            <div><dt>{tr("export.lineCount")}</dt><dd>{rev.goods_lines.length}</dd></div>
            <div><dt>{tr("export.grossWeight")}</dt><dd>{unknown()}</dd></div>
          </dl>
        </section>
      </div>
    </div>
  );
}

const CIRCUIT: [MessageKey, MessageKey, string[]][] = [
  ["circuit.prep", "circuit.prepText", ["draft", "in_preparation", "to_correct"]],
  ["circuit.submit", "circuit.submitText", ["to_validate"]],
  ["circuit.internal", "circuit.internalText", ["validated", "archived"]],
];

function ValidationPage({ detail, membership, act, go }: { detail: CaseDetail; membership: Membership; act: Act; go: (tab: string) => void }) {
  return (
    <div className="grid-2-1">
      <div>
        <Prerequisites detail={detail} kind="validation" go={go} />
        <section className="card" aria-labelledby="circuit-title">
          <h2 id="circuit-title" className="card-title">{tr("circuit.title")}</h2>
          <ol className="circuit">
            {CIRCUIT.map(([title, text, states]) => (
              <li key={title} className={states.includes(detail.revision.state) ? "current" : undefined}>
                <strong>{tr(title)}</strong>
                <small>{tr(text)}</small>
              </li>
            ))}
          </ol>
          <p className="muted small">{tr("circuit.current", { state: stateLabel(detail.revision.state, detail.revision.state_label) })}</p>
        </section>
      </div>
      <div>
        <ValidationActions detail={detail} membership={membership} act={act} go={go} />
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
      <h2 id="history-title" className="card-title">{tr("history.title", { count: events?.length ?? 0 })}</h2>
      {events === null ? (
        <p className="muted">{tr("loading")}</p>
      ) : events.length === 0 ? (
        <p className="empty">{tr("history.none")}</p>
      ) : (
        <ol className="timeline">
          {events.map((e) => (
            <li key={e.id}>
              <span className="activity-icon"><Icon name={eventIcon(e.event_type)} size={16} /></span>
              <span>
                <strong>{eventLabel(e.event_type)}</strong>
                <small>{e.actor ?? tr("activity.system")}</small>
              </span>
              <time dateTime={e.at}>{fmtDateTime(e.at)}</time>
            </li>
          ))}
        </ol>
      )}
    </section>
  );
}
