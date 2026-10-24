import { useEffect, useState, type FormEvent } from "react";
import { request } from "./api";

type Type = { code: string; label_fr: string };
type Policy = {
  id: number; document_type: string; label: string; operation: string;
  regime: string; transport_mode: string; reason: string; active: boolean;
};

export function DocumentPolicies({ isAdmin }: { isAdmin: boolean }) {
  const [types, setTypes] = useState<Type[]>([]);
  const [policies, setPolicies] = useState<Policy[]>([]);
  const [docType, setDocType] = useState("");
  const [operation, setOperation] = useState("import");
  const [transport, setTransport] = useState("");
  const [reason, setReason] = useState("");
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");

  async function load() {
    const [catalogue, policyPage] = await Promise.all([
      request<{ results: Type[] }>("GET", "/document-types"),
      request<{ results: Policy[] }>("GET", "/organization/document-policies"),
    ]);
    setTypes(catalogue.results);
    setPolicies(policyPage.results);
  }

  useEffect(() => {
    void load().catch(() => setError("Référentiel documentaire indisponible."));
  }, []);

  async function submit(event: FormEvent) {
    event.preventDefault();
    setError("");
    setMessage("");
    try {
      await request("POST", "/organization/document-policies", {
        document_type: docType, operation, transport_mode: transport, reason,
      });
      await load();
      setMessage("Exigence supplémentaire enregistrée pour la société.");
    } catch {
      setError("Enregistrement refusé. Vérifiez vos droits et les paramètres.");
    }
  }

  return (
    <section className="card">
      <h2>Politique documentaire</h2>
      <p className="muted">
        Les exigences internes s'ajoutent aux obligations légales, sans pouvoir les supprimer.
        Les documents présents ne sont pas automatiquement validés par la Douane.
      </p>
      {error && <p role="alert">{error}</p>}
      {message && <p role="status">{message}</p>}
      <table>
        <thead><tr><th>Document</th><th>Opération</th><th>Transport</th><th>Raison</th></tr></thead>
        <tbody>{policies.map((p) => (
          <tr key={p.id}><td>{p.label}</td><td>{p.operation || "Toutes"}</td>
            <td>{p.transport_mode || "Tous"}</td><td>{p.reason || "Politique interne"}</td></tr>
        ))}</tbody>
      </table>
      {isAdmin && <form className="row" onSubmit={submit}>
        <label>Document
          <select required value={docType} onChange={(e) => setDocType(e.target.value)}>
            <option value="">Sélectionner</option>
            {types.map((t) => <option key={t.code} value={t.code}>{t.label_fr}</option>)}
          </select>
        </label>
        <label>Opération
          <select value={operation} onChange={(e) => setOperation(e.target.value)}>
            <option value="import">Importation</option><option value="export">Exportation</option>
          </select>
        </label>
        <label>Transport
          <select value={transport} onChange={(e) => setTransport(e.target.value)}>
            <option value="">Tous</option><option value="sea">Maritime</option>
            <option value="air">Aérien</option><option value="road">Routier</option>
            <option value="rail">Ferroviaire</option><option value="multimodal">Multimodal</option>
          </select>
        </label>
        <label>Motif
          <input maxLength={300} value={reason} onChange={(e) => setReason(e.target.value)} />
        </label>
        <button type="submit">Ajouter à la politique</button>
      </form>}
    </section>
  );
}
