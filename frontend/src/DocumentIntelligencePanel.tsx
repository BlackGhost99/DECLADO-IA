import { useCallback, useEffect, useState, type FormEvent } from "react";
import { api, type DocumentIntelligence, type GraphAssociation, type Revision } from "./api";
import { useI18n } from "./i18n";
import { errorText } from "./ui";

const LABELS = {
  fr: {
    title: "Intelligence documentaire", note: "Propositions vérifiables, sans décision automatique ni calcul douanier.",
    analyze: "Analyser les références", empty: "Aucune expédition proposée.",
    shipments: "Expéditions", links: "Documents associés aux factures", conflicts: "Contradictions",
    review: "À vérifier", confirmed: "Confirmé", rejected: "Rejeté", approve: "Confirmer",
    reject: "Refuser", add: "Ajouter", reference: "Référence de transport",
    invoice: "Facture", document: "Document", kind: "Nature du lien",
    associate: "Relier", reason: "Motif", resolve: "Résoudre", pending: "décisions en attente",
    intro: "Les relations sont proposées uniquement après extraction ; l'IA externe reste désactivée.",
  },
  en: {
    title: "Document intelligence", note: "Reviewable suggestions; no automatic decision or duty calculation.",
    analyze: "Analyze references", empty: "No proposed shipment.",
    shipments: "Shipments", links: "Documents linked to invoices", conflicts: "Conflicts",
    review: "Review", confirmed: "Confirmed", rejected: "Rejected", approve: "Confirm",
    reject: "Reject", add: "Add", reference: "Transport reference",
    invoice: "Invoice", document: "Document", kind: "Link type",
    associate: "Link", reason: "Reason", resolve: "Resolve", pending: "pending decisions",
    intro: "Links are suggested after extraction; external AI remains disabled.",
  },
  es: {
    title: "Inteligencia documental", note: "Sugerencias revisables sin decisiones automáticas ni cálculos aduaneros.",
    analyze: "Analizar referencias", empty: "No hay expediciones propuestas.",
    shipments: "Expediciones", links: "Documentos vinculados a facturas", conflicts: "Conflictos",
    review: "Revisar", confirmed: "Confirmado", rejected: "Rechazado", approve: "Confirmar",
    reject: "Rechazar", add: "Añadir", reference: "Referencia de transporte",
    invoice: "Factura", document: "Documento", kind: "Tipo de vínculo",
    associate: "Vincular", reason: "Motivo", resolve: "Resolver", pending: "decisiones pendientes",
    intro: "Se sugieren vínculos tras la extracción; la IA externa sigue desactivada.",
  },
  ar: {
    title: "الذكاء الوثائقي", note: "اقتراحات قابلة للمراجعة دون قرارات آلية أو حساب الرسوم.",
    analyze: "تحليل المراجع", empty: "لا توجد شحنات مقترحة.",
    shipments: "الشحنات", links: "المستندات المرتبطة بالفواتير", conflicts: "التعارضات",
    review: "للمراجعة", confirmed: "مؤكد", rejected: "مرفوض", approve: "تأكيد",
    reject: "رفض", add: "إضافة", reference: "مرجع النقل",
    invoice: "فاتورة", document: "مستند", kind: "نوع الرابط",
    associate: "ربط", reason: "السبب", resolve: "حل", pending: "قرارات معلقة",
    intro: "تُقترح الروابط بعد الاستخراج؛ الذكاء الاصطناعي الخارجي معطل.",
  },
};

const KINDS = ["invoice_reference", "packing", "insurance", "freight", "transport", "other"];

