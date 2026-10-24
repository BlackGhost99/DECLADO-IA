// Lot 3 : extraction assistée. Chaque valeur lue montre sa provenance et sa localisation ;
// rien n'est validé par l'extraction, et une saisie humaine n'est jamais écrasée.
import { useEffect, useState, type FormEvent } from "react";
import {
  api,
  type CaseDocument,
  type Divergence,
  type ExtractionDetail,
  type FieldSource,
  type Invoice,
  type InvoiceLine,
  type Job,
  type ReviewFlag,
  type Span,
  type TotalsCheck,
} from "./api";
import { errorText } from "./ui";
import { useI18n, type MessageKey } from "./i18n";

type Act = (a: () => Promise<unknown>) => Promise<void>;

export const FIELD_LABELS: Record<string, string> = {
  supplier_name: "fournisseur",
  invoice_number: "n° de facture",
  invoice_date: "date",
  currency: "devise",
  incoterm: "incoterm",
  declared_total: "total imprimé",
  source_reference: "réf. fournisseur",
  description_raw: "désignation",
  quantity: "quantité",
  unit: "unité",
  unit_price: "prix unitaire",
  amount: "montant",
  origin_country: "origine",
  "code:customs": "code douanier",
  "code:supplier": "réf. fournisseur (code)",
  "code:ambiguous": "code de nature incertaine",
};

const FIELD_KEYS: Record<string, MessageKey> = {
  supplier_name: "supplier", invoice_number: "invoiceNumber",
  invoice_date: "date", currency: "currency", incoterm: "incotermLabel",
  declared_total: "printedTotal", source_reference: "supplierRef",
  description_raw: "description", quantity: "quantity", unit: "unit",
  unit_price: "unitPrice", amount: "amount", origin_country: "origin",
  "code:customs": "customsCode", "code:supplier": "supplierCode",
  "code:ambiguous": "ambiguousCode",
};
const ORIGIN_KEYS: Record<string, MessageKey> = {
  read: "originRead", inferred: "originInferred", manual: "originManual",
};

/** « p. 2 · zone 14–38 % » pour un PDF ou une image, « Facture!F7 » pour Excel. */
export function spanText(span: Span | null | undefined): string {
  if (!span) return "";
  if (span.sheet) return `${span.sheet}!${span.cell_range ?? ""}`;
  if (span.page == null) return "";
  if (!span.bbox) return `p. ${span.page}`;
  const [, y0, , y1] = span.bbox;
  return `p. ${span.page} · hauteur ${Math.round(y0 * 100)}–${Math.round(y1 * 100)} %`;
}

export function OriginBadge({ origin, source }: { origin?: string; source?: FieldSource }) {
  const { t } = useI18n();
  if (!origin && !source) return null;
  const kind = origin === "manual" ? "manual" : (source?.origin ?? (origin === "extracted" ? "read" : origin ?? ""));
  const label = ORIGIN_KEYS[kind] ? t(ORIGIN_KEYS[kind]) : kind;
  const where = origin === "manual" ? "" : spanText(source?.span);
  const title = [
    source?.span?.excerpt ? `${t("originalText")} « ${source.span.excerpt} »` : "",
    source?.confidence != null ? `${t("ocrConfidence")} ${Math.round(source.confidence)}` : "",
    ...(source?.notes ?? []),
  ]
    .filter(Boolean)
    .join(" · ");
  return (
    <span className={`badge badge-${kind}`} title={title || undefined}>
      {label}
      {where && ` · ${where}`}
    </span>
  );
}

export function Flags({ flags, field }: { flags?: ReviewFlag[]; field?: string }) {
  const shown = (flags ?? []).filter((f) => field === undefined || f.field === field);
  if (shown.length === 0) return null;
  return (
    <ul className="flags small">
      {shown.map((f) => (
        <li key={f.field + f.code + f.message}>⚠ {f.message}</li>
      ))}
    </ul>
  );
}

const sleep = (ms: number) => new Promise((resolve) => setTimeout(resolve, ms));

