// Numérisation (NUM-01 à NUM-08) : lots du scanner et photos, découpés en pièces avant rattachement.
// Mêmes cartes, boutons et couleurs que le reste de l'application.
import { useCallback, useEffect, useRef, useState, type ReactNode } from "react";
import {
  api,
  scanPageImage,
  type CaseDetail,
  type Membership,
  type ScanBatch,
  type ScanBatchSummary,
  type ScanPageInfo,
  type ScanPiece,
} from "./api";
import { USAGES } from "./CaseDetail";
import { Icon } from "./Icon";
import { navigate, rememberCase } from "./router";
import { tr, type MessageKey } from "./i18n";
import { Chip, errorText, fmtDateTime, PageHeader, personName, ProgressBar, StatCard, type Tone } from "./ui";

const SCANNER_ACCEPT = ".pdf,.tif,.tiff,.png,.jpg,.jpeg";
const POLL_MS = 1500;

/** « p. 4 », « p. 4 et 5 », « p. 1 à 3 », ou la liste si les pages ne se suivent pas. */
export function pageRange(numbers: number[]): string {
  const n = [...numbers].sort((a, b) => a - b);
  if (n.length === 0) return tr("scan.noPage");
  const consecutive = n.every((v, i) => i === 0 || v === n[i - 1] + 1);
  if (n.length === 1) return tr("scan.p1", { a: n[0] });
  if (consecutive) return n.length === 2 ? tr("scan.p2", { a: n[0], b: n[1] }) : tr("scan.pRange", { a: n[0], b: n[n.length - 1] });
  return tr("scan.pList", { list: n.join(", ") });
}

/** « 1 pièce », « 3 pièces » : deux textes, au singulier et au pluriel, dans la langue affichée. */
const plural = (n: number, one: MessageKey, many: MessageKey) => tr(n > 1 ? many : one, { n });

function isWorking(batch: ScanBatchSummary): boolean {
  return batch.state === "processing" || batch.counts.pending > 0 || batch.job?.state === "queued" || batch.job?.state === "running";
}

function progressValue(batch: ScanBatchSummary): number {
  const { done = 0, total = 0 } = batch.job?.progress ?? {};
  return total ? Math.round((100 * Number(done)) / Number(total)) : 0;
}

/** Avancement d'un lot, en mots. */
export function batchProgress(batch: ScanBatchSummary): { tone: Tone; text: string } {
  const c = batch.counts;
  if (batch.state === "attached") return { tone: "green", text: tr("scan.attachedState", { pieces: plural(c.pieces, "scan.piece1", "scan.pieceN") }) };
  if (batch.state === "cancelled") return { tone: "gray", text: tr("scan.cancelled") };
  if (batch.job?.state === "failed") return { tone: "red", text: batch.job.error_message ?? tr("scan.readFailed") };
  if (isWorking(batch)) {
    const { done, total } = batch.job?.progress ?? {};
    return { tone: "blue", text: total ? tr("scan.readingPage", { done: done ?? 0, total }) : tr("scan.reading") };
  }
  if (batch.state === "open") return { tone: "blue", text: tr("scan.shooting", { pages: plural(c.pages, "scan.page1", "scan.pageN") }) };
  if (c.unclassified > 0) return { tone: "amber", text: tr("scan.toSort", { pages: plural(c.unclassified, "scan.unclassified1", "scan.unclassifiedN") }) };
  return { tone: "green", text: tr("scan.checkAttach") };
}

/** Bouton qui ouvre le sélecteur de fichiers (ou l'appareil photo du téléphone). */
function FileButton({
  className,
  label,
  accept,
  multiple,
  camera,
  disabled,
  onFiles,
  children,
}: {
  className: string;
  label: string;
  accept: string;
  multiple?: boolean;
  camera?: boolean;
  disabled?: boolean;
  onFiles: (files: File[]) => void;
  children: ReactNode;
}) {
  const input = useRef<HTMLInputElement>(null);
  return (
    <>
      <button type="button" className={className} disabled={disabled} onClick={() => input.current?.click()}>
        {children}
      </button>
      <input
        ref={input}
        type="file"
        className="visually-hidden"
        tabIndex={-1}
        aria-label={label}
        accept={accept}
        multiple={multiple}
        capture={camera ? "environment" : undefined}
        onChange={(e) => {
          const files = Array.from(e.target.files ?? []);
          e.target.value = "";
          if (files.length) onFiles(files);
        }}
      />
    </>
  );
}