export function DocumentIntelligencePanel({ revision, editable }: { revision: Revision; editable: boolean }) {
  const { locale } = useI18n();
  const t = LABELS[locale];
  const [data, setData] = useState<DocumentIntelligence | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [documentId, setDocumentId] = useState("");
  const [invoiceId, setInvoiceId] = useState("");
  const [kind, setKind] = useState("invoice_reference");
  const [shipmentRef, setShipmentRef] = useState("");
  const [resolution, setResolution] = useState<Record<string, string>>({});

  const refresh = useCallback(async () => {
    setData(await api.documentIntelligence(revision.id));
  }, [revision.id]);

  useEffect(() => {
    void refresh().catch((err) => setError(errorText(err, t.title)));
  }, [refresh, t.title]);

  async function run(action: () => Promise<unknown>) {
    setBusy(true);
    setError("");
    try {
      await action();
      await refresh();
    } catch (err) {
      setError(errorText(err, t.title));
    } finally {
      setBusy(false);
    }
  }

  const documents = revision.documents.filter((doc) => !doc.replaced_by_id);
  const docLabel = (id?: string) =>
    documents.find((doc) => doc.id === id)?.document.original_name ?? id?.slice(0, 8) ?? "?";
  const invLabel = (id?: string) => {
    const invoice = revision.invoices.find((item) => item.id === id);
    return invoice ? invoice.invoice_number || String(invoice.ordinal) : id?.slice(0, 8) ?? "?";
  };

  function decision(link: GraphAssociation, model: string) {
    if (link.status !== "proposed") {
      return <span className="muted small">{link.status === "confirmed" ? t.confirmed : t.rejected}</span>;
    }
    if (!editable) return <span className="muted small">{t.review}</span>;
    return <span className="row">
      <button type="button" disabled={busy} onClick={() => void run(() => api.reviewGraphLink(model, link.id, "confirmed"))}>
        {t.approve}
      </button>
      <button type="button" disabled={busy} onClick={() => void run(() => api.reviewGraphLink(model, link.id, "rejected"))}>
        {t.reject}
      </button>
    </span>;
  }

  function association(link: GraphAssociation, model: string, label: string) {
    return <li key={link.id}>
      <span dir="auto">{label}</span>{" "}
      <span dir="ltr" className="muted small">
        {link.evidence.map((item) => item.value).filter(Boolean).join(", ")}
      </span>{" "}{decision(link, model)}
    </li>;
  }

  function addInvoiceLink(event: FormEvent) {
    event.preventDefault();
    if (documentId && invoiceId) {
      void run(() => api.addDocumentInvoiceLink(revision.id, documentId, invoiceId, kind));
    }
  }

  return <section className="card" aria-labelledby="doc-intelligence-title">
    <h2 id="doc-intelligence-title" className="card-title">{t.title}</h2>
    <p className="muted small">{t.note} {t.intro}</p>
    {error && <p role="alert" className="error">{error}</p>}
    <p className="row">
      {editable && <button type="button" disabled={busy}
        onClick={() => void run(() => api.analyzeDocuments(revision.id))}>{t.analyze}</button>}
      {data && <span className="muted small">{data.pending_count} {t.pending}</span>}
    </p>

    <h3>{t.shipments}</h3>
    {!data?.shipments.length && <p className="muted">{t.empty}</p>}
    {data?.shipments.map((shipment) => <div key={shipment.id}>
      <p><strong dir="ltr">{shipment.reference}</strong> · {shipment.status === "confirmed" ? t.confirmed : t.review}
        {editable && shipment.status === "proposed" && <button type="button" disabled={busy}
          onClick={() => void run(() => api.confirmGraphShipment(shipment.id))}>{t.approve}</button>}
      </p>
      <ul className="small">
        {shipment.documents.map((link) => association(link, "shipment_document",
          t.document + ": " + docLabel(link.document_id)))}
        {shipment.invoices.map((link) => association(link, "shipment_invoice",
          t.invoice + ": " + invLabel(link.invoice_id)))}
      </ul>
      {editable && <div className="row">
        <button type="button" disabled={busy || !documentId}
          onClick={() => void run(() => api.addShipmentAssociation(revision.id, shipment.id, "document", documentId))}>
          {t.associate} {t.document}
        </button>
        <button type="button" disabled={busy || !invoiceId}
          onClick={() => void run(() => api.addShipmentAssociation(revision.id, shipment.id, "invoice", invoiceId))}>
          {t.associate} {t.invoice}
        </button>
      </div>}
    </div>)}
    {editable && <form className="row" onSubmit={(event) => {
      event.preventDefault();
      void run(async () => {
        await api.addShipment(revision.id, shipmentRef);
        setShipmentRef("");
      });
    }}>
      <label>{t.reference}
        <input required dir="ltr" value={shipmentRef} onChange={(event) => setShipmentRef(event.target.value)} />
      </label>
      <button type="submit" disabled={busy}>{t.add}</button>
    </form>}

    <h3>{t.links}</h3>
    <ul className="small">
      {data?.document_invoices.map((link) => association(link, "document_invoice",
        docLabel(link.document_id) + " → " + invLabel(link.invoice_id)))}
    </ul>
    {editable && <form onSubmit={addInvoiceLink} className="row">
      <label>{t.document}<select required value={documentId} onChange={(event) => setDocumentId(event.target.value)}>
        <option value="">—</option>
        {documents.map((doc) => <option key={doc.id} value={doc.id}>{doc.document.original_name}</option>)}
      </select></label>
      <label>{t.invoice}<select required value={invoiceId} onChange={(event) => setInvoiceId(event.target.value)}>
        <option value="">—</option>
        {revision.invoices.map((invoice) =>
          <option key={invoice.id} value={invoice.id}>{invoice.invoice_number || invoice.ordinal}</option>)}
      </select></label>
      <label>{t.kind}<select value={kind} onChange={(event) => setKind(event.target.value)}>
        {KINDS.map((value) => <option key={value} value={value}>{value}</option>)}
      </select></label>
      <button type="submit" disabled={busy}>{t.associate}</button>
    </form>}
    <h3>{t.conflicts}</h3>
    {data?.conflicts.map((conflict) => <div key={conflict.id}>
      <p>{conflict.kind} : {invLabel(conflict.invoice_id ?? undefined)}{" "}
        <span dir="ltr">{conflict.detail.current} / {conflict.detail.observed}</span>{" "}
        ({conflict.status === "open" ? t.review : t.confirmed})
      </p>
      {editable && conflict.status === "open" && <form className="row" onSubmit={(event) => {
        event.preventDefault();
        void run(() => api.resolveGraphConflict(conflict.id, resolution[conflict.id] ?? ""));
      }}>
        <label>{t.reason}<input required value={resolution[conflict.id] ?? ""}
          onChange={(event) => setResolution({ ...resolution, [conflict.id]: event.target.value })} /></label>
        <button disabled={busy} type="submit">{t.resolve}</button>
      </form>}
    </div>)}
  </section>;
}
