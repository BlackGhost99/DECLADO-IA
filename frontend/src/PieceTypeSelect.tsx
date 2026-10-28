// Choix du type d'une pièce au dépôt : reconnu d'après le titre par défaut, ou type choisi par l'agent.
import { useEffect, useState } from "react";
import { api } from "./api";
import { tr, type MessageKey } from "./i18n";
import { typeLabel } from "./pieceTypes";

type CatalogType = { code: string; label_fr: string; label_en: string };

export const AUTO = "auto";

/** Usages proposés si le catalogue des types n'a pas pu être chargé. */
const FALLBACK_USAGES: [string, MessageKey][] = [
  ["invoice", "usage.invoice"],
  ["transport", "usage.transport"],
  ["insurance", "usage.insurance"],
  ["freight", "usage.freight"],
  ["packing_list", "usage.packing"],
  ["origin", "usage.origin"],
  ["other", "usage.other"],
];

/** Usage et type envoyés au serveur pour une valeur du menu. */
export function uploadChoice(value: string): { usage: string; documentType: string } {
  if (value.startsWith("type:")) return { usage: AUTO, documentType: value.slice(5) };
  if (value.startsWith("usage:")) return { usage: value.slice(6), documentType: "" };
  return { usage: AUTO, documentType: "" };
}

/** Catalogue des types, avec ceux que la société demande en premier. */
function useCatalog() {
  const [catalog, setCatalog] = useState<{ requested: CatalogType[]; others: CatalogType[] } | null>(null);
  useEffect(() => {
    let live = true;
    Promise.all([api.documentTypes(), api.documentPolicies().catch(() => ({ results: [] }))]).then(
      ([types, policies]) => {
        if (!live) return;
        const wanted = new Set(policies.results.filter((p) => p.active).map((p) => p.document_type));
        types.results.sort((a, b) => typeLabel(a).localeCompare(typeLabel(b)));
        setCatalog({
          requested: types.results.filter((t) => wanted.has(t.code)),
          others: types.results.filter((t) => !wanted.has(t.code)),
        });
      },
      () => live && setCatalog(null),
    );
    return () => {
      live = false;
    };
  }, []);
  return catalog;
}

export function PieceTypeSelect({ value, onChange, label }: { value: string; onChange: (value: string) => void; label?: string }) {
  const catalog = useCatalog();
  const option = (t: CatalogType) => (
    <option key={t.code} value={`type:${t.code}`}>{typeLabel(t)}</option>
  );
  return (
    <select value={value} onChange={(e) => onChange(e.target.value)} aria-label={label}>
      <option value={AUTO}>{tr("usage.auto")}</option>
      {catalog ? (
        <>
          {catalog.requested.length > 0 && <optgroup label={tr("upload.requested")}>{catalog.requested.map(option)}</optgroup>}
          <optgroup label={tr("upload.otherTypes")}>{catalog.others.map(option)}</optgroup>
        </>
      ) : (
        FALLBACK_USAGES.map(([v, l]) => (
          <option key={v} value={`usage:${v}`}>{tr(l)}</option>
        ))
      )}
    </select>
  );
}
