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
import { Chip, errorText, fmtDateTime, PageHeader, personName, ProgressBar, StatCard, type Tone } from "./ui";

const SCANNER_ACCEPT = ".pdf,.tif,.tiff,.png,.jpg,.jpeg";
const POLL_MS = 1500;

/** « p. 4 », « p. 4 et 5 », « p. 1 à 3 », ou la liste si les pages ne se suivent pas. */
export function pageRange(numbers: number[]): string {
  const n = [...numbers].sort((a, b) => a - b);
  if (n.length === 0) return "aucune page";
  const consecutive = n.every((v, i) => i === 0 || v === n[i - 1] + 1);
  if (n.length === 1) return `p. ${n[0]}`;
  if (consecutive) return n.length === 2 ? `p. ${n[0]} et ${n[1]}` : `p. ${n[0]} à ${n[n.length - 1]}`;
  return `p. ${n.join(", ")}`;
}

const plural = (n: number, one: string, many: string) => `${n} ${n > 1 ? many : one}`;

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
  if (batch.state === "attached") return { tone: "green", text: `Rattaché : ${plural(c.pieces, "pièce", "pièces")}` };
  if (batch.state === "cancelled") return { tone: "gray", text: "Abandonné" };
  if (batch.job?.state === "failed") return { tone: "red", text: batch.job.error_message ?? "Lecture en échec" };
  if (isWorking(batch)) {
    const { done, total } = batch.job?.progress ?? {};
    return { tone: "blue", text: total ? `Lecture du texte : page ${done ?? 0} sur ${total}` : "Lecture en cours" };
  }
  if (batch.state === "open") return { tone: "blue", text: `Prise de vue en cours : ${plural(c.pages, "page", "pages")}` };
  if (c.unclassified > 0) return { tone: "amber", text: `À trier : ${plural(c.unclassified, "page non classée", "pages non classées")}` };
  return { tone: "green", text: "À vérifier puis rattacher" };
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
      title={flagged ? "Texte peu lisible" : page.title || undefined}
      onClick={onSelect}
    >
      {page.has_image ? (
        <img src={scanPageImage(page)} alt={`Page ${page.number}`} loading="lazy" />
      ) : (
        <span className="scan-thumb-empty">{page.state === "pending" ? "lecture…" : "illisible"}</span>
      )}
      p. {page.number}
    </button>
  );
}

function pageStatus(page: ScanPageInfo): { tone: Tone; text: string } {
  if (page.removed) return { tone: "gray", text: page.removed_label };
  if (page.state === "pending") return { tone: "blue", text: "Lecture en cours" };
  if (page.state === "failed") return { tone: "red", text: "Illisible, à reprendre" };
  if (page.hard_to_read) return { tone: "amber", text: "Peu lisible, à reprendre" };
  return { tone: "green", text: page.text_origin === "ocr" ? "Texte lu (OCR)" : "Texte lu" };
}

/** Écrans de numérisation d'un dossier : #/dossiers/:id/numerisation[/:lot[/photos]]. */
export function ScanScreens({ caseId, rest, membership }: { caseId: string; rest: string[]; membership: Membership }) {
  const [detail, setDetail] = useState<CaseDetail | null>(null);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    rememberCase(caseId);
    api.caseDetail(caseId).then(setDetail, (err) => setError(errorText(err, "Dossier introuvable.")));
  }, [caseId]);
  if (!detail) return <p className="muted">{error ?? "Chargement…"}</p>;
  const editable = membership.roles.some((r) => r === "declarant" || r === "validator") && detail.revision.is_editable;
  const [batchId, sub] = rest;
  if (batchId && sub === "photos") return <Capture key={batchId} detail={detail} batchId={batchId} editable={editable} />;
  if (batchId) return <SortBatch key={batchId} detail={detail} batchId={batchId} editable={editable} />;
  return <AddPieces detail={detail} editable={editable} />;
}

