import { useEffect, useState, type FormEvent } from "react";
import {
  api,
  ApiError,
  type CaseDetail,
  type ExemptionClaim,
  type ExemptionRegime,
  type ExemptionRegimeInput,
  type Membership,
  type TaxAmendment,
} from "./api";
import { Icon } from "./Icon";
import { tr, type MessageKey } from "./i18n";
import { SOURCES, taxName } from "./Taxes";
import { Chip, fmtDate, type Tone } from "./ui";

/** Exonérations (TAX-04) : déclarées par l'admin ClairTransit, demandées et prouvées dans le dossier. */

const errorText = (err: unknown) => (err instanceof ApiError ? err.message : tr("saveError"));
const ratePct = (rate: string) => `${rate.replace(".", ",")} %`;

export function taxesText(taxes: Record<string, string>) {
  return Object.entries(taxes)
    .map(([tax, rate]) => (Number(rate) === 0 ? tr("exo.taxExempt", { tax }) : tr("exo.taxReduced", { tax, rate: ratePct(rate) })))
    .join(" · ");
}

function scopeText(r: ExemptionRegime) {
  const codes = r.hs_prefixes.length ? r.hs_prefixes.join(", ") : tr("exo.allCodes");
  const regimes = r.customs_regimes.length ? r.customs_regimes.join(", ") : tr("exo.allRegimes");
  return `${tr("exo.codes")} : ${codes} · ${tr("exo.regimes")} : ${regimes}`;
}

function periodText(r: ExemptionRegime) {
  return r.valid_to ? tr("exo.period", { from: fmtDate(r.valid_from), to: fmtDate(r.valid_to) }) : tr("exo.since", { from: fmtDate(r.valid_from) });
}

function SourceText({ regime }: { regime: ExemptionRegime }) {
  return (
    <>
      {tr(SOURCES[regime.source_kind])}
      {regime.source_reference && ` · ${regime.source_reference}`}
      {!regime.official && <span className="block"><Chip tone="amber">{tr("exo.noOfficialText")}</Chip></span>}
    </>
  );
}