function Thumb({ page, selected, onSelect }: { page: ScanPageInfo; selected: boolean; onSelect: () => void }) {
  const flagged = page.hard_to_read || page.state === "failed";
  return (
    <button
      type="button"
      className={`scan-thumb${selected ? " selected" : ""}${flagged ? " flagged" : ""}`}
      aria-pressed={selected}
      title={flagged ? tr("scan.hardRead") : page.title || undefined}
      onClick={onSelect}
    >
      {page.has_image ? (
        <img src={scanPageImage(page)} alt={tr("scan.pageN1", { n: page.number ?? "" })} loading="lazy" />
      ) : (
        <span className="scan-thumb-empty">{page.state === "pending" ? tr("scan.thumbReading") : tr("scan.unreadable")}</span>
      )}
      {tr("scan.p1", { a: page.number ?? "" })}
    </button>
  );
}

function pageStatus(page: ScanPageInfo): { tone: Tone; text: string } {
  if (page.removed) return { tone: "gray", text: page.removed_label };
  if (page.state === "pending") return { tone: "blue", text: tr("scan.reading") };
  if (page.state === "failed") return { tone: "red", text: tr("scan.unreadableRedo") };
  if (page.hard_to_read) return { tone: "amber", text: tr("scan.hardRedo") };
  return { tone: "green", text: page.text_origin === "ocr" ? tr("scan.textOcr") : tr("scan.text") };
}

/** Écrans de numérisation d'un dossier : #/dossiers/:id/numerisation[/:lot[/photos]]. */
export function ScanScreens({ caseId, rest, membership }: { caseId: string; rest: string[]; membership: Membership }) {
  const [detail, setDetail] = useState<CaseDetail | null>(null);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    rememberCase(caseId);
    api.caseDetail(caseId).then(setDetail, (err) => setError(errorText(err, tr("case.notFound"))));
  }, [caseId]);
  if (!detail) return <p className="muted">{error ?? tr("loading")}</p>;
  const editable = membership.roles.some((r) => r === "declarant" || r === "validator") && detail.revision.is_editable;
  const [batchId, sub] = rest;
  if (batchId && sub === "photos") return <Capture key={batchId} detail={detail} batchId={batchId} editable={editable} />;
  if (batchId) return <SortBatch key={batchId} detail={detail} batchId={batchId} editable={editable} />;
  return <AddPieces detail={detail} editable={editable} />;
}

function Breadcrumb({ detail, last }: { detail: CaseDetail; last?: string }) {
  const base = `/dossiers/${detail.id}`;
  return (
    <nav className="breadcrumb" aria-label={tr("nav.breadcrumb")}>
      <button type="button" className="link" onClick={() => navigate("/dossiers")}>{tr("nav.myCases")}</button>
      <Icon name="chevronRight" size={14} />
      <button type="button" className="link" onClick={() => navigate(`${base}/apercu`)}>{detail.reference}</button>
      <Icon name="chevronRight" size={14} />
      <button type="button" className="link" onClick={() => navigate(`${base}/documents`)}>{tr("tab.documents")}</button>
      {last && (
        <>
          <Icon name="chevronRight" size={14} />
          <span>{last}</span>
        </>
      )}
    </nav>
  );
}

const onLocalMachine = () => ["localhost", "127.0.0.1", "[::1]"].includes(window.location.hostname);

function PhoneNote() {
  return onLocalMachine() ? (
    <p className="note-blue small">
      {tr("scan.phoneLocal")}
    </p>
  ) : (
    <p className="note-blue small">
      {tr("scan.phoneOpen", { url: window.location.href })}
    </p>
  );
}

// ---- Ajouter les pièces : scanner, téléphone ou webcam, fichiers déjà prêts ---------------------

