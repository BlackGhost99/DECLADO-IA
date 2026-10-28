import { useEffect, useState } from "react";
import { ApiError, request, type PieceType } from "./api";
import { tr, useI18n } from "./i18n";
import { confirmReason, typeLabel } from "./pieceTypes";

interface Requirement {
  document_type: string;
  label: string;
  status: string;
  reasons: { kind: string; article?: string; source?: string }[];
  documents: { filename: string; type_source?: PieceType["source"] }[];
}
/** Pièce sans type confirmé ; detected_type : type reconnu d'après son titre, à confirmer. */
interface Unclassified {
  case_document_id: string;
  filename: string;
  classification?: { suggested_type: string | null };
  detected_type?: string | null;
  type_evidence?: PieceType["evidence"] | null;
}
interface Checklist {
  coverage: string;
  regulatory_validation: boolean;
  requirements: Requirement[];
  warning: string;
  unclassified_documents: Unclassified[];
}

export function DocumentChecklist({ revisionId }: { revisionId: string }) {
  const { t } = useI18n();
  const [transport, setTransport] = useState("sea");
  const [operation, setOperation] = useState("import");
  const [result, setResult] = useState<Checklist | null>(null);
  const [error, setError] = useState("");
  useEffect(() => { setResult(null); }, [revisionId]);
  async function evaluate() {
    setError("");
    setResult(null);
    try {
      const params = new URLSearchParams({ operation, transport_mode: transport });
      const data = await request<Checklist>("GET", `/revisions/${revisionId}/document-checklist?${params}`);
      setResult(data);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : t("evaluationUnavailable"));
    }
  }
  return (
    <section className="card" aria-labelledby="document-checklist-title">
      <h2 id="document-checklist-title" className="card-title">{t("checklistTitle")}</h2>
      <p className="muted">{t("checklistNotice")}</p>
      <div className="row">
        <label>{t("operation")}
          <select value={operation} onChange={(e) => setOperation(e.target.value)}>
            <option value="import">{t("import")}</option><option value="export">{t("export")}</option>
          </select>
        </label>
        <label>{t("transport")}
          <select value={transport} onChange={(e) => setTransport(e.target.value)}>
            <option value="sea">{t("sea")}</option><option value="air">{t("air")}</option>
            <option value="road">{t("road")}</option><option value="rail">{t("rail")}</option>
            <option value="multimodal">{t("multimodal")}</option>
          </select>
        </label>
        <button type="button" onClick={() => void evaluate()}>{t("evaluate")}</button>
      </div>
      {error && <p role="alert" className="error">{error}</p>}
      {result && <>
        <p role="status" className="warning">{result.warning}</p>
        <p>{t("coverage")} {result.coverage} — {t("validationNo")}</p>
        {result.requirements.length === 0
          ? <p className="warning">{t("noRule")}</p>
          : <table className="data"><thead><tr><th>{t("documents")}</th><th>{t("status")}</th><th>{t("basis")}</th></tr></thead>
            <tbody>{result.requirements.map((r) => <tr key={r.document_type}>
              <td>{r.label}</td><td>
                {r.status === "missing" ? t("missing") : t("receivedReview")}
                {r.documents.some((d) => d.type_source === "detected") && <span className="muted small"> · {tr("chk.detected")}</span>}
              </td>
              <td>{r.reasons.map((v) => v.kind === "regulation"
                ? `${v.source || ""} art. ${v.article || ""}` : t("orgPolicy")).join(" · ")}</td>
            </tr>)}</tbody></table>}
        {result.unclassified_documents.length > 0 && <>
          <p className="muted">{result.unclassified_documents.length} {t("uncategorized")}</p>
          {result.unclassified_documents.map((doc) => (
            <ClassificationPicker
              key={doc.case_document_id} doc={doc} onConfirmed={() => void evaluate()}
            />
          ))}
        </>}
      </>}
    </section>
  );
}


function ClassificationPicker({
  doc, onConfirmed,
}: {
  doc: Unclassified;
  onConfirmed: () => void;
}) {
  const [types, setTypes] = useState<{ code: string; label_fr: string; label_en: string }[]>([]);
  const [choice, setChoice] = useState(doc.detected_type ?? doc.classification?.suggested_type ?? "");
  // Le type reconnu d'après le titre est proposé avec le texte qui le justifie ; l'agent confirme ou corrige.
  const [reason, setReason] = useState(doc.detected_type && doc.type_evidence ? confirmReason({ evidence: doc.type_evidence }, doc.filename) : "");
  const [error, setError] = useState("");

  useEffect(() => {
    void request<{ results: { code: string; label_fr: string; label_en: string }[] }>("GET", "/document-types")
      .then((page) => setTypes(page.results), () => setError(tr("chk.catalogUnavailable")));
  }, []);

  async function submit() {
    setError("");
    try {
      await request("POST", `/case-documents/${doc.case_document_id}/confirm-type`, {
        document_type: choice, reason,
      });
      onConfirmed();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : tr("chk.confirmFailed"));
    }
  }

  return <div className="row">
    <strong>{doc.filename}</strong>
    <label>{tr("chk.verifiedType")}
      <select value={choice} onChange={(e) => setChoice(e.target.value)}>
        <option value="">{tr("choose")}</option>
        {types.map((item) => <option key={item.code} value={item.code}>{typeLabel(item)}</option>)}
      </select>
    </label>
    <label>{tr("chk.justification")}
      <input value={reason} onChange={(e) => setReason(e.target.value)} maxLength={300} />
    </label>
    <button type="button" disabled={!choice || reason.trim().length < 3} onClick={() => void submit()}>
      {tr("chk.confirm")}
    </button>
    {error && <p role="alert" className="error">{error}</p>}
  </div>;
}