/** Suit un travail jusqu'à son terme ; la page reste utilisable pendant ce temps. */
export async function followJob(id: string, onTick: (job: Job) => void, interval = 1200, maxTicks = 300): Promise<Job> {
  let job = await api.job(id);
  for (let i = 0; i < maxTicks && (job.state === "queued" || job.state === "running"); i++) {
    onTick(job);
    await sleep(interval);
    job = await api.job(id);
  }
  onTick(job);
  return job;
}

export function ExtractionControls({
  link,
  editable,
  onDone,
}: {
  link: CaseDocument;
  editable: boolean;
  onDone: () => Promise<void>;
}) {
  const { t } = useI18n();
  const run = link.latest_extraction ?? null;
  const [job, setJob] = useState<Job | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [open, setOpen] = useState(false);
  const isImage = link.document.mime.startsWith("image/");
  const busy = job !== null && (job.state === "queued" || job.state === "running");
  const canExtract = editable && !link.replaced_by_id && link.document.readability === "ok";

  async function start(options: { ocr?: boolean; retry?: boolean }) {
    setError(null);
    try {
      const started = await api.extract(link.id, options);
      const final = await followJob(started.job.id, setJob);
      setJob(final.state === "succeeded" ? null : final);
      await onDone();
    } catch (err) {
      setJob(null);
      setError(errorText(err, "Extraction impossible."));
    }
  }

  return (
    <div className="small">
      {run && !busy && (
        <div>
          Lecture {run.attempt} : <strong>{run.status_label}</strong>
          {run.parser && <span className="muted"> · {run.parser === "ocr" ? "OCR" : run.parser}</span>}
          {run.warnings.length > 0 && <span className="muted"> · {run.warnings.length} avertissement(s)</span>}
          {run.error_message && <div className="error">{run.error_message}</div>}
          {run.hint && <div className="muted">{run.hint}</div>}
        </div>
      )}
      {busy && (
        <div role="status">
          {job.state_label} · {job.phase}
          {job.progress.total ? ` (${job.progress.done ?? 0}/${job.progress.total})` : ""}
        </div>
      )}
      {job?.state === "failed" && <div className="error">{job.error_message}</div>}
      {canExtract && !busy && (
        <div className="row">
          {!run && !isImage && <button type="button" onClick={() => void start({})}>{t("extract")}</button>}
          {!run && <button type="button" onClick={() => void start({ ocr: true })}>{t("extractOCR")}</button>}
          {run && <button type="button" onClick={() => void start({ retry: true, ocr: Boolean(run.options.ocr) })}>{t("retry")}</button>}
          {run && !run.options.ocr && <button type="button" onClick={() => void start({ retry: true, ocr: true })}>{t("retryOCR")}</button>}
        </div>
      )}
      {run && (
        <button type="button" className="link" onClick={() => setOpen(!open)}>
          {open ? "Masquer la lecture" : "Voir la lecture"}
        </button>
      )}
      {open && run && <RunDetail runId={run.id} />}
      {error && <p role="alert" className="error">⚠ {error}</p>}
    </div>
  );
}

function show(value: unknown): string {
  if (value === null || value === undefined || value === "") return "—";
  return String(value);
}