/** Référentiel › Exonérations : liste, déclaration et désactivation (admin ClairTransit seulement). */
export function ExemptionsPanel() {
  const [data, setData] = useState<{ results: ExemptionRegime[]; taxes: string[]; can_edit: boolean } | null>(null);
  const [failed, setFailed] = useState(false);
  const [creating, setCreating] = useState(false);
  const [closing, setClosing] = useState<string | null>(null);
  const [reason, setReason] = useState("");
  const [error, setError] = useState<string | null>(null);

  const load = () => api.exemptionRegimes().then(setData, () => setFailed(true));
  useEffect(() => {
    void load();
  }, []);

  if (failed) return <p className="empty">{tr("exo.loadError")}</p>;
  if (!data) return <p className="muted">{tr("loading")}</p>;
  if (creating)
    return (
      <ExemptionForm
        taxes={data.taxes}
        onCancel={() => setCreating(false)}
        onDone={() => {
          setCreating(false);
          void load();
        }}
      />
    );

  async function deactivate(id: string) {
    setError(null);
    try {
      await api.deactivateExemptionRegime(id, reason);
      setClosing(null);
      setReason("");
      void load();
    } catch (err) {
      setError(errorText(err));
    }
  }

  return (
    <section className="card" aria-labelledby="exo-title">
      <div className="card-head">
        <h2 id="exo-title" className="card-title">{tr("exo.title")}</h2>
        {data.can_edit && (
          <button type="button" className="btn-primary" onClick={() => setCreating(true)}>{tr("exo.declare")}</button>
        )}
      </div>
      <p className="muted small">{tr("exo.help")}</p>
      {data.results.length === 0 ? (
        <p className="empty">{tr("exo.none")}</p>
      ) : (
        <div className="table-wrap">
          <table className="data">
            <thead>
              <tr>
                <th scope="col">{tr("exo.reference")}</th>
                <th scope="col">{tr("exo.taxes")}</th>
                <th scope="col">{tr("exo.scope")}</th>
                <th scope="col">{tr("exo.proofs")}</th>
                <th scope="col">{tr("ref.source")}</th>
                <th scope="col">{tr("ref.state")}</th>
                {data.can_edit && <th scope="col"><span className="visually-hidden">{tr("fx.actions")}</span></th>}
              </tr>
            </thead>
            <tbody>
              {data.results.map((r) => (
                <tr key={r.id}>
                  <td>
                    <strong>{r.code}</strong>
                    <span className="block small">{r.label}</span>
                    {r.conditions && <span className="block small muted">{r.conditions}</span>}
                  </td>
                  <td className="small">{taxesText(r.taxes)}</td>
                  <td className="small">{scopeText(r)}<span className="block muted">{periodText(r)}</span></td>
                  <td className="small">{r.required_documents.join(" · ")}</td>
                  <td className="small"><SourceText regime={r} /></td>
                  <td>
                    <Chip tone={r.is_active ? "green" : "gray"}>{tr(r.is_active ? "exo.active" : "exo.inactive")}</Chip>
                    {!r.is_active && r.deactivation_reason && <span className="block small muted">{r.deactivation_reason}</span>}
                  </td>
                  {data.can_edit && (
                    <td>
                      {r.is_active && closing !== r.id && (
                        <button type="button" className="btn-outline-small" onClick={() => { setClosing(r.id); setReason(""); setError(null); }}>
                          {tr("exo.deactivate")}
                        </button>
                      )}
                      {closing === r.id && (
                        <form className="nc-form" onSubmit={(e) => { e.preventDefault(); void deactivate(r.id); }}>
                          <label className="nc-field">
                            <span className="nc-label">{tr("exo.deactivateReason")} *</span>
                            <input type="text" required value={reason} onChange={(e) => setReason(e.target.value)} />
                          </label>
                          {error && <p className="error" role="alert">{error}</p>}
                          <div className="tx-btns">
                            <button type="button" className="btn-secondary" onClick={() => setClosing(null)}>{tr("cancel")}</button>
                            <button type="submit" className="btn-primary">{tr("exo.deactivate")}</button>
                          </div>
                        </form>
                      )}
                    </td>
                  )}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      <p className="tx-ro">
        <Icon name="shield" size={18} />
        <span>{tr(data.can_edit ? "exo.canEdit" : "exo.readOnly")}</span>
      </p>
    </section>
  );
}

export function ExemptionForm({ taxes, onCancel, onDone }: { taxes: string[]; onCancel: () => void; onDone: (r: ExemptionRegime) => void }) {
  const [form, setForm] = useState<ExemptionRegimeInput>({
    code: "",
    label: "",
    conditions: "",
    taxes: {},
    hs_prefixes: "",
    customs_regimes: "",
    required_documents: [],
    valid_from: "",
    valid_to: "",
    source_kind: "finance_law",
    source_reference: "",
    reason: "",
  });
  const [documents, setDocuments] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const set = (patch: Partial<ExemptionRegimeInput>) => setForm({ ...form, ...patch });
  const toggleTax = (tax: string) => {
    const next = { ...form.taxes };
    if (tax in next) delete next[tax];
    else next[tax] = "0";
    set({ taxes: next });
  };

  async function submit(e: FormEvent) {
    e.preventDefault();
    setSaving(true);
    setError(null);
    try {
      const rates = Object.fromEntries(Object.entries(form.taxes).map(([k, v]) => [k, v.replace(",", ".")]));
      const required = documents.split("\n").map((d) => d.trim()).filter(Boolean);
      onDone(await api.createExemptionRegime({ ...form, taxes: rates, required_documents: required }));
    } catch (err) {
      setError(errorText(err));
    } finally {
      setSaving(false);
    }
  }

  return (
    <form className="card tx-dialog nc-form" aria-labelledby="exo-form-title" onSubmit={(e) => void submit(e)}>
      <h2 id="exo-form-title" className="nc-h2">{tr("exo.declareTitle")}</h2>
      <div className="tx-pair">
        <label className="nc-field">
          <span className="nc-label">{tr("exo.reference")} *</span>
          <input type="text" required maxLength={40} value={form.code} placeholder={tr("exo.referencePh")} onChange={(e) => set({ code: e.target.value })} />
        </label>
        <label className="nc-field">
          <span className="nc-label">{tr("exo.label")} *</span>
          <input type="text" required maxLength={200} value={form.label} onChange={(e) => set({ label: e.target.value })} />
        </label>
      </div>
      <fieldset className="nc-field">
        <legend className="nc-label">{tr("exo.taxesLegend")} *</legend>
        {taxes.map((tax) => (
          <div key={tax} className="exchange-row">
            <label>
              <input type="checkbox" checked={tax in form.taxes} onChange={() => toggleTax(tax)} /> {tax} · {taxName(tax)}
            </label>
            {tax in form.taxes && (
              <label>
                {tr("exo.appliedRate")}
                <input type="text" inputMode="decimal" required value={form.taxes[tax]} onChange={(e) => set({ taxes: { ...form.taxes, [tax]: e.target.value } })} />
              </label>
            )}
          </div>
        ))}
        <small className="muted">{tr("exo.appliedRateHint")}</small>
      </fieldset>
      <div className="tx-pair">
        <label className="nc-field">
          <span className="nc-label">{tr("exo.codes")}</span>
          <input type="text" inputMode="numeric" value={form.hs_prefixes} placeholder="8701, 870421" onChange={(e) => set({ hs_prefixes: e.target.value })} />
          <small className="muted">{tr("exo.codesHint")}</small>
        </label>
        <label className="nc-field">
          <span className="nc-label">{tr("exo.regimes")}</span>
          <input type="text" value={form.customs_regimes} onChange={(e) => set({ customs_regimes: e.target.value })} />
          <small className="muted">{tr("exo.regimesHint")}</small>
        </label>
      </div>
      <label className="nc-field">
        <span className="nc-label">{tr("exo.proofs")} *</span>
        <textarea required value={documents} placeholder={tr("exo.proofsPh")} onChange={(e) => setDocuments(e.target.value)} />
      </label>
      <label className="nc-field">
        <span className="nc-label">{tr("exo.conditions")}</span>
        <textarea value={form.conditions} onChange={(e) => set({ conditions: e.target.value })} />
      </label>
      <div className="tx-pair">
        <label className="nc-field">
          <span className="nc-label">{tr("exo.validFrom")} *</span>
          <input type="date" required value={form.valid_from} onChange={(e) => set({ valid_from: e.target.value })} />
        </label>
        <label className="nc-field">
          <span className="nc-label">{tr("exo.validTo")}</span>
          <input type="date" value={form.valid_to} onChange={(e) => set({ valid_to: e.target.value })} />
        </label>
      </div>
      <label className="nc-field">
        <span className="nc-label">{tr("ref.source")} *</span>
        <select value={form.source_kind} onChange={(e) => set({ source_kind: e.target.value as TaxAmendment["source_kind"] })}>
          {(Object.keys(SOURCES) as TaxAmendment["source_kind"][]).map((k) => (
            <option key={k} value={k}>{tr(SOURCES[k])}</option>
          ))}
        </select>
      </label>
      <label className="nc-field">
        <span className="nc-label">{tr("fx.reference")}{form.source_kind !== "operator" && " *"}</span>
        <input type="text" required={form.source_kind !== "operator"} value={form.source_reference} placeholder={tr("fx.referencePh")} onChange={(e) => set({ source_reference: e.target.value })} />
      </label>
      <label className="nc-field">
        <span className="nc-label">{tr("fx.reason")} *</span>
        <textarea required value={form.reason} onChange={(e) => set({ reason: e.target.value })} />
      </label>
      <p className="tx-ro">
        <Icon name="shield" size={18} />
        <span>{tr("exo.formNote")}</span>
      </p>
      {error && <p className="error" role="alert">{error}</p>}
      <div className="tx-btns">
        <button type="button" className="btn-secondary" onClick={onCancel}>{tr("cancel")}</button>
        <button type="submit" className="btn-primary" disabled={saving || !Object.keys(form.taxes).length}>{tr("fx.save")}</button>
      </div>
    </form>
  );
}

const CLAIM_STATUS: Record<ExemptionClaim["status"], [Tone, MessageKey]> = {
  requested: ["amber", "exo.st.requested"],
  validated: ["green", "exo.st.validated"],
  rejected: ["red", "exo.st.rejected"],
  withdrawn: ["gray", "exo.st.withdrawn"],
};

type Draft = { regime_id: string; goods_line_ids: string[]; proof_ids: string[]; proof_reference: string };

/** Onglet Calculs : exonérations demandées dans le dossier, justificatif et décision. */
export function CaseExemptions({ detail, membership, onChanged }: { detail: CaseDetail; membership: Membership; onChanged: () => void }) {
  const revision = detail.revision;
  const [claims, setClaims] = useState<ExemptionClaim[] | null>(null);
  const [regimes, setRegimes] = useState<ExemptionRegime[]>([]);
  const [draft, setDraft] = useState<Draft | null>(null);
  const [editing, setEditing] = useState<string | null>(null);
  const [rejecting, setRejecting] = useState<string | null>(null);
  const [reason, setReason] = useState("");
  const [error, setError] = useState<string | null>(null);
  const canEdit = revision.is_editable && membership.roles.some((r) => r === "declarant" || r === "validator");
  const canDecide = revision.is_editable && membership.roles.some((r) => r === "validator" || r === "org_admin");
  const documents = revision.documents.filter((d) => !d.replaced_by_id);
  const docName = (id: string) => documents.find((d) => d.id === id)?.document.original_name ?? tr("exo.pieceRemoved");

  const load = () => api.caseExemptions(detail.id).then((r) => setClaims(r.results), () => setClaims([]));
  useEffect(() => {
    void load();
  }, [detail]);
  useEffect(() => {
    if (canEdit) api.exemptionRegimes(true).then((r) => setRegimes(r.results), () => setRegimes([]));
  }, [canEdit]);

  async function run(action: () => Promise<unknown>) {
    setError(null);
    try {
      await action();
      setDraft(null);
      setEditing(null);
      setRejecting(null);
      setReason("");
      onChanged();
      void load();
    } catch (err) {
      setError(errorText(err));
    }
  }

  const toggle = (list: string[], id: string) => (list.includes(id) ? list.filter((x) => x !== id) : [...list, id]);

  // Fonction de rendu (pas un composant) : la saisie garde le focus d'un rendu à l'autre.
  function draftFields(value: Draft, onChange: (d: Draft) => void) {
    return (
      <>
        <fieldset className="nc-field">
          <legend className="nc-label">{tr("exo.articles")}</legend>
          <small className="muted">{tr("exo.articlesHint")}</small>
          {revision.goods_lines.map((g) => (
            <label key={g.id} className="block small">
              <input type="checkbox" checked={value.goods_line_ids.includes(g.id)} onChange={() => onChange({ ...value, goods_line_ids: toggle(value.goods_line_ids, g.id) })} />{" "}
              {g.ordinal}. {g.description}
            </label>
          ))}
        </fieldset>
        <fieldset className="nc-field">
          <legend className="nc-label">{tr("exo.proofPieces")}</legend>
          {documents.length === 0 && <small className="muted">{tr("exo.noPieces")}</small>}
          {documents.map((d) => (
            <label key={d.id} className="block small">
              <input type="checkbox" checked={value.proof_ids.includes(d.id)} onChange={() => onChange({ ...value, proof_ids: toggle(value.proof_ids, d.id) })} />{" "}
              {d.document.original_name}
            </label>
          ))}
        </fieldset>
        <label className="nc-field">
          <span className="nc-label">{tr("exo.proofReference")}</span>
          <input type="text" maxLength={120} value={value.proof_reference} onChange={(e) => onChange({ ...value, proof_reference: e.target.value })} />
        </label>
      </>
    );
  }

  const selected = draft ? regimes.find((r) => r.id === draft.regime_id) : undefined;
  return (
    <section className="card" aria-labelledby="case-exo-title">
      <h2 id="case-exo-title" className="card-title">{tr("exo.caseTitle")}</h2>
      <p className="muted small">{tr("exo.caseHelp")}</p>
      {claims === null && <p className="muted">{tr("loading")}</p>}
      {claims?.length === 0 && !draft && <p className="muted small">{tr("exo.caseNone")}</p>}
      <ul className="tx-hist">
        {claims?.map((c) => {
          const [tone, label] = CLAIM_STATUS[c.status];
          const open = c.status === "requested";
          return (
            <li key={c.id}>
              <strong>{c.regime.code} · {c.regime.label}</strong>
              <span><Chip tone={tone}>{tr(label)}</Chip></span>
              <span className="small">{taxesText(c.regime.taxes)}</span>
              <span className="small muted">
                {c.goods_line_ids.length ? tr("exo.someArticles", { n: c.goods_line_ids.length }) : tr("exo.allArticles")}
              </span>
              <span className="small">{tr("exo.required", { list: c.regime.required_documents.join(" · ") })}</span>
              <span className="small">
                {c.proof_ids.length ? tr("exo.joined", { list: c.proof_ids.map(docName).join(" · ") }) : <span className="tx-prov">{tr("exo.noProof")}</span>}
                {c.proof_reference && ` · ${tr("exo.proofRef", { ref: c.proof_reference })}`}
              </span>
              {c.decided_by && (
                <span className="small muted">
                  {tr("exo.decidedBy", { who: c.decided_by, date: c.decided_at ? fmtDate(c.decided_at) : "" })}
                  {c.decision_reason && ` · ${c.decision_reason}`}
                </span>
              )}
              {!c.regime.official && <span className="small"><Chip tone="amber">{tr("exo.noOfficialText")}</Chip></span>}
              {editing === c.id && draft && (
                <form className="nc-form" onSubmit={(e) => { e.preventDefault(); void run(() => api.updateExemption(detail.id, c.id, { ...draft, row_version: c.row_version })); }}>
                  {draftFields(draft, setDraft)}
                  <div className="tx-btns">
                    <button type="button" className="btn-secondary" onClick={() => { setEditing(null); setDraft(null); }}>{tr("cancel")}</button>
                    <button type="submit" className="btn-primary">{tr("fx.save")}</button>
                  </div>
                </form>
              )}
              {rejecting === c.id && (
                <form className="nc-form" onSubmit={(e) => { e.preventDefault(); void run(() => api.decideExemption(detail.id, c.id, "reject", c.row_version, reason)); }}>
                  <label className="nc-field">
                    <span className="nc-label">{tr("exo.rejectReason")} *</span>
                    <input type="text" required value={reason} onChange={(e) => setReason(e.target.value)} />
                  </label>
                  <div className="tx-btns">
                    <button type="button" className="btn-secondary" onClick={() => setRejecting(null)}>{tr("cancel")}</button>
                    <button type="submit" className="btn-primary">{tr("exo.reject")}</button>
                  </div>
                </form>
              )}
              {open && editing !== c.id && rejecting !== c.id && (canEdit || canDecide) && (
                <div className="tx-btns">
                  {canEdit && (
                    <button type="button" className="btn-outline-small" onClick={() => { setEditing(c.id); setDraft({ regime_id: c.regime.id, goods_line_ids: c.goods_line_ids, proof_ids: c.proof_ids, proof_reference: c.proof_reference }); }}>
                      {tr("exo.edit")}
                    </button>
                  )}
                  {canDecide && (
                    <button type="button" className="btn-small" disabled={!c.proof_ids.length} onClick={() => void run(() => api.decideExemption(detail.id, c.id, "validate", c.row_version))}>
                      {tr("exo.validate")}
                    </button>
                  )}
                  {canDecide && (
                    <button type="button" className="btn-outline-small" onClick={() => { setRejecting(c.id); setReason(""); }}>{tr("exo.reject")}</button>
                  )}
                  {canEdit && (
                    <button type="button" className="btn-outline-small" onClick={() => void run(() => api.decideExemption(detail.id, c.id, "withdraw", c.row_version))}>
                      {tr("exo.withdraw")}
                    </button>
                  )}
                </div>
              )}
            </li>
          );
        })}
      </ul>
      {canEdit && !draft && !editing && (
        regimes.length ? (
          <button type="button" className="btn-secondary" onClick={() => setDraft({ regime_id: regimes[0].id, goods_line_ids: [], proof_ids: [], proof_reference: "" })}>
            {tr("exo.request")}
          </button>
        ) : (
          <p className="muted small">{tr("exo.noneDeclared")}</p>
        )
      )}
      {draft && !editing && (
        <form className="nc-form" aria-label={tr("exo.request")} onSubmit={(e) => { e.preventDefault(); void run(() => api.requestExemption(detail.id, draft)); }}>
          <label className="nc-field">
            <span className="nc-label">{tr("exo.which")} *</span>
            <select value={draft.regime_id} onChange={(e) => setDraft({ ...draft, regime_id: e.target.value })}>
              {regimes.map((r) => (
                <option key={r.id} value={r.id}>{r.code} · {r.label}</option>
              ))}
            </select>
          </label>
          {selected && (
            <p className="note-blue small">
              {taxesText(selected.taxes)} · {scopeText(selected)}
              <span className="block">{tr("exo.required", { list: selected.required_documents.join(" · ") })}</span>
            </p>
          )}
          {draftFields(draft, setDraft)}
          <div className="tx-btns">
            <button type="button" className="btn-secondary" onClick={() => setDraft(null)}>{tr("cancel")}</button>
            <button type="submit" className="btn-primary">{tr("exo.send")}</button>
          </div>
        </form>
      )}
      {error && <p className="error" role="alert">{error}</p>}
    </section>
  );
}