function Breadcrumb({ detail, last }: { detail: CaseDetail; last?: string }) {
  const base = `/dossiers/${detail.id}`;
  return (
    <nav className="breadcrumb" aria-label="Fil d'Ariane">
      <button type="button" className="link" onClick={() => navigate("/dossiers")}>Mes dossiers</button>
      <Icon name="chevronRight" size={14} />
      <button type="button" className="link" onClick={() => navigate(`${base}/apercu`)}>{detail.reference}</button>
      <Icon name="chevronRight" size={14} />
      <button type="button" className="link" onClick={() => navigate(`${base}/documents`)}>Documents</button>
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
      Pour photographier avec un téléphone, ouvrez ClairTransit sur le téléphone avec l'adresse du serveur de l'agence (pas « localhost »), puis ce dossier.
    </p>
  ) : (
    <p className="note-blue small">
      Sur un téléphone connecté au réseau de l'agence, ouvrez <strong className="code">{window.location.href}</strong> après vous être connecté.
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
    load().catch((err) => setError(errorText(err, "Lots indisponibles.")));
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
      const label = files.length === 1 ? files[0].name : `${files[0].name} et ${plural(files.length - 1, "autre fichier", "autres fichiers")}`;
      const batch = await api.createScanBatch(detail.id, "scanner", label.slice(0, 200));
      await api.addScanFiles(batch.id, files);
      navigate(`${base}/numerisation/${batch.id}`);
    } catch (err) {
      setError(errorText(err, "Dépôt du lot impossible."));
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
      setError(errorText(err, "Prise de vue impossible."));
    } finally {
      setBusy(false);
    }
  }

  const visible = (batches ?? []).filter((b) => b.state !== "cancelled");

  return (
    <div className="scan-page">
      <Breadcrumb detail={detail} />
      <PageHeader
        title="Ajouter les pièces du dossier"
        subtitle={<>Dossier {detail.reference}{detail.importer && <> · {detail.importer.name}</>} · {detail.revision.mode_label}</>}
      >
        <button type="button" className="btn-secondary" onClick={() => navigate(`${base}/documents`)}>
          <Icon name="file" size={18} /> Voir les pièces du dossier
        </button>
      </PageHeader>
      {error && <p role="alert" className="error">⚠ {error}</p>}
      {!editable && <p className="note-amber small">Ce dossier n'est pas modifiable par vous : les lots restent consultables.</p>}

      <div className="scan-ways">
        <section className="card" aria-labelledby="way-scanner">
          <div className="card-head">
            <h2 id="way-scanner" className="card-title">Lot du scanner</h2>
            <Chip tone="green">Recommandé pour plusieurs dizaines de pages</Chip>
          </div>
          <p className="muted">
            Passez toutes les pièces dans le chargeur du scanner, puis déposez ici le PDF obtenu ou les images. ClairTransit sépare les pièces et propose leur type.
          </p>
          <p className="muted small">PDF multipage, ou images PNG, JPEG, TIFF{maxPages ? ` · ${maxPages} pages au plus par lot` : ""}.</p>
          <FileButton
            className="btn-primary btn-block"
            label="Fichiers du lot"
            accept={SCANNER_ACCEPT}
            multiple
            disabled={!editable || busy}
            onFiles={(files) => void scanner(files)}
          >
            <Icon name="cloudUpload" /> {busy ? "Envoi du lot…" : "Choisir les fichiers du lot"}
          </FileButton>
        </section>

        <section className="card" aria-labelledby="way-camera">
          <div className="card-head">
            <h2 id="way-camera" className="card-title">Téléphone ou webcam</h2>
            <Chip tone="gray">Quand aucun scanner n'est disponible</Chip>
          </div>
          <p className="muted">
            Photographiez les pages une à une. Chaque photo est recadrée et redressée, puis les pages forment une pièce PDF.
          </p>
          <PhoneNote />
          <button type="button" className="btn-primary btn-block" disabled={!editable || busy} onClick={() => void camera()}>
            <Icon name="eye" /> Commencer la prise de vue
          </button>
        </section>

        <section className="card" aria-labelledby="way-files">
          <div className="card-head">
            <h2 id="way-files" className="card-title">Fichiers déjà prêts</h2>
            <Chip tone="gray">Comme aujourd'hui</Chip>
          </div>
          <p className="muted">
            Une pièce par fichier, reçue par e-mail ou exportée d'un logiciel : facture PDF, classeur Excel, photo.
          </p>
          <button type="button" className="btn-secondary btn-block" onClick={() => navigate(`${base}/documents`)}>
            <Icon name="plus" /> Ajouter des fichiers
          </button>
        </section>
      </div>

      <section className="card" aria-labelledby="batches-title">
        <h2 id="batches-title" className="card-title">Lots en cours pour ce dossier</h2>
        {batches === null ? (
          <p className="muted">Chargement…</p>
        ) : visible.length === 0 ? (
          <p className="empty">Aucun lot numérisé pour ce dossier.</p>
        ) : (
          <div className="table-wrap">
            <table className="data">
              <thead>
                <tr>
                  <th>Lot</th>
                  <th>Source</th>
                  <th className="num">Pages</th>
                  <th>Avancement</th>
                  <th>Action</th>
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
                          {photos ? "Continuer la prise de vue" : b.state === "to_sort" ? "Trier le lot" : "Ouvrir"}
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
          Conseil de numérisation : 300 points par pouce, recto verso si les pièces sont imprimées des deux côtés. Une page blanche entre deux pièces aide la séparation, sans être obligatoire.
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
      setError(errorText(err, "Lot introuvable."));
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
      setError(errorText(err, "Action impossible."));
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

  if (!batch) return <p className="muted">{error ?? "Chargement…"}</p>;
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
      <Breadcrumb detail={detail} last={`Lot ${batch.label}`} />
      <PageHeader
        title={`Trier le lot : ${plural(c.pages, "page", "pages")}, ${plural(pieces.length, "pièce proposée", "pièces proposées")}`}
        subtitle={<>{batch.source_label} · {batch.label} · déposé par {personName(batch.created_by)} le {fmtDateTime(batch.created_at)}</>}
      >
        {canEdit && batch.source === "scanner" && (
          <FileButton
            className="btn-secondary"
            label="Pages à ajouter au lot"
            accept={SCANNER_ACCEPT}
            multiple
            disabled={working}
            onFiles={(files) => void act(() => api.addScanFiles(batch.id, files))}
          >
            <Icon name="plus" size={18} /> Ajouter des pages au lot
          </FileButton>
        )}
        {canEdit && batch.source === "camera" && (
          <button type="button" className="btn-secondary" onClick={() => navigate(`${base}/numerisation/${batch.id}/photos`)}>
            <Icon name="plus" size={18} /> Ajouter des photos
          </button>
        )}
        {canEdit && (
          <button
            type="button"
            className="btn-primary"
            disabled={working || pieces.length === 0}
            onClick={() => void act(() => api.scanAction(batch.id, "attach"))}
          >
            <Icon name="check" size={18} /> Rattacher {plural(pieces.length, "pièce", "pièces")} au dossier
          </button>
        )}
      </PageHeader>
      {error && <p role="alert" className="error">⚠ {error}</p>}

      <div className="stats stats-4">
        <StatCard icon="layers" tone="blue" label="Pages reçues" value={c.pages} hint={plural(batch.sources.length, "fichier", "fichiers")} />
        <StatCard
          icon="eye"
          tone={working ? "blue" : "green"}
          label="Pages redressées et lues"
          value={`${read} / ${kept.length}`}
          hint={working ? <ProgressBar value={progressValue(batch)} /> : "lecture terminée"}
        />
        <StatCard
          icon="file"
          tone={c.unclassified || c.hard_to_read ? "amber" : "green"}
          label="Séparation proposée"
          value={plural(pieces.length, "pièce", "pièces")}
          hint={[
            c.unclassified ? plural(c.unclassified, "page à classer", "pages à classer") : null,
            c.hard_to_read ? plural(c.hard_to_read, "page à reprendre", "pages à reprendre") : null,
            c.blank_removed ? plural(c.blank_removed, "page blanche retirée", "pages blanches retirées") : null,
          ].filter(Boolean).join(", ") || "rien à signaler"}
        />
        <StatCard icon="checkCircle" tone="gray" label="Votre vérification" value={batch.state_label} hint="rien n'est rattaché avant votre clic" />
      </div>

      <div className="split-panel">
        <div>
          {pieces.length === 0 && !working && <p className="empty card">Aucune pièce proposée : rangez les pages ci-dessous.</p>}
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
                <h2 id="unclassified-title" className="card-title">Pages non classées</h2>
                <Chip tone="amber">{plural(unclassified.length, "page", "pages")}</Chip>
              </div>
              <p className="muted small">Aucun titre reconnu : choisissez la pièce de chacune, ou créez une pièce. Une page non classée reste dans le lot.</p>
              <div className="scan-thumbs">
                {unclassified.map((p) => (
                  <Thumb key={p.id} page={p} selected={selected?.id === p.id} onSelect={() => setSelectedId(p.id)} />
                ))}
              </div>
            </section>
          )}
          {removed.length > 0 && (
            <details className="card small">
              <summary>{plural(removed.length, "page retirée", "pages retirées")} du lot, conservée(s)</summary>
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
                Abandonner ce lot
              </button>{" "}
              <span className="muted">(les fichiers déposés restent conservés)</span>
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
            <section className="card"><p className="empty">{working ? "Lecture des pages en cours…" : "Aucune page."}</p></section>
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
          <option key={v} value={v}>{l}</option>
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
        <h2 id={`piece-${piece.id}`} className="card-title">Pièce {index + 1}</h2>
        <UsageSelect
          label="Type"
          value={piece.usage}
          disabled={!editable}
          onChange={(usage) => void act(() => api.updateScanPiece(piece.id, usage))}
        />
        <Chip tone="gray">{pageRange(pages.map((p) => p.number ?? 0))}</Chip>
      </div>
      <p className="muted small">{piece.usage_by_user ? "Type choisi par l'agent" : `Proposé : ${piece.reason}`}</p>
      <div className="scan-thumbs">
        {pages.map((p) => (
          <Thumb key={p.id} page={p} selected={selectedId === p.id} onSelect={() => onSelect(p.id)} />
        ))}
      </div>
      {editable && index > 0 && (
        <div className="actions-row">
          <button type="button" className="btn-small" onClick={() => void act(() => api.joinScanPiece(piece.id))}>
            Joindre à la pièce précédente
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
        <h2 id="page-title" className="card-title">Page {page.number}</h2>
        <Chip tone={status.tone}>{status.text}</Chip>
      </div>
      {page.has_image ? (
        <img className="scan-preview" src={scanPageImage(page, false)} alt={`Page ${page.number} du lot`} />
      ) : (
        <p className="empty">{page.state === "pending" ? "Lecture en cours…" : "Image indisponible."}</p>
      )}
      <ul className="plain small">
        <li>Fichier {page.source_name}, page {page.source_page}</li>
        {piece && <li>Dans la pièce {pieceIndex + 1} ({piece.usage_label})</li>}
        {page.title && <li>Titre lu : « {page.title} »{page.reference && <>, n° {page.reference}</>}</li>}
        {page.page_marker && <li>Mention « page {page.page_marker} » lue</li>}
        {page.notes.map((n) => <li key={n} className="muted">{n}</li>)}
      </ul>
      {(page.hard_to_read || page.state === "failed") && (
        <p className="note-amber small">
          Le texte de cette page n'a pas pu être lu correctement. Repassez-la au scanner ou reprenez-la en photo ; elle remplacera celle-ci à la même place.
        </p>
      )}
      {editable && (
        <div className="scan-actions">
          <FileButton
            className="btn-secondary"
            label="Nouvelle prise de la page"
            accept={SCANNER_ACCEPT}
            camera
            onFiles={([file]) => void act(() => api.replaceScanPage(page.id, file))}
          >
            <Icon name="refresh" size={18} /> Reprendre la page
          </FileButton>
          {page.removed ? (
            <button type="button" className="btn-secondary" onClick={() => void act(() => api.updateScanPage(page.id, { removed: false }))}>
              <Icon name="plus" size={18} /> Remettre dans le lot
            </button>
          ) : (
            <>
              <button
                type="button"
                className="btn-secondary"
                onClick={() => void act(() => api.updateScanPage(page.id, { rotation: (page.rotation + 90) % 360 }))}
              >
                <Icon name="refresh" size={18} /> Pivoter
              </button>
              {piece && !firstOfPiece && (
                <button type="button" className="btn-secondary" onClick={() => void act(() => api.splitScanPage(page.id))}>
                  <Icon name="minus" size={18} /> Couper la pièce ici
                </button>
              )}
              {piece && firstOfPiece && pieceIndex > 0 && (
                <button type="button" className="btn-secondary" onClick={() => void act(() => api.joinScanPiece(piece.id))}>
                  <Icon name="layers" size={18} /> Joindre à la précédente
                </button>
              )}
              <label>
                Déplacer vers…
                <select value="" onChange={(e) => move(e.target.value)}>
                  <option value="">Choisir</option>
                  {pieces.map((p, i) =>
                    p.id === page.piece_id ? null : (
                      <option key={p.id} value={p.id}>Pièce {i + 1} · {p.usage_label}</option>
                    ),
                  )}
                  <option value="new">Nouvelle pièce (type ci-dessous)</option>
                  {page.piece_id && <option value="none">Pages non classées</option>}
                </select>
              </label>
              <UsageSelect label="Type d'une nouvelle pièce" value={newUsage} onChange={setNewUsage} />
              <button type="button" className="btn-secondary" onClick={() => void act(() => api.updateScanPage(page.id, { removed: true }))}>
                <Icon name="x" size={18} /> Retirer du lot
              </button>
            </>
          )}
        </div>
      )}
      <p className="muted small">Les types sont des propositions : rien n'est rattaché au dossier avant votre clic sur « Rattacher ».</p>
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
      <Breadcrumb detail={detail} last={`Lot ${batch.label}`} />
      <PageHeader title="Pièces du dossier">
        <button type="button" className="btn-secondary" onClick={() => navigate(`${base}/numerisation`)}>
          <Icon name="plus" size={18} /> Ajouter ou numériser des pièces
        </button>
        <button type="button" className="btn-primary" onClick={() => navigate(`${base}/documents`)}>
          <Icon name="file" size={18} /> Ouvrir les documents
        </button>
      </PageHeader>
      <p className="note-blue">
        {plural(attached.length, "pièce rattachée", "pièces rattachées")} depuis le lot {batch.label}.
        {left > 0 && ` ${plural(left, "page non classée reste", "pages non classées restent")} dans le lot.`}
        {reading > 0 && ` La lecture de ${plural(reading, "facture", "factures")} a démarré.`}
      </p>
      <section className="card" aria-label="Pièces rattachées">
        <div className="table-wrap">
          <table className="data">
            <thead>
              <tr>
                <th>Pièce</th>
                <th>Type</th>
                <th className="num">Pages</th>
                <th>Provenance</th>
                <th>Lecture</th>
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
                    <td>Numérisé · lot {batch.label} · {pageRange(p.page_ids.map((id) => numbers.get(id) ?? 0))}</td>
                    <td>
                      {run ? (
                        <Chip tone={run.status === "failed" ? "red" : run.status === "succeeded" ? "green" : "blue"}>{run.status_label}</Chip>
                      ) : (
                        <span className="muted">non demandée</span>
                      )}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
        <p className="muted small">
          Chaque pièce numérisée garde le lot d'origine et ses numéros de page, pour retrouver la feuille papier. Les valeurs lues dans un scan restent à vérifier tant qu'un agent ne les a pas confirmées.
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

  if (!batch) return <p className="muted">{error ?? "Chargement…"}</p>;
  if (batch.state !== "open") {
    return (
      <div className="scan-page">
        <Breadcrumb detail={detail} last={`Lot ${batch.label}`} />
        <p className="note-blue">La prise de vue de ce lot est terminée.</p>
        <button type="button" className="btn-primary" onClick={() => navigate(`${base}/numerisation/${batch.id}`)}>Trier le lot</button>
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
      setCamError("Webcam indisponible ou refusée par le navigateur.");
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
      <Breadcrumb detail={detail} last={`Lot ${batch.label}`} />
      <PageHeader title="Prise de vue" subtitle={<>Dossier {detail.reference} · {batch.label} · {plural(batch.counts.pages, "page", "pages")}</>}>
        <button
          type="button"
          className="btn-primary"
          disabled={!editable || batch.counts.pages === 0 || sending}
          onClick={() => void act(() => api.scanAction(batch.id, "finish")).then((ok) => ok && navigate(`${base}/numerisation/${batch.id}`))}
        >
          <Icon name="check" size={18} /> Terminer la prise de vue
        </button>
      </PageHeader>
      {error && <p role="alert" className="error">⚠ {error}</p>}

      <div className="split-panel">
        <div>
          <section className="card" aria-labelledby="shoot-title">
            <div className="card-head">
              <h2 id="shoot-title" className="card-title">
                {current ? `Pièce en cours : ${current.usage_label}, page ${current.page_ids.length + 1}` : "Nouvelle pièce"}
              </h2>
              {current && (
                <button type="button" className="btn-secondary btn-small-pad" onClick={() => setPieceId(null)}>
                  Pièce terminée
                </button>
              )}
            </div>
            {!current && <UsageSelect label="Type de la pièce" value={usage} onChange={setUsage} />}
            <p className="muted small">Posez la feuille à plat sur un fond sombre, bien éclairée : la photo est recadrée sur la feuille et redressée.</p>
            <div className="actions-row scan-shoot">
              <FileButton
                className="btn-primary"
                label="Photo de la page"
                accept="image/*"
                camera
                disabled={!editable || sending}
                onFiles={([file]) => void send(file)}
              >
                <Icon name="plus" /> {sending ? "Envoi…" : "Prendre une photo"}
              </FileButton>
              {webcamAvailable && !webcam && (
                <button type="button" className="btn-secondary" disabled={!editable} onClick={() => void startWebcam()}>
                  <Icon name="eye" /> Utiliser la webcam
                </button>
              )}
            </div>
            {camError && <p role="alert" className="error">⚠ {camError}</p>}
            {webcam && (
              <div className="scan-webcam">
                <video ref={video} className="scan-video" autoPlay playsInline muted />
                <div className="actions-row">
                  <button type="button" className="btn-secondary" onClick={() => setWebcam(null)}>Fermer la webcam</button>
                  <button type="button" className="btn-primary" disabled={sending} onClick={snap}>Capturer la page</button>
                </div>
              </div>
            )}
          </section>
          <PhoneNote />
        </div>

        <aside className="side-panel">
          <section className="card" aria-labelledby="shots-title">
            <h2 id="shots-title" className="card-title">Pages photographiées</h2>
            {pieces.length === 0 ? (
              <p className="empty">Aucune photo pour l'instant.</p>
            ) : (
              pieces.map((p, i) => (
                <div key={p.id} className="subcard">
                  <strong>Pièce {i + 1} · {p.usage_label}</strong>
                  <div className="scan-thumbs">
                    {p.page_ids.map((id) => byId.get(id)).filter((x): x is ScanPageInfo => !!x).map((page) => (
                      <Thumb key={page.id} page={page} selected={false} onSelect={() => setPieceId(p.id)} />
                    ))}
                  </div>
                </div>
              ))
            )}
            <p className="muted small">Touchez une page pour reprendre la pièce correspondante ; une page floue se reprend ensuite au tri.</p>
          </section>
        </aside>
      </div>
    </div>
  );
}