function AddPieces({ detail, editable }: { detail: CaseDetail; editable: boolean }) {
  const [batches, setBatches] = useState<ScanBatchSummary[] | null>(null);
  const [maxPages, setMaxPages] = useState<number | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const base = `/dossiers/${detail.id}`;

  const load = useCallback(async () => {
    const page = await api.scanBatches(detail.id);
    setBatches(page.results);
    setMaxPages(page.max_pages);
  }, [detail.id]);

  useEffect(() => {
    load().catch((err) => setError(errorText(err, tr("scan.batchesUnavailable"))));
  }, [load]);

  useEffect(() => {
    if (!batches?.some(isWorking)) return;
    const timer = setTimeout(() => void load().catch(() => undefined), POLL_MS);
    return () => clearTimeout(timer);
  }, [batches, load]);

  async function scanner(files: File[]) {
    setBusy(true);
    setError(null);
    try {
      const label = files.length === 1 ? files[0].name : tr(files.length > 2 ? "scan.andOthersN" : "scan.andOthers1", { name: files[0].name, n: files.length - 1 });
      const batch = await api.createScanBatch(detail.id, "scanner", label.slice(0, 200));
      await api.addScanFiles(batch.id, files);
      navigate(`${base}/numerisation/${batch.id}`);
    } catch (err) {
      setError(errorText(err, tr("scan.uploadFailed")));
      await load().catch(() => undefined);
    } finally {
      setBusy(false);
    }
  }

  async function camera() {
    setBusy(true);
    setError(null);
    try {
      const batch = await api.createScanBatch(detail.id, "camera");
      navigate(`${base}/numerisation/${batch.id}/photos`);
    } catch (err) {
      setError(errorText(err, tr("scan.cameraFailed")));
    } finally {
      setBusy(false);
    }
  }

  const visible = (batches ?? []).filter((b) => b.state !== "cancelled");

  return (
    <div className="scan-page">
      <Breadcrumb detail={detail} />
      <PageHeader
        title={tr("scan.addTitle")}
        subtitle={<>{tr("scan.caseRef", { ref: detail.reference })}{detail.importer && <> · {detail.importer.name}</>} · {detail.revision.mode_label}</>}
      >
        <button type="button" className="btn-secondary" onClick={() => navigate(`${base}/documents`)}>
          <Icon name="file" size={18} /> {tr("scan.seeDocs")}
        </button>
      </PageHeader>
      {error && <p role="alert" className="error">⚠ {error}</p>}
      {!editable && <p className="note-amber small">{tr("scan.readOnly")}</p>}

      <div className="scan-ways">
        <section className="card" aria-labelledby="way-scanner">
          <div className="card-head">
            <h2 id="way-scanner" className="card-title">{tr("scan.scannerBatch")}</h2>
            <Chip tone="green">{tr("scan.recommended")}</Chip>
          </div>
          <p className="muted">
            {tr("scan.scannerText")}
          </p>
          <p className="muted small">{tr("scan.formats")}{maxPages ? tr("scan.maxPages", { n: maxPages }) : ""}.</p>
          <FileButton
            className="btn-primary btn-block"
            label={tr("scan.batchFiles")}
            accept={SCANNER_ACCEPT}
            multiple
            disabled={!editable || busy}
            onFiles={(files) => void scanner(files)}
          >
            <Icon name="cloudUpload" /> {busy ? tr("scan.sending") : tr("scan.chooseFiles")}
          </FileButton>
        </section>

        <section className="card" aria-labelledby="way-camera">
          <div className="card-head">
            <h2 id="way-camera" className="card-title">{tr("scan.phone")}</h2>
            <Chip tone="gray">{tr("scan.noScanner")}</Chip>
          </div>
          <p className="muted">
            {tr("scan.phoneText")}
          </p>
          <PhoneNote />
          <button type="button" className="btn-primary btn-block" disabled={!editable || busy} onClick={() => void camera()}>
            <Icon name="eye" /> {tr("scan.startShooting")}
          </button>
        </section>

        <section className="card" aria-labelledby="way-files">
          <div className="card-head">
            <h2 id="way-files" className="card-title">{tr("scan.readyFiles")}</h2>
            <Chip tone="gray">{tr("scan.asToday")}</Chip>
          </div>
          <p className="muted">
            {tr("scan.readyText")}
          </p>
          <button type="button" className="btn-secondary btn-block" onClick={() => navigate(`${base}/documents`)}>
            <Icon name="plus" /> {tr("scan.addFiles")}
          </button>
        </section>
      </div>

      <section className="card" aria-labelledby="batches-title">
        <h2 id="batches-title" className="card-title">{tr("scan.batchesTitle")}</h2>
        {batches === null ? (
          <p className="muted">{tr("loading")}</p>
        ) : visible.length === 0 ? (
          <p className="empty">{tr("scan.noBatch")}</p>
        ) : (
          <div className="table-wrap">
            <table className="data">
              <thead>
                <tr>
                  <th>{tr("scan.batch")}</th>
                  <th>{tr("scan.source")}</th>
                  <th className="num">{tr("scan.pages")}</th>
                  <th>{tr("scan.progress")}</th>
                  <th>{tr("scan.action")}</th>
                </tr>
              </thead>
              <tbody>
                {visible.map((b) => {
                  const progress = batchProgress(b);
                  const photos = b.source === "camera" && b.state === "open";
                  return (
                    <tr key={b.id}>
                      <td>
                        <strong>{b.label}</strong>
                        <div className="muted small">{personName(b.created_by)} · {fmtDateTime(b.created_at)}</div>
                      </td>
                      <td>{b.source_label}</td>
                      <td className="num">{b.counts.pages}</td>
                      <td>
                        <Chip tone={progress.tone}>{progress.text}</Chip>
                        {isWorking(b) && <div><ProgressBar value={progressValue(b)} /></div>}
                      </td>
                      <td>
                        <button
                          type="button"
                          className="btn-small"
                          onClick={() => navigate(`${base}/numerisation/${b.id}${photos ? "/photos" : ""}`)}
                        >
                          {photos ? tr("scan.continueShooting") : b.state === "to_sort" ? tr("scan.sortBatch") : tr("scan.open")}
                        </button>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
        <p className="muted small">
          {tr("scan.tip")}
        </p>
      </section>
    </div>
  );
}

// ---- Suivi d'un lot (lecture puis tri) -----------------------------------------------------------

function useBatch(batchId: string) {
  const [batch, setBatch] = useState<ScanBatch | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      setBatch(await api.scanBatch(batchId));
    } catch (err) {
      setError(errorText(err, tr("scan.batchNotFound")));
    }
  }, [batchId]);

  useEffect(() => {
    void load();
  }, [load]);

  useEffect(() => {
    if (!batch || !isWorking(batch)) return;
    const timer = setTimeout(() => void load(), POLL_MS);
    return () => clearTimeout(timer);
  }, [batch, load]);

  /** Une action renvoie le lot à jour ; une erreur est montrée sans perdre l'affichage. */
  const act = useCallback(async (action: () => Promise<ScanBatch>) => {
    setError(null);
    try {
      setBatch(await action());
      return true;
    } catch (err) {
      setError(errorText(err, tr("common.actionFailed")));
      await load();
      return false;
    }
  }, [load]);

  return { batch, error, act };
}

function SortBatch({ detail, batchId, editable }: { detail: CaseDetail; batchId: string; editable: boolean }) {
  const { batch, error, act } = useBatch(batchId);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const base = `/dossiers/${detail.id}`;

  if (!batch) return <p className="muted">{error ?? tr("loading")}</p>;
  if (batch.state === "attached") return <AttachResult detail={detail} batch={batch} />;

  const working = isWorking(batch);
  const canEdit = editable && (batch.state === "to_sort" || batch.state === "open" || batch.state === "processing");
  const kept = batch.pages.filter((p) => !p.removed);
  const byId = new Map(batch.pages.map((p) => [p.id, p]));
  const pieces = batch.pieces.filter((p) => p.page_ids.length > 0);
  const unclassified = kept.filter((p) => !p.piece_id);
  const removed = batch.pages.filter((p) => p.removed);
  const selected =
    (selectedId && byId.get(selectedId)) ||
    kept.find((p) => p.hard_to_read || p.state === "failed") ||
    unclassified[0] ||
    kept[0] ||
    null;
  const c = batch.counts;
  const read = kept.filter((p) => p.state !== "pending").length;

  return (
    <div className="scan-page">
      <Breadcrumb detail={detail} last={tr("scan.batchLabel", { label: batch.label })} />
      <PageHeader
        title={tr("scan.sortTitle", { pages: plural(c.pages, "scan.page1", "scan.pageN"), pieces: plural(pieces.length, "scan.proposed1", "scan.proposedN") })}
        subtitle={tr("scan.uploadedBy", { source: batch.source_label, label: batch.label, who: personName(batch.created_by), date: fmtDateTime(batch.created_at) })}
      >
        {canEdit && batch.source === "scanner" && (
          <FileButton
            className="btn-secondary"
            label={tr("scan.pagesToAdd")}
            accept={SCANNER_ACCEPT}
            multiple
            disabled={working}
            onFiles={(files) => void act(() => api.addScanFiles(batch.id, files))}
          >
            <Icon name="plus" size={18} /> {tr("scan.addPages")}
          </FileButton>
        )}
        {canEdit && batch.source === "camera" && (
          <button type="button" className="btn-secondary" onClick={() => navigate(`${base}/numerisation/${batch.id}/photos`)}>
            <Icon name="plus" size={18} /> {tr("scan.addPhotos")}
          </button>
        )}
        {canEdit && (
          <button
            type="button"
            className="btn-primary"
            disabled={working || pieces.length === 0}
            onClick={() => void act(() => api.scanAction(batch.id, "attach"))}
          >
            <Icon name="check" size={18} /> {tr("scan.attach", { pieces: plural(pieces.length, "scan.piece1", "scan.pieceN") })}
          </button>
        )}
      </PageHeader>
      {error && <p role="alert" className="error">⚠ {error}</p>}

      <div className="stats stats-4">
        <StatCard icon="layers" tone="blue" label={tr("scan.received")} value={c.pages} hint={plural(batch.sources.length, "scan.file1", "scan.fileN")} />
        <StatCard
          icon="eye"
          tone={working ? "blue" : "green"}
          label={tr("scan.straightened")}
          value={`${read} / ${kept.length}`}
          hint={working ? <ProgressBar value={progressValue(batch)} /> : tr("scan.readDone")}
        />
        <StatCard
          icon="file"
          tone={c.unclassified || c.hard_to_read ? "amber" : "green"}
          label={tr("scan.split")}
          value={plural(pieces.length, "scan.piece1", "scan.pieceN")}
          hint={[
            c.unclassified ? plural(c.unclassified, "scan.toClassify1", "scan.toClassifyN") : null,
            c.hard_to_read ? plural(c.hard_to_read, "scan.toRedo1", "scan.toRedoN") : null,
            c.blank_removed ? plural(c.blank_removed, "scan.blank1", "scan.blankN") : null,
          ].filter(Boolean).join(", ") || tr("scan.nothing")}
        />
        <StatCard icon="checkCircle" tone="gray" label={tr("scan.yourCheck")} value={batch.state_label} hint={tr("scan.nothingAttached")} />
      </div>

      <div className="split-panel">
        <div>
          {pieces.length === 0 && !working && <p className="empty card">{tr("scan.noPiece")}</p>}
          {pieces.map((piece, index) => (
            <PieceCard
              key={piece.id}
              piece={piece}
              index={index}
              pages={piece.page_ids.map((id) => byId.get(id)).filter((p): p is ScanPageInfo => !!p)}
              selectedId={selected?.id ?? null}
              onSelect={setSelectedId}
              editable={canEdit}
              act={act}
            />
          ))}
          {unclassified.length > 0 && (
            <section className="card" aria-labelledby="unclassified-title">
              <div className="card-head">
                <h2 id="unclassified-title" className="card-title">{tr("scan.unclassifiedTitle")}</h2>
                <Chip tone="amber">{plural(unclassified.length, "scan.page1", "scan.pageN")}</Chip>
              </div>
              <p className="muted small">{tr("scan.unclassifiedHelp")}</p>
              <div className="scan-thumbs">
                {unclassified.map((p) => (
                  <Thumb key={p.id} page={p} selected={selected?.id === p.id} onSelect={() => setSelectedId(p.id)} />
                ))}
              </div>
            </section>
          )}
          {removed.length > 0 && (
            <details className="card small">
              <summary>{plural(removed.length, "scan.removed1", "scan.removedN")}</summary>
              <div className="scan-thumbs">
                {removed.map((p) => (
                  <Thumb key={p.id} page={p} selected={selected?.id === p.id} onSelect={() => setSelectedId(p.id)} />
                ))}
              </div>
            </details>
          )}
          {canEdit && (
            <p className="small">
              <button type="button" className="link" onClick={() => void act(() => api.scanAction(batch.id, "cancel")).then((ok) => ok && navigate(`${base}/numerisation`))}>
                {tr("scan.abandon")}
              </button>{" "}
              <span className="muted">{tr("scan.filesKept")}</span>
            </p>
          )}
        </div>
        <aside className="side-panel">
          {selected ? (
            <PageAside
              key={selected.id}
              page={selected}
              pieces={pieces}
              allPieces={batch.pieces}
              editable={canEdit}
              act={act}
            />
          ) : (
            <section className="card"><p className="empty">{working ? tr("scan.readingPages") : tr("scan.noPageFull")}</p></section>
          )}
        </aside>
      </div>
    </div>
  );
}

type BatchAct = (action: () => Promise<ScanBatch>) => Promise<boolean>;

function UsageSelect({ value, onChange, label, disabled }: { value: string; onChange: (v: string) => void; label: string; disabled?: boolean }) {
  return (
    <label className="inline">
      {label}
      <select value={value} disabled={disabled} onChange={(e) => onChange(e.target.value)}>
        {USAGES.map(([v, l]) => (
          <option key={v} value={v}>{tr(l)}</option>
        ))}
      </select>
    </label>
  );
}

function PieceCard({
  piece,
  index,
  pages,
  selectedId,
  onSelect,
  editable,
  act,
}: {
  piece: ScanPiece;
  index: number;
  pages: ScanPageInfo[];
  selectedId: string | null;
  onSelect: (id: string) => void;
  editable: boolean;
  act: BatchAct;
}) {
  return (
    <section className="card scan-piece" aria-labelledby={`piece-${piece.id}`}>
      <div className="card-head">
        <h2 id={`piece-${piece.id}`} className="card-title">{tr("scan.pieceN1", { n: index + 1 })}</h2>
        <UsageSelect
          label={tr("scan.type")}
          value={piece.usage}
          disabled={!editable}
          onChange={(usage) => void act(() => api.updateScanPiece(piece.id, usage))}
        />
        <Chip tone="gray">{pageRange(pages.map((p) => p.number ?? 0))}</Chip>
      </div>
      <p className="muted small">{piece.usage_by_user ? tr("scan.typeByAgent") : tr("scan.proposedReason", { reason: piece.reason })}</p>
      <div className="scan-thumbs">
        {pages.map((p) => (
          <Thumb key={p.id} page={p} selected={selectedId === p.id} onSelect={() => onSelect(p.id)} />
        ))}
      </div>
      {editable && index > 0 && (
        <div className="actions-row">
          <button type="button" className="btn-small" onClick={() => void act(() => api.joinScanPiece(piece.id))}>
            {tr("scan.joinPrevious")}
          </button>
        </div>
      )}
    </section>
  );
}

function PageAside({
  page,
  pieces,
  allPieces,
  editable,
  act,
}: {
  page: ScanPageInfo;
  pieces: ScanPiece[];
  allPieces: ScanPiece[];
  editable: boolean;
  act: BatchAct;
}) {
  const status = pageStatus(page);
  const piece = allPieces.find((p) => p.id === page.piece_id) ?? null;
  const pieceIndex = piece ? pieces.findIndex((p) => p.id === piece.id) : -1;
  const firstOfPiece = piece ? piece.page_ids[0] === page.id : false;
  const [newUsage, setNewUsage] = useState("other");

  function move(target: string) {
    if (!target) return;
    if (target === "none") void act(() => api.updateScanPage(page.id, { piece_id: null }));
    else if (target === "new") void act(() => api.updateScanPage(page.id, { piece_id: "new", usage: newUsage }));
    else void act(() => api.updateScanPage(page.id, { piece_id: target }));
  }

  return (
    <section className="card" aria-labelledby="page-title">
      <div className="card-head">
        <h2 id="page-title" className="card-title">{tr("scan.pageN1", { n: page.number ?? "" })}</h2>
        <Chip tone={status.tone}>{status.text}</Chip>
      </div>
      {page.has_image ? (
        <img className="scan-preview" src={scanPageImage(page, false)} alt={tr("scan.pageOfBatch", { n: page.number ?? "" })} />
      ) : (
        <p className="empty">{page.state === "pending" ? tr("scan.readingEllipsis") : tr("scan.noImage")}</p>
      )}
      <ul className="plain small">
        <li>{tr("scan.fromFile", { name: page.source_name, page: page.source_page })}</li>
        {piece && <li>{tr("scan.inPiece", { n: pieceIndex + 1, usage: piece.usage_label })}</li>}
        {page.title && <li>{tr("scan.titleRead", { title: page.title })}{page.reference && tr("scan.refNo", { ref: page.reference })}</li>}
        {page.page_marker && <li>{tr("scan.markerRead", { marker: page.page_marker })}</li>}
        {page.notes.map((n) => <li key={n} className="muted">{n}</li>)}
      </ul>
      {(page.hard_to_read || page.state === "failed") && (
        <p className="note-amber small">
          {tr("scan.badText")}
        </p>
      )}
      {editable && (
        <div className="scan-actions">
          <FileButton
            className="btn-secondary"
            label={tr("scan.newTake")}
            accept={SCANNER_ACCEPT}
            camera
            onFiles={([file]) => void act(() => api.replaceScanPage(page.id, file))}
          >
            <Icon name="refresh" size={18} /> {tr("scan.redoPage")}
          </FileButton>
          {page.removed ? (
            <button type="button" className="btn-secondary" onClick={() => void act(() => api.updateScanPage(page.id, { removed: false }))}>
              <Icon name="plus" size={18} /> {tr("scan.putBack")}
            </button>
          ) : (
            <>
              <button
                type="button"
                className="btn-secondary"
                onClick={() => void act(() => api.updateScanPage(page.id, { rotation: (page.rotation + 90) % 360 }))}
              >
                <Icon name="refresh" size={18} /> {tr("scan.rotate")}
              </button>
              {piece && !firstOfPiece && (
                <button type="button" className="btn-secondary" onClick={() => void act(() => api.splitScanPage(page.id))}>
                  <Icon name="minus" size={18} /> {tr("scan.cutHere")}
                </button>
              )}
              {piece && firstOfPiece && pieceIndex > 0 && (
                <button type="button" className="btn-secondary" onClick={() => void act(() => api.joinScanPiece(piece.id))}>
                  <Icon name="layers" size={18} /> {tr("scan.joinPrev")}
                </button>
              )}
              <label>
                {tr("scan.moveTo")}
                <select value="" onChange={(e) => move(e.target.value)}>
                  <option value="">{tr("scan.choose")}</option>
                  {pieces.map((p, i) =>
                    p.id === page.piece_id ? null : (
                      <option key={p.id} value={p.id}>{tr("scan.pieceOption", { n: i + 1, usage: p.usage_label })}</option>
                    ),
                  )}
                  <option value="new">{tr("scan.newPieceBelow")}</option>
                  {page.piece_id && <option value="none">{tr("scan.unclassifiedTitle")}</option>}
                </select>
              </label>
              <UsageSelect label={tr("scan.newPieceType")} value={newUsage} onChange={setNewUsage} />
              <button type="button" className="btn-secondary" onClick={() => void act(() => api.updateScanPage(page.id, { removed: true }))}>
                <Icon name="x" size={18} /> {tr("scan.removeFromBatch")}
              </button>
            </>
          )}
        </div>
      )}
      <p className="muted small">{tr("scan.typesProposed")}</p>
    </section>
  );
}

// ---- Résultat : les pièces rattachées, avec leur provenance --------------------------------------

function AttachResult({ detail, batch }: { detail: CaseDetail; batch: ScanBatch }) {
  const numbers = new Map(batch.pages.map((p) => [p.id, p.number ?? 0]));
  const attached = batch.pieces.filter((p) => p.case_document);
  const reading = attached.filter((p) => p.case_document?.latest_extraction).length;
  const left = batch.counts.unclassified;
  const base = `/dossiers/${detail.id}`;
  return (
    <div className="scan-page">
      <Breadcrumb detail={detail} last={tr("scan.batchLabel", { label: batch.label })} />
      <PageHeader title={tr("scan.caseDocs")}>
        <button type="button" className="btn-secondary" onClick={() => navigate(`${base}/numerisation`)}>
          <Icon name="plus" size={18} /> {tr("scan.addOrScan")}
        </button>
        <button type="button" className="btn-primary" onClick={() => navigate(`${base}/documents`)}>
          <Icon name="file" size={18} /> {tr("scan.openDocs")}
        </button>
      </PageHeader>
      <p className="note-blue">
        {tr("scan.fromBatch", { attached: plural(attached.length, "scan.attached1", "scan.attachedN"), label: batch.label })}
        {left > 0 && plural(left, "scan.left1", "scan.leftN")}
        {reading > 0 && plural(reading, "scan.reading1", "scan.readingN")}
      </p>
      <section className="card" aria-label={tr("scan.attachedPieces")}>
        <div className="table-wrap">
          <table className="data">
            <thead>
              <tr>
                <th>{tr("scan.piece")}</th>
                <th>{tr("scan.type")}</th>
                <th className="num">{tr("scan.pages")}</th>
                <th>{tr("scan.origin")}</th>
                <th>{tr("scan.readingCol")}</th>
              </tr>
            </thead>
            <tbody>
              {attached.map((p) => {
                const link = p.case_document!;
                const run = link.latest_extraction;
                return (
                  <tr key={p.id}>
                    <td><strong>{link.document.original_name}</strong></td>
                    <td>{link.usage_label}</td>
                    <td className="num">{p.page_ids.length}</td>
                    <td>{tr("scan.scannedFrom", { label: batch.label, pages: pageRange(p.page_ids.map((id) => numbers.get(id) ?? 0)) })}</td>
                    <td>
                      {run ? (
                        <Chip tone={run.status === "failed" ? "red" : run.status === "succeeded" ? "green" : "blue"}>{run.status_label}</Chip>
                      ) : (
                        <span className="muted">{tr("scan.notRequested")}</span>
                      )}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
        <p className="muted small">
          {tr("scan.keepsOrigin")}
        </p>
      </section>
    </div>
  );
}

// ---- Prise de vue : téléphone (appareil photo) ou webcam -----------------------------------------

function Capture({ detail, batchId, editable }: { detail: CaseDetail; batchId: string; editable: boolean }) {
  const { batch, error, act } = useBatch(batchId);
  const [usage, setUsage] = useState("invoice");
  const [pieceId, setPieceId] = useState<string | null>(null);
  const [sending, setSending] = useState(false);
  const [webcam, setWebcam] = useState<MediaStream | null>(null);
  const [camError, setCamError] = useState<string | null>(null);
  const video = useRef<HTMLVideoElement>(null);
  const base = `/dossiers/${detail.id}`;

  useEffect(() => {
    if (video.current && webcam) video.current.srcObject = webcam;
    return () => webcam?.getTracks().forEach((t) => t.stop());
  }, [webcam]);

  if (!batch) return <p className="muted">{error ?? tr("loading")}</p>;
  if (batch.state !== "open") {
    return (
      <div className="scan-page">
        <Breadcrumb detail={detail} last={tr("scan.batchLabel", { label: batch.label })} />
        <p className="note-blue">{tr("scan.shootDone")}</p>
        <button type="button" className="btn-primary" onClick={() => navigate(`${base}/numerisation/${batch.id}`)}>{tr("scan.sortBatch")}</button>
      </div>
    );
  }

  const current = batch.pieces.find((p) => p.id === pieceId) ?? null;
  const byId = new Map(batch.pages.map((p) => [p.id, p]));
  const pieces = batch.pieces.filter((p) => p.page_ids.length > 0);

  async function send(file: Blob) {
    setSending(true);
    const ok = await act(async () => {
      const result = await api.addScanPhoto(batchId, file, current ? { piece_id: current.id } : { usage });
      const page = result.batch.pages.find((p) => p.id === result.page_id);
      setPieceId(page?.piece_id ?? null);
      return result.batch;
    });
    if (!ok) setPieceId(null);
    setSending(false);
  }

  async function startWebcam() {
    setCamError(null);
    try {
      setWebcam(await navigator.mediaDevices.getUserMedia({ video: { facingMode: "environment", width: { ideal: 1920 } } }));
    } catch {
      setCamError(tr("scan.webcamDenied"));
    }
  }

  function snap() {
    const v = video.current;
    if (!v || !v.videoWidth) return;
    const canvas = document.createElement("canvas");
    canvas.width = v.videoWidth;
    canvas.height = v.videoHeight;
    canvas.getContext("2d")?.drawImage(v, 0, 0);
    canvas.toBlob((blob) => blob && void send(blob), "image/jpeg", 0.92);
  }

  const webcamAvailable = typeof navigator !== "undefined" && !!navigator.mediaDevices?.getUserMedia;

  return (
    <div className="scan-page">
      <Breadcrumb detail={detail} last={tr("scan.batchLabel", { label: batch.label })} />
      <PageHeader title={tr("scan.shootTitle")} subtitle={tr("scan.shootSub", { ref: detail.reference, label: batch.label, pages: plural(batch.counts.pages, "scan.page1", "scan.pageN") })}>
        <button
          type="button"
          className="btn-primary"
          disabled={!editable || batch.counts.pages === 0 || sending}
          onClick={() => void act(() => api.scanAction(batch.id, "finish")).then((ok) => ok && navigate(`${base}/numerisation/${batch.id}`))}
        >
          <Icon name="check" size={18} /> {tr("scan.finishShooting")}
        </button>
      </PageHeader>
      {error && <p role="alert" className="error">⚠ {error}</p>}

      <div className="split-panel">
        <div>
          <section className="card" aria-labelledby="shoot-title">
            <div className="card-head">
              <h2 id="shoot-title" className="card-title">
                {current ? tr("scan.currentPiece", { usage: current.usage_label, n: current.page_ids.length + 1 }) : tr("scan.newPiece")}
              </h2>
              {current && (
                <button type="button" className="btn-secondary btn-small-pad" onClick={() => setPieceId(null)}>
                  {tr("scan.pieceDone")}
                </button>
              )}
            </div>
            {!current && <UsageSelect label={tr("scan.pieceType")} value={usage} onChange={setUsage} />}
            <p className="muted small">{tr("scan.layFlat")}</p>
            <div className="actions-row scan-shoot">
              <FileButton
                className="btn-primary"
                label={tr("scan.pagePhoto")}
                accept="image/*"
                camera
                disabled={!editable || sending}
                onFiles={([file]) => void send(file)}
              >
                <Icon name="plus" /> {sending ? tr("scan.sendingShort") : tr("scan.takePhoto")}
              </FileButton>
              {webcamAvailable && !webcam && (
                <button type="button" className="btn-secondary" disabled={!editable} onClick={() => void startWebcam()}>
                  <Icon name="eye" /> {tr("scan.useWebcam")}
                </button>
              )}
            </div>
            {camError && <p role="alert" className="error">⚠ {camError}</p>}
            {webcam && (
              <div className="scan-webcam">
                <video ref={video} className="scan-video" autoPlay playsInline muted />
                <div className="actions-row">
                  <button type="button" className="btn-secondary" onClick={() => setWebcam(null)}>{tr("scan.closeWebcam")}</button>
                  <button type="button" className="btn-primary" disabled={sending} onClick={snap}>{tr("scan.capture")}</button>
                </div>
              </div>
            )}
          </section>
          <PhoneNote />
        </div>

        <aside className="side-panel">
          <section className="card" aria-labelledby="shots-title">
            <h2 id="shots-title" className="card-title">{tr("scan.photographed")}</h2>
            {pieces.length === 0 ? (
              <p className="empty">{tr("scan.noPhoto")}</p>
            ) : (
              pieces.map((p, i) => (
                <div key={p.id} className="subcard">
                  <strong>{tr("scan.pieceOption", { n: i + 1, usage: p.usage_label })}</strong>
                  <div className="scan-thumbs">
                    {p.page_ids.map((id) => byId.get(id)).filter((x): x is ScanPageInfo => !!x).map((page) => (
                      <Thumb key={page.id} page={page} selected={false} onSelect={() => setPieceId(p.id)} />
                    ))}
                  </div>
                </div>
              ))
            )}
            <p className="muted small">{tr("scan.touchPage")}</p>
          </section>
        </aside>
      </div>
    </div>
  );
}