export function RunDetail({ runId }: { runId: string }) {
  const { t } = useI18n();
  const [run, setRun] = useState<ExtractionDetail | null>(null);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    api.extractionRun(runId).then(setRun, (err) => setError(errorText(err, t("loadMissing"))));
  }, [runId]);
  if (error) return <p className="error">{error}</p>;
  if (!run) return <p className="muted">{t("loading")}</p>;
  const report = Object.entries(run.merge_report ?? {}).filter(([, v]) => v);
  return (
    <div className="evidence" aria-label={`Lecture ${run.attempt}`}>
      <p className="muted">
        Lecteur {run.parser} {run.parser_version} · par {run.created_by} · {run.provider ? `IA ${run.provider}` : "sans IA"}. {run.job.note}
      </p>
      {run.warnings.length > 0 && (
        <ul>
          {run.warnings.map((w) => (
            <li key={w.code + w.message}>⚠ {w.message}</li>
          ))}
        </ul>
      )}
      {report.length > 0 && (
        <p>Fusion : {report.map(([k, v]) => (v === true ? MERGE_LABELS[k] : `${MERGE_LABELS[k] ?? k} ${v}`)).join(" · ")}</p>
      )}
      {run.charges.length > 0 && (
        <p>
          Autres lignes lues :{" "}
          {run.charges.map((c) => `${c.label} ${show(c.amount)}${c.page ? ` (p. ${c.page})` : ""}`).join(" ; ")}
        </p>
      )}
      {run.comparison && (
        <>
          <p>
            Comparée à la lecture {run.comparison.previous_attempt} : {run.comparison.counts.same} identique(s),{" "}
            {run.comparison.counts.changed} changée(s), {run.comparison.counts.new} nouvelle(s),{" "}
            {run.comparison.counts.not_reread} non relue(s).
          </p>
          {run.comparison.rows.length > 0 && (
            <table>
              <thead>
                <tr><th scope="col">{t("element")}</th><th scope="col">{t("field")}</th><th scope="col">{t("before")}</th><th scope="col">{t("now")}</th></tr>
              </thead>
              <tbody>
                {run.comparison.rows.map((r) => (
                  <tr key={r.entity_key + r.field}>
                    <td>{r.entity_key}</td>
                    <td>{FIELD_KEYS[r.field] ? t(FIELD_KEYS[r.field]) : r.field}</td>
                    <td>{show(r.previous)}</td>
                    <td>{show(r.current)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </>
      )}
    </div>
  );
}

const MERGE_LABELS: Record<string, string> = {
  invoice_created: "facture créée",
  lines_created: "lignes créées",
  lines_updated: "lignes mises à jour",
  lines_not_reread: "lignes non relues (conservées)",
  values_set: "valeurs renseignées",
  values_not_reread: "valeurs non relues (conservées)",
  corrections_kept: "corrections conservées",
  divergences: "divergences",
  codes_observed: "codes lus",
};

const TOTALS_KEYS: Record<TotalsCheck["status"], MessageKey> = {
  match: "totalMatch", gap: "totalGap", incomplete: "totalUnknown", no_printed_total: "noPrintedTotal",
};

export function TotalsPanel({ totals, currency }: { totals?: TotalsCheck; currency: string }) {
  const { t } = useI18n();
  if (!totals || totals.goods_lines === 0) return null;
  const c = totals.components;
  return (
    <div className={totals.status === "match" ? "evidence small" : "warning small"} aria-label={t("totalsCheck")}>
      <p><strong>{t(TOTALS_KEYS[totals.status])}</strong></p>
      <p>
        {t("goods")} {show(c.goods)} + {t("fees")} {show(c.fees)} − {t("discounts")} {show(c.discounts)} + {t("taxes")} {show(c.taxes)} ={" "}
        <strong>{show(totals.computed_total)}</strong> {currency} · {t("printed")} <strong>{show(totals.printed_total)}</strong>
        {totals.gap && totals.gap !== "0" && <> · {t("gap")} <strong>{totals.gap}</strong></>}
      </p>
      {totals.goods_lines_without_amount > 0 && <p>{totals.goods_lines_without_amount} {t("linesWithoutAmount")}</p>}
      {totals.explanations.map((e) => (
        <p key={e}>{e}</p>
      ))}
      {totals.subtotals_not_added.length > 0 && (
        <p className="muted">
          {t("excludedSubtotals")}{" "}
          {totals.subtotals_not_added.map((s) => `${s.label} ${show(s.amount)}`).join(" ; ")}
        </p>
      )}
    </div>
  );
}

export function Divergences({ invoice, editable, act }: { invoice: Invoice; editable: boolean; act: Act }) {
  const { t } = useI18n();
  const open = (invoice.divergences ?? []).filter((d) => d.state === "open");
  const closed = (invoice.divergences ?? []).filter((d) => d.state !== "open");
  if (open.length === 0 && closed.length === 0) return null;
  return (
    <div className="warning small" aria-label={t("divergences")}>
      {open.length > 0 && (
        <>
          <p>
            <strong>{open.length} {t("reviewCount")}</strong> {t("valueRetained")}
          </p>
          <ul>
            {open.map((d) => (
              <DivergenceItem key={d.id} divergence={d} editable={editable} act={act} />
            ))}
          </ul>
        </>
      )}
      {closed.length > 0 && (
        <details>
          <summary>{closed.length} {t("divergencesClosed")}</summary>
          <ul>
            {closed.map((d) => (
              <li key={d.id}>
                {where(d)} : {d.state_label} par {d.resolved_by}
                {d.resolution_reason && ` (motif : ${d.resolution_reason})`}
              </li>
            ))}
          </ul>
        </details>
      )}
    </div>
  );
}

function where(d: Divergence) {
  const field = FIELD_KEYS[d.field] ? t(FIELD_KEYS[d.field]) : d.field;
  return d.line_ordinal ? `Ligne ${d.line_ordinal}${d.field ? `, ${field}` : ""}` : `Facture, ${field}`;
}

function DivergenceItem({ divergence: d, editable, act }: { divergence: Divergence; editable: boolean; act: Act }) {
  const { t } = useI18n();
  const [reason, setReason] = useState("");
  return (
    <li>
      {where(d)} :{" "}
      {d.kind === "line_not_reread" ? (
        t("notReread")
      ) : (
        <>
          valeur actuelle <strong>{show(d.current_value)}</strong>, relecture <strong>{show(d.extracted_value)}</strong>
          {d.span && <span className="muted"> ({spanText(d.span)})</span>}
        </>
      )}
      {editable && (
        <span className="row">
          <input aria-label={t("correctionReason")} placeholder={t("reasonOptional")} value={reason} onChange={(e) => setReason(e.target.value)} size={24} />
          <button type="button" onClick={() => void act(() => api.resolveDivergence(d.id, "keep", reason))}>
            Garder la valeur actuelle
          </button>
          {d.kind === "value" && (
            <button type="button" onClick={() => void act(() => api.resolveDivergence(d.id, "accept", reason))}>
              Retenir la relecture
            </button>
          )}
        </span>
      )}
    </li>
  );
}

const EDITABLE_FIELDS = ["description_raw", "quantity", "unit", "unit_price", "amount", "origin_country"] as const;

/** Correction d'une ligne : la valeur devient « saisie », protégée des relectures, et la correction est tracée. */
export function LineEditor({
  line,
  act,
  toDecimal,
  onClose,
}: {
  line: InvoiceLine;
  act: Act;
  toDecimal: (v: string) => string | null;
  onClose: () => void;
}) {
  const { t } = useI18n();
  const [form, setForm] = useState<Record<string, string>>(
    Object.fromEntries(EDITABLE_FIELDS.map((f) => [f, String(line[f] ?? "")])),
  );
  const [reason, setReason] = useState("");

  function submit(event: FormEvent) {
    event.preventDefault();
    const data: Record<string, unknown> = { row_version: line.row_version, correction_reason: reason };
    for (const f of EDITABLE_FIELDS) {
      const before = String(line[f] ?? "");
      if (form[f] === before) continue;
      data[f] = ["quantity", "unit_price", "amount"].includes(f) ? toDecimal(form[f]) : form[f];
    }
    void act(async () => {
      await api.updateLine(line.id, data);
      onClose();
    });
  }

  return (
    <form className="row small" onSubmit={submit} aria-label={`Corriger la ligne ${line.ordinal}`}>
      {EDITABLE_FIELDS.map((f) => (
        <label key={f}>
          {FIELD_KEYS[f] ? t(FIELD_KEYS[f]) : FIELD_LABELS[f]}
          <input value={form[f]} size={f === "description_raw" ? 28 : 8} onChange={(e) => setForm({ ...form, [f]: e.target.value })} />
        </label>
      ))}
      <label>
        Motif de la correction
        <input value={reason} onChange={(e) => setReason(e.target.value)} size={28} placeholder="ex. bon de livraison" />
      </label>
      <button type="submit">{t("saveCorrection")}</button>
      <button type="button" onClick={onClose}>{t("cancel")}</button>
    </form>
  );
}
