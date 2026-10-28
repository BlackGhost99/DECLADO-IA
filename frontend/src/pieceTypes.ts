import type { CaseDocument, PieceType } from "./api";
import { currentLocale, tr, translations, type MessageKey } from "./i18n";

/** Lecture automatique selon le type de pièce ; reprend backend/apps/extraction/readers.py. */
const READER_FOR_TYPE: Record<string, string> = {
  commercial_invoice: "invoice",
  proforma_invoice: "invoice",
  bill_of_lading: "transport",
  sea_waybill: "transport",
  air_waybill: "transport",
  road_consignment_note: "transport",
  rail_consignment_note: "transport",
  insurance_invoice: "insurance",
  insurance_certificate: "insurance",
  insurance_policy: "insurance",
  freight_invoice: "freight",
  freight_receipt: "freight",
};
const READER_FOR_USAGE: Record<string, string> = { invoice: "invoice", transport: "transport", insurance: "insurance", freight: "freight" };

/** Lecture qui s'appliquera à la pièce, ou null si son type n'a pas de lecture automatique. */
export function readerOf(link: Pick<CaseDocument, "usage" | "document_type">): string | null {
  const type = link.document_type;
  if (type && READER_FOR_TYPE[type.code]) return READER_FOR_TYPE[type.code];
  if (type?.source === "confirmed") return null;
  return READER_FOR_USAGE[link.usage] ?? null;
}

function known(key: string): key is MessageKey {
  return key in translations.fr;
}

/** Nom d'un type de pièce dans la langue affichée ; libellé du catalogue pour un type non traduit ici. */
export function typeLabel(type: { code: string; label?: string; label_fr?: string; label_en?: string }): string {
  const key = `doctype.${type.code}`;
  if (known(key)) return tr(key);
  const fr = type.label ?? type.label_fr ?? type.code;
  return currentLocale() === "fr" ? fr : type.label_en ?? fr;
}

/** Libellé d'une information lue (B/L, assurance) ; libellé enregistré par le serveur sinon. */
export function fieldLabel(field: string, fallback: string): string {
  const key = `docField.${field}`;
  return known(key) ? tr(key) : fallback;
}

/** Raison enregistrée quand l'agent confirme un type reconnu. */
export function confirmReason(type: Pick<PieceType, "evidence">, fileName: string): string {
  const excerpt = type.evidence.excerpt;
  return type.evidence.method === "title" && excerpt ? tr("doc.reasonTitle", { title: excerpt }) : tr("doc.reasonFile", { name: fileName });
}
