import { useEffect, useState } from "react";
import { ApiError, request } from "./api";
import { useI18n } from "./i18n";

interface Requirement {
  document_type: string;
  label: string;
  status: string;
  reasons: { kind: string; article?: string; source?: string }[];
  documents: { filename: string }[];
}
interface Checklist {
  coverage: string;
  regulatory_validation: boolean;
  requirements: Requirement[];
  warning: string;
  unclassified_documents: { filename: string; classification?: { suggested_type: string | null } }[];
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
      <h2 id="document-checklist-title">{t("checklistTitle")}</h2>
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
          : <table><thead><tr><th>{t("documents")}</th><th>{t("status")}</th><th>{t("basis")}</th></tr></thead>
            <tbody>{result.requirements.map((r) => <tr key={r.document_type}>
              <td>{r.label}</td><td>{r.status === "missing" ? t("missing") : t("receivedReview")}</td>
              <td>{r.reasons.map((v) => v.kind === "regulation"
                ? `${v.source || ""} art. ${v.article || ""}` : t("orgPolicy")).join(" · ")}</td>
            </tr>)}</tbody></table>}
        {result.unclassified_documents.length > 0 && <p className="muted">
          {result.unclassified_documents.length} {t("uncategorized")}
        </p>}
      </>}
    </section>
  );
}
