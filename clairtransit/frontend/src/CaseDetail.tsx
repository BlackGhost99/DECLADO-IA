import { useCallback, useEffect, useState, type FormEvent } from "react";
import {
  api,
  ApiError,
  type AuditEntry,
  type CaseDetail,
  type CaseDocument,
  type CodeCheck,
  type GoodsLine,
  type Invoice,
  type Me,
  type Membership,
  type Preview,
  type Revision,
} from "./api";
import { errorText, type EditionOption } from "./ui";

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

/** « 1 500,00 » → « 1500.00 » ; le texte reste une chaîne, jamais un nombre flottant. */
export function decimalInput(value: string): string | null {
  const v = value.replace(/\s/g, "");
  if (!v) return null;
  return v.includes(",") && !v.includes(".") ? v.replace(",", ".") : v;
}

function formatBytes(n: number) {
  return n > 1024 * 1024 ? `${(n / 1024 / 1024).toFixed(1)} Mo` : `${Math.max(1, Math.round(n / 1024))} Ko`;
}

export function CaseDetailView({
  caseId,
  me,
  membership,
  editions,
  onBack,
}: {
  caseId: string;
  me: Pick<Me, "id">;
  membership: Membership;
  editions: EditionOption[];
  onBack: () => void;
}) {
  const canEdit = membership.roles.some((r) => r === "declarant" || r === "validator");
  const [detail, setDetail] = useState<CaseDetail | null>(null);
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
    void reload();
  }, [reload]);

  async function act(action: () => Promise<unknown>) {
    setError(null);
    try {
      await action();
    } catch (err) {
      setError(errorText(err, "Action impossible."));
    }
    await reload();
  }

  if (!detail) return <p>{error ?? "Chargement…"}</p>;
  const rev = detail.revision;
  const editable = canEdit && rev.is_editable;

  return (
    <>
      <p>
        <button type="button" className="link" onClick={onBack}>← Tous les dossiers</button>
      </p>
      <section className="card" aria-labelledby="case-title">
        <h2 id="case-title">
          <span className="code">{detail.reference}</span> {detail.title}
        </h2>
        <p className="muted small">
          Révision {rev.revision_no} · {rev.state_label} · {rev.mode_label}. {rev.status_note}
        </p>
        <dl className="facts">
          <dt>Importateur</dt>
          <dd>{detail.importer?.name ?? <em className="muted">à renseigner</em>}</dd>
          <dt>Agent</dt>
          <dd>
            {detail.assigned_to?.email ?? <span className="muted">non affecté</span>}{" "}
            {canEdit && !detail.assigned_to && (
              <button type="button" onClick={() => act(() => api.assignCase(detail.id, me.id, detail.row_version))}>
                Prendre le dossier
              </button>
            )}
          </dd>
        </dl>
        {rev.target_edition?.warning && <p className="warning" role="note">ⓘ {rev.target_edition.warning}</p>}
        {error && <p role="alert" className="error">⚠ {error}</p>}
        <RevisionForm revision={rev} editions={editions} editable={editable} onSave={(data) => act(() => api.updateRevision(rev.id, data))} />
      </section>

      <Completeness revision={rev} />
      <Documents caseId={detail.id} revision={rev} editable={editable} onChange={reload} />
      <Invoices revision={rev} editable={editable} act={act} />
      <GoodsLines revision={rev} editions={editions} editable={editable} act={act} />
      <History caseId={detail.id} version={tick} />
    </>
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
    <form className="row" onSubmit={submit}>
      <fieldset disabled={!editable} className="row plain-fieldset">
        <label>
          Date de déclaration prévue
          <input type="date" value={form.planned_declaration_date} onChange={(e) => setForm({ ...form, planned_declaration_date: e.target.value })} />
        </label>
        <label>
          Régime
          <input value={form.regime} onChange={(e) => setForm({ ...form, regime: e.target.value })} />
        </label>
        <label>
          Édition du référentiel
          <select value={form.target_edition_id} onChange={(e) => setForm({ ...form, target_edition_id: e.target.value })}>
            <option value="">À choisir</option>
            {editions.map((e) => (
              <option key={e.id} value={e.id}>{e.label}</option>
            ))}
          </select>
        </label>
        <button type="submit">Enregistrer</button>
      </fieldset>
    </form>
  );
}

