import { useEffect, useState, type FormEvent } from "react";
import {
  api,
  ApiError,
  type AmendmentInput,
  type CalcTax,
  type CaseCalculation,
  type CodeRates,
  type ScheduleLineInfo,
  type TaxAmendment,
  type TaxBaseKind,
  type TaxOverview,
  type TaxOverviewRow,
} from "./api";
import { Icon } from "./Icon";
import { tr, type MessageKey } from "./i18n";
import { Chip, fmtAmount, fmtDate, StatCard, type Tone } from "./ui";

/** Taxes à l'importation, dans l'ordre du calcul ; la redevance est globale, le droit de sortie hors import. */
export const TAX_CODES = ["DDI", "DA", "TVA", "TCI", "CCI", "OAD", "CSS", "CAF", "RI", "DSO"] as const;
const AMENDABLE = ["DDI", "DA", "TVA", "TCI", "CCI", "OAD", "CSS", "CAF"] as const;
const SINGLE_RATE = new Set(["TCI", "CCI", "OAD", "CSS", "CAF", "RI"]);
const REVIEW_KINDS = ["tec_difference", "empty_tax", "national_subposition"] as const;

export const taxName = (code: string) => tr(`fx.tax.${code}` as MessageKey);
export const baseName = (kind: TaxBaseKind) => tr(`fx.base.${kind}` as MessageKey);
export const pct = (rate: string | null | undefined) => (rate === null || rate === undefined ? "" : `${fmtAmount(rate, 0)} %`);
/** Montant en FCFA arrondi au franc pour l'affichage (le calcul garde la valeur exacte). */
export const xaf = (amount: string | null | undefined) =>
  amount === null || amount === undefined || amount === "" ? "" : fmtAmount(String(Math.round(Number(amount))), 0);
const unknown = (text: string) => <em className="muted">{text}</em>;

function rateRange(row: TaxOverviewRow): string {
  const rates = row.values.map(([r]) => Number(r));
  if (!rates.length) return "";
  const min = String(Math.min(...rates));
  const max = String(Math.max(...rates));
  return min === max ? pct(min) : tr("fx.range", { min: fmtAmount(min, 0), max: fmtAmount(max, 0) });
}

function rateText(row: TaxOverviewRow) {
  if (row.status === "sydonia") return tr("fx.bySydonia");
  if (row.status === "to_confirm") return unknown(tr("fx.toConfirmRate"));
  if (row.amendment && row.amendment.scope === "all") return pct(row.amendment.rate);
  if (row.status === "export_only") return tr("fx.exportCodes", { range: rateRange(row), n: row.values.reduce((a, [, n]) => a + n, 0) });
  if (row.distinct > 1) {
    if (row.empty_means_none) return tr("fx.someCodes", { range: rateRange(row), n: row.values.reduce((a, [, n]) => a + n, 0) });
    const [main, n] = row.values[0];
    return row.code === "TVA" ? tr("fx.mostly", { rate: pct(main), n: fmtAmount(String(n), 0) }) : tr("fx.byCode", { range: rateRange(row) });
  }
  return row.common_rate ? pct(row.common_rate) : unknown(tr("fx.unknownRate"));
}

const STATUS: Record<TaxOverviewRow["status"], [Tone, MessageKey]> = {
  verified: ["green", "fx.st.verified"],
  from_schedule: ["blue", "fx.st.fromSchedule"],
  to_confirm: ["gray", "fx.st.toConfirm"],
  set: ["green", "fx.st.set"],
  export_only: ["gray", "fx.st.exportOnly"],
  sydonia: ["gray", "fx.st.sydonia"],
};

const SOURCES: Record<TaxAmendment["source_kind"], MessageKey> = {
  finance_law: "fx.src.finance_law",
  cemac_act: "fx.src.cemac_act",
  customs_circular: "fx.src.customs_circular",
  operator: "fx.src.operator",
};

const dotted = (code: string) => (code.length === 8 ? `${code.slice(0, 4)}.${code.slice(4, 6)}.${code.slice(6)}` : code);

