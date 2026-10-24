import { useEffect, useState, type FormEvent } from "react";
import { request } from "./api";
import { useI18n } from "./i18n";

type Type = { code: string; label_fr: string };
type Policy = {
  id: number; document_type: string; label: string; operation: string;
  regime: string; transport_mode: string; reason: string; active: boolean;
};

export function DocumentPolicies({ isAdmin }: { isAdmin: boolean }) {
  const { t } = useI18n();
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
    void load().catch(() => setError(t("policyUnavailable")));
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
      setMessage(t("policySaved"));
    } catch {
      setError(t("policyError"));
    }
  }

  return (
    <section className="card">
      <h2>{t("policyTitle")}</h2>
      <p className="muted">
        {t("policyInfo")}
      </p>
      {error && <p role="alert">{error}</p>}
      {message && <p role="status">{message}</p>}
      <table>
        <thead><tr><th>{t("documents")}</th><th>{t("operation")}</th><th>{t("transport")}</th><th>{t("reason")}</th></tr></thead>
        <tbody>{policies.map((p) => (
          <tr key={p.id}><td>{p.label}</td><td>{p.operation || t("allOperations")}</td>
            <td>{p.transport_mode || t("all")}</td><td>{p.reason || t("internalPolicy")}</td></tr>
        ))}</tbody>
      </table>
      {isAdmin && <form className="row" onSubmit={submit}>
        <label>Document
          <select required value={docType} onChange={(e) => setDocType(e.target.value)}>
            <option value="">{t("choose")}</option>
            {types.map((t) => <option key={t.code} value={t.code}>{t.label_fr}</option>)}
          </select>
        </label>
        <label>{t("operation")}
          <select value={operation} onChange={(e) => setOperation(e.target.value)}>
            <option value="import">{t("import")}</option><option value="export">{t("export")}</option>
          </select>
        </label>
        <label>{t("transport")}
          <select value={transport} onChange={(e) => setTransport(e.target.value)}>
            <option value="">{t("all")}</option><option value="sea">{t("sea")}</option>
            <option value="air">{t("air")}</option><option value="road">{t("road")}</option>
            <option value="rail">{t("rail")}</option><option value="multimodal">{t("multimodal")}</option>
          </select>
        </label>
        <label>{t("reasonLabel")}
          <input maxLength={300} value={reason} onChange={(e) => setReason(e.target.value)} />
        </label>
        <button type="submit">{t("policyAdd")}</button>
      </form>}
    </section>
  );
}