function Completeness({ revision }: { revision: Revision }) {
  const { blocking, warnings } = revision.completeness;
  return (
    <section className="card" aria-labelledby="completeness-title">
      <h2 id="completeness-title">Avant calcul et validation</h2>
      {blocking.length === 0 ? (
        <p>Aucun manque bloquant.</p>
      ) : (
        <>
          <p className="muted small">{blocking.length} élément(s) à compléter. Le brouillon reste enregistrable.</p>
          <ul className="small">
            {blocking.map((b) => (
              <li key={`${b.id}-${b.field}`}>
                <strong>{b.label}</strong> : {b.message}
              </li>
            ))}
          </ul>
        </>
      )}
      {warnings.length > 0 && (
        <>
          <h3>À examiner</h3>
          <ul className="small">
            {warnings.map((w) => (
              <li key={`${w.id}-${w.field}-${w.message}`}>
                <strong>{w.label}</strong> : {w.message}
              </li>
            ))}
          </ul>
        </>
      )}
    </section>
  );
}

function Documents({
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
  const [limits, setLimits] = useState<{ max_bytes: number; accepted: string[] } | null>(null);
  const [file, setFile] = useState<File | null>(null);
  const [usage, setUsage] = useState("invoice");
  const [duplicate, setDuplicate] = useState<{ id: string; original_name: string; cases: string[] }[] | null>(null);
  const [preview, setPreview] = useState<{ doc: CaseDocument; data: Preview } | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api.documentLimits().then(setLimits, () => setLimits(null));
  }, []);

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
      await onChange();
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
      await api.reuseDocument(caseId, id, usage);
      setDuplicate(null);
      setMessage("Pièce existante réutilisée, sans nouveau dépôt.");
      await onChange();
    } catch (err) {
      setError(errorText(err, "Réutilisation impossible."));
    }
  }

  async function open(link: CaseDocument) {
    setError(null);
    try {
      setPreview({ doc: link, data: await api.documentPreview(link.document.id) });
    } catch (err) {
      setError(errorText(err, "Aperçu impossible."));
    }
  }

  async function download(link: CaseDocument) {
    const { url } = await api.documentLink(link.document.id);
    window.location.assign(url);
  }

  return (
    <section className="card" aria-labelledby="docs-title">
      <h2 id="docs-title">Pièces</h2>
      {limits && (
        <p className="muted small">
          Formats acceptés : {limits.accepted.join(", ")}. Taille maximale : {formatBytes(limits.max_bytes)}. Le contenu
          réel du fichier est contrôlé ; l'original est conservé tel quel, avec son empreinte.
        </p>
      )}
      {revision.documents.length === 0 ? (
        <p className="muted">Aucune pièce.</p>
      ) : (
        <table>
          <thead>
            <tr>
              <th scope="col">Pièce</th><th scope="col">Usage</th><th scope="col">État</th>
              <th scope="col">Ajoutée par</th><th scope="col">Actions</th>
            </tr>
          </thead>
          <tbody>
            {revision.documents.map((link) => (
              <tr key={link.id} className={link.replaced_by_id ? "muted" : undefined}>
                <td>
                  {link.document.original_name} <span className="small muted">v{link.document.version} · {link.document.type_label} · {formatBytes(link.document.bytes)}</span>
                  <div className="small muted code" title="Empreinte SHA-256">{link.document.sha256.slice(0, 16)}…</div>
                </td>
                <td>{link.usage_label}</td>
                <td>
                  {link.replaced_by_id ? "Remplacée (conservée)" : link.document.readability_label}
                  {link.document.inspection_notes.map((n) => (
                    <div key={n} className="small muted">{n}</div>
                  ))}
                </td>
                <td className="small">{link.added_by.email}</td>
                <td className="row">
                  <button type="button" onClick={() => void open(link)} disabled={!link.document.previewable}>Aperçu</button>
                  <button type="button" onClick={() => void download(link)}>Télécharger</button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
      {editable && (
        <form className="row" onSubmit={(e) => { e.preventDefault(); void send(); }}>
          <label>
            Fichier
            <input type="file" accept=".pdf,.png,.jpg,.jpeg,.xlsx" onChange={(e) => setFile(e.target.files?.[0] ?? null)} required />
          </label>
          <label>
            Usage
            <select value={usage} onChange={(e) => setUsage(e.target.value)}>
              {USAGES.map(([v, l]) => (
                <option key={v} value={v}>{l}</option>
              ))}
            </select>
          </label>
          <button type="submit">Ajouter la pièce</button>
        </form>
      )}
      {duplicate && (
        <div className="warning" role="alert">
          <p>Un fichier identique existe déjà dans votre société :</p>
          <ul className="small">
            {duplicate.map((d) => (
              <li key={d.id}>
                {d.original_name} {d.cases.length > 0 && `(dossiers ${d.cases.join(", ")})`}{" "}
                <button type="button" onClick={() => void reuse(d.id)}>Réutiliser cette pièce</button>
              </li>
            ))}
          </ul>
          <button type="button" onClick={() => void send("keep_both")}>Conserver les deux</button>{" "}
          <button type="button" onClick={() => setDuplicate(null)}>Annuler</button>
        </div>
      )}
      {message && <p role="status">{message}</p>}
      {error && <p role="alert" className="error">⚠ {error}</p>}
      {preview && <PreviewPanel preview={preview} onClose={() => setPreview(null)} />}
    </section>
  );
}

function PreviewPanel({ preview, onClose }: { preview: { doc: CaseDocument; data: Preview }; onClose: () => void }) {
  const { doc, data } = preview;
  return (
    <div className="evidence" aria-label={`Aperçu de ${doc.document.original_name}`}>
      <div className="row">
        <strong>{doc.document.original_name}</strong>
        <button type="button" onClick={onClose}>Fermer l'aperçu</button>
      </div>
      {data.kind === "pdf" && <iframe title={doc.document.original_name} src={data.url} className="preview" />}
      {data.kind === "image" && <img alt={doc.document.original_name} src={data.url} className="preview-image" />}
      {data.kind === "unavailable" && <p className="warning">{data.message}</p>}
      {data.kind === "sheet" && (
        <>
          <p className="muted small">{data.note}</p>
          {data.sheets.map((sheet) => (
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
        </>
      )}
    </div>
  );
}

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

function Invoices({ revision, editable, act }: { revision: Revision; editable: boolean; act: (a: () => Promise<unknown>) => Promise<void> }) {
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
      <h2 id="invoices-title">Factures et lignes saisies</h2>
      {revision.invoices.map((inv) => (
        <InvoiceBlock key={inv.id} invoice={inv} revision={revision} editable={editable} act={act} />
      ))}
      {editable && (
        <form className="row" onSubmit={add} aria-label="Ajouter une facture">
          <label>Fournisseur<input value={form.supplier_name} onChange={(e) => setForm({ ...form, supplier_name: e.target.value })} /></label>
          <label>N° facture<input value={form.invoice_number} onChange={(e) => setForm({ ...form, invoice_number: e.target.value })} /></label>
          <label>Date<input type="date" value={form.invoice_date} onChange={(e) => setForm({ ...form, invoice_date: e.target.value })} /></label>
          <label>Devise<input value={form.currency} maxLength={3} size={4} onChange={(e) => setForm({ ...form, currency: e.target.value })} placeholder="EUR" /></label>
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
          <button type="submit">Ajouter une facture</button>
        </form>
      )}
    </section>
  );
}

function InvoiceBlock({
  invoice,
  revision,
  editable,
  act,
}: {
  invoice: Invoice;
  revision: Revision;
  editable: boolean;
  act: (a: () => Promise<unknown>) => Promise<void>;
}) {
  const [line, setLine] = useState(EMPTY_LINE);
  const docs = revision.documents.filter((d) => !d.replaced_by_id);

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
      {invoice.lines.length > 0 && (
        <table className="small">
          <thead>
            <tr>
              <th scope="col">N°</th><th scope="col">Désignation</th><th scope="col">Réf. fournisseur</th>
              <th scope="col">Code douanier lu</th><th scope="col">Qté</th><th scope="col">PU</th>
              <th scope="col">Montant</th><th scope="col">Origine</th><th scope="col">Marchandise</th>
            </tr>
          </thead>
          <tbody>
            {invoice.lines.map((ln) => (
              <tr key={ln.id}>
                <td>{ln.ordinal}</td>
                <td>{ln.description_raw || <em className="muted">?</em>}<div className="muted">{ln.entry_origin_label}</div></td>
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
                <td>{ln.quantity ?? <em className="muted">inconnue</em>} {ln.unit}</td>
                <td>{ln.unit_price ?? "—"}</td>
                <td>{ln.amount ?? <em className="muted">inconnu</em>}</td>
                <td>{ln.origin_country || "—"}</td>
                <td>
                  {ln.goods_line_ids.length > 0 ? (
                    "rattachée"
                  ) : editable ? (
                    <button type="button" onClick={() => void act(() => api.addGoods(revision.id, [ln.id]))}>Préparer</button>
                  ) : (
                    "—"
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
      {editable && (
        <form className="row small" onSubmit={add} aria-label={`Ajouter une ligne à la facture ${invoice.ordinal}`}>
          <label>Désignation<input value={line.description_raw} onChange={(e) => setLine({ ...line, description_raw: e.target.value })} /></label>
          <label>Réf. article fournisseur<input value={line.source_reference} onChange={(e) => setLine({ ...line, source_reference: e.target.value })} /></label>
          <label>Code douanier lu<input className="code" value={line.customs_code} onChange={(e) => setLine({ ...line, customs_code: e.target.value })} placeholder="0101.10.00" /></label>
          <label>Intitulé du champ<input value={line.customs_code_label} onChange={(e) => setLine({ ...line, customs_code_label: e.target.value })} /></label>
          <label>Qté<input inputMode="decimal" size={6} value={line.quantity} onChange={(e) => setLine({ ...line, quantity: e.target.value })} /></label>
          <label>Unité<input size={5} value={line.unit} onChange={(e) => setLine({ ...line, unit: e.target.value })} /></label>
          <label>PU<input inputMode="decimal" size={8} value={line.unit_price} onChange={(e) => setLine({ ...line, unit_price: e.target.value })} /></label>
          <label>Montant<input inputMode="decimal" size={9} value={line.amount} onChange={(e) => setLine({ ...line, amount: e.target.value })} /></label>
          <label>Origine<input size={3} maxLength={2} value={line.origin_country} onChange={(e) => setLine({ ...line, origin_country: e.target.value })} placeholder="FR" /></label>
          <label>
            Pièce source
            <select value={line.evidence_document_id} onChange={(e) => setLine({ ...line, evidence_document_id: e.target.value })}>
              <option value="">—</option>
              {docs.map((d) => (
                <option key={d.id} value={d.id}>{d.document.original_name}</option>
              ))}
            </select>
          </label>
          <label>Page<input type="number" min={1} size={3} value={line.evidence_page} onChange={(e) => setLine({ ...line, evidence_page: e.target.value })} /></label>
          <button type="submit">Ajouter la ligne</button>
        </form>
      )}
    </div>
  );
}

function GoodsLines({
  revision,
  editions,
  editable,
  act,
}: {
  revision: Revision;
  editions: EditionOption[];
  editable: boolean;
  act: (a: () => Promise<unknown>) => Promise<void>;
}) {
  return (
    <section className="card" aria-labelledby="goods-title">
      <h2 id="goods-title">Marchandises et codes</h2>
      <p className="muted small">
        Un code retrouvé dans le référentiel n'est pas un classement validé : il attend votre confirmation motivée.
      </p>
      {revision.goods_lines.length === 0 && <p className="muted">Préparez une marchandise depuis une ligne facturée.</p>}
      {revision.goods_lines.map((g) => (
        <GoodsCard key={g.id} goods={g} revision={revision} editions={editions} editable={editable} act={act} />
      ))}
    </section>
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
  act: (a: () => Promise<unknown>) => Promise<void>;
}) {
  const [edition, setEdition] = useState(revision.target_edition?.id ?? editions[0]?.id ?? "");
  const [reason, setReason] = useState("");
  const [subdivision, setSubdivision] = useState("");
  const check: CodeCheck | null = goods.latest_check;
  const decision = goods.decision;
  const subdivisions = check?.findings.find((f) => f.code === "SUBDIVISIONS_REQUIRED")?.details?.subdivisions ?? [];

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
    <div className="subcard" aria-label={`Marchandise ${goods.ordinal}`}>
      <h3>Marchandise {goods.ordinal} · {goods.description || <em className="muted">désignation ?</em>}</h3>
      <p className="small muted">
        Issue de {goods.sources.map((s) => `facture ${s.invoice_ordinal} ligne ${s.line_ordinal}`).join(", ")} · origine{" "}
        {goods.origin_country || "?"}
      </p>
      {decision && (
        <p className={decision.is_current ? "decision" : "warning"}>
          {decision.is_current ? "✓" : "⚠"} {decision.action_label} : <span className="code">{decision.selected_code_display}</span>{" "}
          {decision.label} ({decision.edition.label}) par {decision.actor.email} le{" "}
          {new Date(decision.at).toLocaleString("fr-FR")}. Motif : {decision.reason}
          {!decision.is_current && " — Données modifiées depuis : décision à revoir."}
          <span className="small muted"> {decision.note}</span>
        </p>
      )}
      {editable && (
        <div className="row">
          <label>
            Contrôler contre
            <select value={edition} onChange={(e) => setEdition(e.target.value)}>
              {editions.map((e) => (
                <option key={e.id} value={e.id}>{e.label}</option>
              ))}
            </select>
          </label>
          <button type="button" disabled={!edition} onClick={() => void act(() => api.checkCode(goods.id, edition))}>
            Contrôler le code présent
          </button>
        </div>
      )}
      {check && (
        <div className="evidence" aria-label="Résultat du contrôle">
          <p>
            <strong>{check.recognition_label}</strong>
            {check.observed_code && (
              <>
                {" "}· lu <span className="code">{check.observed_code}</span> dans « {check.observed_field} » → normalisé{" "}
                <span className="code">{check.normalized_code ?? "—"}</span>
              </>
            )}{" "}
            · {check.target_edition_label} · {CONFIRMATION[check.human_confirmation]}
          </p>
          {check.node && (
            <p className="small">
              <span className="code">{check.node.code_display}</span> {check.node.full_path}
            </p>
          )}
          <ul className="small">
            {check.findings.map((f) => (
              <li key={f.code + f.message} className={f.severity === "info" ? "muted" : undefined}>
                {f.message}
              </li>
            ))}
          </ul>
          {editable && check.is_current && check.recognition_status === "recognized" && check.human_confirmation === "pending" && (
            <form className="row" onSubmit={(e) => { e.preventDefault(); decide("confirm"); }}>
              <label>
                Motif de la confirmation
                <input required value={reason} onChange={(e) => setReason(e.target.value)} size={40} />
              </label>
              <button type="submit">Confirmer le code</button>
            </form>
          )}
          {editable && check.is_current && check.recognition_status === "incomplete" && subdivisions.length > 0 && (
            <form className="row" onSubmit={(e) => { e.preventDefault(); decide("complete"); }}>
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
                <input required value={reason} onChange={(e) => setReason(e.target.value)} size={30} />
              </label>
              <button type="submit">Compléter le code</button>
            </form>
          )}
        </div>
      )}
    </div>
  );
}

function History({ caseId, version }: { caseId: string; version: number }) {
  const [events, setEvents] = useState<AuditEntry[]>([]);
  useEffect(() => {
    api.caseAudit(caseId).then((r) => setEvents(r.results), () => setEvents([]));
  }, [caseId, version]);
  return (
    <details className="card">
      <summary>Historique du dossier ({events.length})</summary>
      <ul className="small">
        {events.map((e) => (
          <li key={e.id}>
            {new Date(e.at).toLocaleString("fr-FR")} · {e.actor ?? "système"} · <span className="code">{e.event_type}</span>
          </li>
        ))}
      </ul>
    </details>
  );
}