/** Onglet « Taxes et règles » du référentiel : barème actif, formule, lignes à revoir, historique. */
export function TaxesPanel() {
  const [data, setData] = useState<TaxOverview | null>(null);
  const [failed, setFailed] = useState(false);
  const [editing, setEditing] = useState<{ tax: string } | null>(null);
  const [review, setReview] = useState<string | null>(null);

  const load = () => api.taxOverview().then(setData, () => setFailed(true));
  useEffect(() => {
    void load();
  }, []);

  if (failed) return <p className="empty">{tr("fx.loadError")}</p>;
  if (!data) return <p className="muted">{tr("loading")}</p>;
  if (editing)
    return (
      <AmendmentForm
        tax={editing.tax}
        version={data.version}
        onCancel={() => setEditing(null)}
        onDone={() => {
          setEditing(null);
          void load();
        }}
      />
    );

  const schedule = data.schedule;
  const counts = data.review;
  const toReview = (counts.tec_difference ?? 0) + (counts.empty_tax ?? 0);
  const last = data.history[0];
  return (
    <>
      <div className="stats stats-3">
        <StatCard
          icon="percent"
          tone="green"
          label={tr("fx.inForce")}
          value={tr("fx.version", { n: data.version })}
          hint={schedule ? tr("fx.importedOn", { label: schedule.label, date: fmtDate(schedule.imported_at) }) : tr("fx.noSchedule")}
        />
        <StatCard
          icon="clock"
          tone="blue"
          label={tr("fx.lastChange")}
          value={last ? fmtDate(last.created_at) : schedule ? fmtDate(schedule.imported_at) : "—"}
          hint={last ? tr("fx.by", { who: last.created_by }) : schedule?.label}
        />
        <StatCard icon="alert" tone="amber" label={tr("fx.toReview")} value={schedule ? toReview : "—"} hint={tr("fx.toReviewHint")} />
      </div>

      <section className="card" aria-labelledby="taxes-title">
        <h2 id="taxes-title" className="card-title">{tr("fx.title")}</h2>
        {!schedule && <p className="note-amber small">{tr("fx.noScheduleText")}</p>}
        <div className="table-wrap">
          <table className="data">
            <thead>
              <tr>
                <th scope="col">{tr("ref.code")}</th>
                <th scope="col">{tr("ref.tax")}</th>
                <th scope="col">{tr("fx.baseCol")}</th>
                <th scope="col">{tr("ref.rate")}</th>
                <th scope="col">{tr("ref.source")}</th>
                <th scope="col">{tr("ref.state")}</th>
                <th scope="col"><span className="visually-hidden">{tr("fx.actions")}</span></th>
              </tr>
            </thead>
            <tbody>
              {data.taxes.map((row) => {
                const [tone, label] = STATUS[row.status];
                return (
                  <tr key={row.code}>
                    <td><strong>{row.code}</strong></td>
                    <td>{taxName(row.code)}</td>
                    <td className="small">{row.status === "export_only" ? "—" : row.scope === "declaration" ? tr("fx.perDeclaration") : baseName(row.base_kind)}</td>
                    <td>{rateText(row)}</td>
                    <td className="small">
                      {row.amendment ? tr("fx.amendmentN", { n: row.amendment.sequence }) : row.scope === "declaration" ? tr("fx.declaration") : schedule?.label ?? "—"}
                    </td>
                    <td><Chip tone={tone}>{tr(label)}</Chip></td>
                    <td>
                      {data.can_edit && row.status !== "export_only" && row.status !== "sydonia" && schedule && (
                        <button type="button" className="btn-outline-small" onClick={() => setEditing({ tax: row.code })}>
                          {tr("fx.edit")}
                        </button>
                      )}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
        <p className="muted small" style={{ marginTop: 12 }}>{tr("fx.verifiedNote")}</p>
      </section>

      <div className="tx-row">
        <section className="card">
          <h2 className="card-title">{tr("fx.formula")}</h2>
          <p className="tx-formula">
            <b>DDI</b>, <b>TCI</b>, <b>CCI</b>, <b>OAD</b>, <b>CAF</b> {tr("fx.onValue")}
            <br />
            <b>DA</b> {tr("fx.onValueDdi")}
            <br />
            <b>TVA</b> {tr("fx.and")} <b>CSS</b> {tr("fx.onValueDdiDa")}
          </p>
          <p className="muted small" style={{ marginTop: 10 }}>{tr("fx.formulaNote")}</p>
        </section>
        <section className="card">
          <h2 className="card-title">{tr("fx.toReview")}</h2>
          <ul className="tx-todo">
            {REVIEW_KINDS.map((kind) => (
              <li key={kind}>
                <span className="tx-num">{counts[kind] ?? 0}</span>
                <div>
                  <strong>{tr(`fx.rv.${kind}` as MessageKey)}</strong>
                  <span>{tr(`fx.rv.${kind}.hint` as MessageKey)}</span>
                </div>
                {(counts[kind] ?? 0) > 0 && (
                  <button type="button" className="btn-small" aria-expanded={review === kind} onClick={() => setReview(review === kind ? null : kind)}>
                    {review === kind ? tr("fx.hideList") : tr("fx.seeList")}
                  </button>
                )}
              </li>
            ))}
          </ul>
        </section>
        <section className="card">
          <h2 className="card-title">{tr("fx.history")}</h2>
          <ul className="tx-hist">
            {data.history.map((a) => (
              <li key={a.sequence} className={a.sequence === data.history[0].sequence ? "tx-on" : undefined}>
                <strong>
                  {tr("fx.version", { n: a.version })}
                  {a.sequence === data.history[0].sequence && ` · ${tr("fx.current")}`}
                </strong>
                <span>{fmtDate(a.created_at)} · {a.created_by}</span>
                <span className="muted">
                  {tr("fx.historyLine", {
                    tax: a.tax,
                    scope: a.hs_code ? dotted(a.hs_code) : tr("fx.allCodes"),
                    from: a.previous_rate ? pct(a.previous_rate) : "—",
                    to: pct(a.rate),
                    date: fmtDate(a.effective_from),
                  })}
                </span>
                <span className="tx-src">{tr(SOURCES[a.source_kind])}{a.source_reference && ` · ${a.source_reference}`}</span>
              </li>
            ))}
            {schedule && (
              <li className={data.history.length ? undefined : "tx-on"}>
                <strong>{tr("fx.version", { n: 1 })}{data.history.length === 0 && ` · ${tr("fx.current")}`}</strong>
                <span>{fmtDate(schedule.imported_at)}</span>
                <span className="muted">{tr("fx.importLine", { label: schedule.label, n: fmtAmount(String(schedule.counts.lines ?? 0), 0) })}</span>
              </li>
            )}
          </ul>
          <p className="muted small" style={{ marginTop: 12 }}>{tr("fx.historyNote")}</p>
        </section>
        <p className="tx-ro">
          <Icon name="shield" size={18} />
          <span>{tr("fx.readOnly")}</span>
        </p>
      </div>
      {review && <ReviewList kind={review} />}
    </>
  );
}

function ReviewList({ kind }: { kind: string }) {
  const [page, setPage] = useState(1);
  const [data, setData] = useState<{ count: number; results: ScheduleLineInfo[] } | null>(null);
  useEffect(() => {
    setData(null);
    api.taxReview(kind, page).then(setData, () => setData({ count: 0, results: [] }));
  }, [kind, page]);
  return (
    <section className="card" aria-labelledby="review-title" style={{ marginTop: 20 }}>
      <h2 id="review-title" className="card-title">{tr(`fx.rv.${kind}` as MessageKey)}</h2>
      {!data ? (
        <p className="muted">{tr("loading")}</p>
      ) : (
        <>
          <div className="table-wrap">
            <table className="data compact">
              <thead>
                <tr>
                  <th scope="col">{tr("ref.code")}</th>
                  <th scope="col">{tr("fx.national")}</th>
                  <th scope="col">{tr("col.label")}</th>
                  <th scope="col">DDI</th>
                  <th scope="col">{tr("fx.tecDd")}</th>
                  <th scope="col">{tr("fx.emptyTaxes")}</th>
                  <th scope="col">{tr("fx.sheetRow")}</th>
                </tr>
              </thead>
              <tbody>
                {data.results.map((ln) => (
                  <tr key={ln.row_number}>
                    <td className="code">{dotted(ln.hs_code)}</td>
                    <td>{ln.national_code}</td>
                    <td className="small">{ln.label}</td>
                    <td>{ln.rates.DDI ? pct(ln.rates.DDI) : "—"}</td>
                    <td>{ln.reference.dd_raw?.toUpperCase() === "EXO" ? "EXO" : ln.reference.dd_percent ? pct(ln.reference.dd_percent) : "—"}</td>
                    <td className="small">
                      {Object.entries(ln.rates)
                        .filter(([tax, raw]) => !raw && !["DSO", "DA"].includes(tax))
                        .map(([tax]) => tax)
                        .join(", ") || "—"}
                    </td>
                    <td>{ln.row_number}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <div className="action-bar">
            <span className="muted small">{tr("fx.count", { n: data.count })}</span>
            <button type="button" className="btn-small" disabled={page === 1} onClick={() => setPage(page - 1)}>{tr("fx.prev")}</button>
            <button type="button" className="btn-small" disabled={page * 200 >= data.count} onClick={() => setPage(page + 1)}>{tr("fx.next")}</button>
          </div>
        </>
      )}
    </section>
  );
}

/** Formulaire de modification d'un taux : réservé à l'admin ClairTransit (le serveur le vérifie aussi). */
export function AmendmentForm({
  tax: initialTax,
  code: initialCode = "",
  version,
  onCancel,
  onDone,
}: {
  tax?: string;
  code?: string;
  version: number;
  onCancel: () => void;
  onDone: (a: TaxAmendment) => void;
}) {
  const [tax, setTax] = useState(initialTax ?? "DDI");
  const [scope, setScope] = useState<"code" | "all">(initialCode ? "code" : SINGLE_RATE.has(initialTax ?? "") ? "all" : "code");
  const [code, setCode] = useState(initialCode);
  const [current, setCurrent] = useState<CodeRates | null>(null);
  const [rate, setRate] = useState("");
  const [date, setDate] = useState("");
  const [sourceKind, setSourceKind] = useState<AmendmentInput["source_kind"]>("finance_law");
  const [reference, setReference] = useState("");
  const [reason, setReason] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const forcedAll = tax === "RI";
  const effectiveScope = forcedAll ? "all" : scope;
  const digits = code.replace(/\D/g, "");

  useEffect(() => {
    setCurrent(null);
    if (effectiveScope === "code" && digits.length === 8) api.codeRates(digits).then(setCurrent, () => setCurrent(null));
  }, [digits, effectiveScope]);

  const currentRate = current?.rates.find((r) => r.tax === tax);

  async function submit(e: FormEvent) {
    e.preventDefault();
    setSaving(true);
    setError(null);
    try {
      const saved = await api.amendRate({
        tax,
        scope: effectiveScope,
        hs_code: effectiveScope === "code" ? digits : "",
        rate: rate.replace(",", "."),
        effective_from: date,
        source_kind: sourceKind,
        source_reference: reference,
        reason,
      });
      onDone(saved);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : tr("saveError"));
    } finally {
      setSaving(false);
    }
  }

  return (
    <form className="card tx-dialog nc-form" aria-labelledby="edit-title" onSubmit={(e) => void submit(e)}>
      <h2 id="edit-title" className="nc-h2">{tr("fx.editTitle")}</h2>
      <label className="nc-field">
        <span className="nc-label">{tr("ref.tax")} *</span>
        <select value={tax} onChange={(e) => setTax(e.target.value)}>
          {AMENDABLE.map((c) => (
            <option key={c} value={c}>{c} · {taxName(c)}</option>
          ))}
        </select>
      </label>
      {!forcedAll && (
        <fieldset className="nc-field">
          <legend className="nc-label">{tr("fx.appliesTo")}</legend>
          <div className="tx-choices">
            <label className={`tx-choice${scope === "code" ? " tx-choice-on" : ""}`}>
              <input type="radio" name="scope" checked={scope === "code"} onChange={() => setScope("code")} />
              <span><strong>{tr("fx.thisCode")}</strong><small>{digits.length === 8 ? dotted(digits) : tr("fx.codeToEnter")}</small></span>
            </label>
            <label className={`tx-choice${scope === "all" ? " tx-choice-on" : ""}`}>
              <input type="radio" name="scope" checked={scope === "all"} onChange={() => setScope("all")} />
              <span><strong>{tr("fx.allCodesCap")}</strong><small>{tr("fx.allCodesHint")}</small></span>
            </label>
          </div>
        </fieldset>
      )}
      {effectiveScope === "code" && (
        <label className="nc-field">
          <span className="nc-label">{tr("fx.hsCode")} *</span>
          <input type="text" value={code} readOnly={!!initialCode} required inputMode="numeric" placeholder="0401.10.00" onChange={(e) => setCode(e.target.value)} />
          {current?.label && <small className="muted">{current.label}</small>}
        </label>
      )}
      {effectiveScope === "code" && current && currentRate && (
        <div className="tx-cur">
          <span>{tr("fx.currentRate")}</span>
          <strong>{currentRate.status === "none" ? tr("fx.noExcise") : currentRate.rate !== null ? pct(currentRate.rate) : tr("fx.unknownRate")}</strong>
          <span className="muted">{tr("fx.version", { n: current.version })}{currentRate.cell && ` · ${tr("fx.cell", { cell: currentRate.cell })}`}</span>
          {tax === "DDI" && current.reference.dd_percent && <Chip tone="amber">{tr("fx.tec", { rate: pct(current.reference.dd_percent) })}</Chip>}
        </div>
      )}
      <div className="tx-pair">
        <label className="nc-field">
          <span className="nc-label">{tr("fx.newRate")} *</span>
          <input type="text" inputMode="decimal" required value={rate} onChange={(e) => setRate(e.target.value)} />
        </label>
        <label className="nc-field">
          <span className="nc-label">{tr("fx.effectiveFrom")} *</span>
          <input type="date" required value={date} onChange={(e) => setDate(e.target.value)} />
        </label>
      </div>
      <label className="nc-field">
        <span className="nc-label">{tr("ref.source")} *</span>
        <select value={sourceKind} onChange={(e) => setSourceKind(e.target.value as AmendmentInput["source_kind"])}>
          {(Object.keys(SOURCES) as AmendmentInput["source_kind"][]).map((k) => (
            <option key={k} value={k}>{tr(SOURCES[k])}</option>
          ))}
        </select>
      </label>
      <label className="nc-field">
        <span className="nc-label">{tr("fx.reference")}{sourceKind !== "operator" && " *"}</span>
        <input type="text" value={reference} required={sourceKind !== "operator"} placeholder={tr("fx.referencePh")} onChange={(e) => setReference(e.target.value)} />
      </label>
      <label className="nc-field">
        <span className="nc-label">{tr("fx.reason")} *</span>
        <textarea required value={reason} onChange={(e) => setReason(e.target.value)} />
      </label>
      <p className="note-blue small tx-note">
        <Icon name="history" size={18} />
        <span>{tr("fx.createsVersion", { n: version + 1 })}</span>
      </p>
      <p className="tx-ro">
        <Icon name="shield" size={18} />
        <span>{tr("fx.reservedNote")}</span>
      </p>
      {error && <p className="error" role="alert">{error}</p>}
      <div className="tx-btns">
        <button type="button" className="btn-secondary" onClick={onCancel}>{tr("cancel")}</button>
        <button type="submit" className="btn-primary" disabled={saving}>{tr("fx.save")}</button>
      </div>
    </form>
  );
}

/** Bloc « Taxes et taux » de la fiche d'un code : taux applicables aujourd'hui, avec leur cellule. */
export function CodeTaxes({ code }: { code: string | null }) {
  const digits = (code ?? "").replace(/\D/g, "");
  const [data, setData] = useState<CodeRates | null>(null);
  const [editing, setEditing] = useState(false);
  const load = () => api.codeRates(digits).then(setData, () => setData(null));
  useEffect(() => {
    setData(null);
    setEditing(false);
    if (digits.length === 8) void load();
  }, [digits]);
  if (digits.length !== 8 || !data || (!data.row_number && data.subpositions.length === 0 && !data.history.length)) return null;
  const tecDdi = data.reference.dd_percent;
  const ddi = data.rates.find((r) => r.tax === "DDI");
  return (
    <>
      <h3>{tr("ref.taxesRates")}</h3>
      <p className="muted small">{tr("fx.codeVersion", { n: data.version })}</p>
      {data.notes.map((n) => (
        <p key={n} className="note-amber small" role="note">{n}</p>
      ))}
      <table className="data compact">
        <thead>
          <tr><th scope="col">{tr("ref.tax")}</th><th scope="col">{tr("ref.rate")}</th><th scope="col">{tr("ref.source")}</th></tr>
        </thead>
        <tbody>
          {data.rates
            .filter((r) => r.tax !== "DSO" || r.rate !== null)
            .map((r) => (
              <tr key={r.tax}>
                <td><strong>{r.tax}</strong></td>
                <td>
                  {r.status === "none"
                    ? tr("fx.noExcise")
                    : r.rate !== null
                      ? pct(r.rate)
                      : unknown(r.tax === "RI" ? tr("fx.toConfirmRate") : tr("fx.unknownRate"))}
                  {r.status === "export_only" && <span className="block small muted">{tr("fx.st.exportOnly")}</span>}
                </td>
                <td className="small">
                  {r.source === "amendment" && r.amendment
                    ? tr("fx.amendmentFrom", { n: r.amendment.sequence, date: fmtDate(r.amendment.effective_from) })
                    : r.cell
                      ? tr("fx.cell", { cell: r.cell })
                      : "—"}
                </td>
              </tr>
            ))}
        </tbody>
      </table>
      {data.cumulative_rate && (
        <p className="note-blue small" role="note" style={{ marginTop: 8 }}>{tr("fx.cumulative", { rate: pct(data.cumulative_rate) })}</p>
      )}
      {data.subpositions.length > 1 && (
        <p className="muted small">
          {tr("fx.subpositions", { list: data.subpositions.map((s) => s.national_code).join(", ") })}
        </p>
      )}
      {tecDdi && ddi?.rate && Number(tecDdi) !== Number(ddi.rate) && (
        <div className="tx-diff">
          <p>{tr("fx.tecDiff", { gabon: pct(ddi.rate), tec: pct(tecDdi) })}</p>
        </div>
      )}
      {data.can_edit && !editing && (
        <button type="button" className="btn-small" style={{ marginTop: 8 }} onClick={() => setEditing(true)}>
          {tr("fx.editRate")}
        </button>
      )}
      {editing && (
        <AmendmentForm
          code={digits}
          version={data.version}
          onCancel={() => setEditing(false)}
          onDone={() => {
            setEditing(false);
            void load();
          }}
        />
      )}
    </>
  );
}

/** Calcul des taxes d'un dossier, rechargé quand le dossier change. */
export function useCaseCalculation(caseId: string, key: unknown) {
  const [data, setData] = useState<CaseCalculation | null>(null);
  const [failed, setFailed] = useState(false);
  useEffect(() => {
    setFailed(false);
    api.caseCalculation(caseId).then(setData, () => setFailed(true));
  }, [caseId, key]);
  return { data, failed };
}

/** Taux d'une taxe sur toutes les lignes : un seul taux, ou « 10 % ou 18 % selon la ligne ». */
function ratesAcross(calc: CaseCalculation, code: string): string | null {
  const taxes = calc.articles.map((a) => a.taxes.find((t) => t.code === code)).filter((t): t is CalcTax => !!t);
  if (code === "RI") return tr("fx.bySydonia");
  if (taxes.some((t) => t.rate === null)) return null;
  if (taxes.length && taxes.every((t) => t.rate_status === "none")) return tr("fx.noExcise");
  const distinct = [...new Set(taxes.map((t) => t.rate as string))].sort((a, b) => Number(a) - Number(b));
  if (!distinct.length) return null;
  return distinct.length === 1 ? pct(distinct[0]) : tr("fx.byLine", { list: distinct.map(pct).join(tr("fx.or")) });
}

export function CalcTaxesTable({ calc }: { calc: CaseCalculation }) {
  const codes = [...TAX_CODES.filter((c) => c !== "DSO")];
  return (
    <div className="table-wrap">
      <table className="data calc-taxes">
        <thead>
          <tr>
            <th scope="col">{tr("col.code")}</th>
            <th scope="col">{tr("col.label")}</th>
            <th scope="col">{tr("col.rate")}</th>
            <th scope="col">{tr("calc.base")}</th>
            <th scope="col" className="num">{tr("col.amountPlain")}</th>
          </tr>
        </thead>
        <tbody>
          {codes.map((code) => {
            const amount = calc.totals.by_tax[code];
            const rate = ratesAcross(calc, code);
            const reason = code === "RI" ? calc.global_taxes[0]?.reason : calc.articles.flatMap((a) => a.taxes).find((t) => t.code === code && t.amount === null)?.reason;
            return (
              <tr key={code}>
                <td><strong>{code}</strong></td>
                <td>{taxName(code)}</td>
                <td>{rate ?? unknown(code === "RI" ? tr("fx.toConfirmRate") : tr("fx.unknownRate"))}</td>
                <td>{code === "RI" ? tr("fx.perDeclaration") : baseName((calc.articles[0]?.taxes.find((t) => t.code === code)?.base_kind ?? "value") as TaxBaseKind)}</td>
                <td className="num">
                  {code === "RI" ? unknown(tr("fx.bySydonia")) : amount !== null && amount !== undefined ? `${xaf(amount)} FCFA` : unknown(reason || tr("fx.unknownAmount"))}
                  {code === "TCI" && <span className="block muted small">{tr("fx.account2")}</span>}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

export function CalcLinesTable({ calc }: { calc: CaseCalculation }) {
  const other = ["CCI", "OAD", "CSS", "CAF"];  // la TCI (compte 2) n'entre pas dans le total
  const sum = (taxes: CalcTax[], codes: string[]) => {
    const picked = taxes.filter((t) => codes.includes(t.code));
    return picked.some((t) => t.amount === null) ? null : String(picked.reduce((a, t) => a + Number(t.amount), 0));
  };
  const cell = (v: string | null, rate?: string | null) =>
    v === null ? unknown(tr("value.unknownM")) : <>{xaf(v)}{rate ? <span className="block muted small">{pct(rate)}</span> : null}</>;
  return (
    <>
      <h3 className="calc-h3">
        {tr("fx.byGoods")} {calc.demo && <span className="tx-fict">{tr("demo.fictitious")}</span>} <span className="muted small">{tr("fx.inFcfa")}</span>
      </h3>
      <div className="table-wrap">
        <table className="data tx-lines">
          <thead>
            <tr>
              <th scope="col">{tr("fx.line")}</th>
              <th scope="col">{tr("fx.hsCode")}</th>
              <th scope="col">{tr("col.label")}</th>
              <th scope="col" className="num">{tr("calc.customsValueCap")}</th>
              <th scope="col" className="num">DDI</th>
              <th scope="col" className="num">TVA</th>
              <th scope="col" className="num">{tr("fx.otherTaxes")}</th>
              <th scope="col" className="num">{tr("fx.total")}</th>
            </tr>
          </thead>
          <tbody>
            {calc.articles.map((a) => {
              const ddi = a.taxes.find((t) => t.code === "DDI");
              const tva = a.taxes.find((t) => t.code === "TVA");
              return (
                <tr key={a.goods_line_id}>
                  <td>{a.ordinal}</td>
                  <td className="code">{a.hs_code ? dotted(a.hs_code) : unknown(a.code_status === "stale" ? tr("fx.codeStale") : tr("fx.codeMissing"))}</td>
                  <td>
                    {a.description}
                    {a.value.notes.map((n) => (
                      <span key={n} className="block small muted">{n}</span>
                    ))}
                  </td>
                  <td className="num">{cell(a.value.xaf)}</td>
                  <td className="num">{cell(ddi?.amount ?? null, ddi?.rate)}</td>
                  <td className="num">{cell(tva?.amount ?? null, tva?.rate)}</td>
                  <td className="num">{cell(sum(a.taxes, other))}</td>
                  <td className="num"><strong>{cell(a.total)}</strong></td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
      <p className="muted small" style={{ marginTop: 8 }}>{tr("fx.linesNote")}</p>
    </>
  );
}
