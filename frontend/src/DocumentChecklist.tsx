import { useEffect, useState } from "react";
import { ApiError, request } from "./api";

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
      setError(err instanceof ApiError ? err.message : "Évaluation documentaire indisponible.");
    }
  }
  return (
    <section className="card" aria-labelledby="document-checklist-title">
      <h2 id="document-checklist-title">Contrôle documentaire réglementaire</h2>
      <p className="muted">Évaluation indicative : la présence d'une pièce ne vaut pas conformité réglementaire.</p>
      <div className="row">
        <label>Opération
          <select value={operation} onChange={(e) => setOperation(e.target.value)}>
            <option value="import">Importation</option><option value="export">Exportation</option>
          </select>
        </label>
        <label>Transport
          <select value={transport} onChange={(e) => setTransport(e.target.value)}>
            <option value="sea">Maritime</option><option value="air">Aérien</option>
            <option value="road">Routier</option><option value="rail">Ferroviaire</option>
            <option value="multimodal">Multimodal</option>
          </select>
        </label>
        <button type="button" onClick={() => void evaluate()}>Évaluer les pièces</button>
      </div>
      {error && <p role="alert" className="error">{error}</p>}
      {result && <>
        <p role="status" className="warning">{result.warning}</p>
        <p>Couverture : {result.coverage} — Validation réglementaire : non</p>
        {result.requirements.length === 0
          ? <p className="warning">Aucune règle publiée ne permet de conclure que ce dossier est complet.</p>
          : <table><thead><tr><th>Document</th><th>État</th><th>Fondement</th></tr></thead>
            <tbody>{result.requirements.map((r) => <tr key={r.document_type}>
              <td>{r.label}</td><td>{r.status === "missing" ? "Manquant" : "Reçu, à vérifier"}</td>
              <td>{r.reasons.map((v) => v.kind === "regulation"
                ? `${v.source || ""} art. ${v.article || ""}` : "Politique société").join(" · ")}</td>
            </tr>)}</tbody></table>}
        {result.unclassified_documents.length > 0 && <p className="muted">
          {result.unclassified_documents.length} document(s) non classés avec certitude.
          Les suggestions tirées du nom des fichiers doivent être confirmées par un agent.
        </p>}
      </>}
    </section>
  );
}
