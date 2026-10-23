// Contrôles du dossier : tout ce que le serveur signale déjà (manques, divergences, totaux, codes),
// réuni en une liste. Rien n'est inventé ici : chaque ligne vient d'une donnée de la révision.
import { useState } from "react";
import type { CaseDetail } from "./api";
import { FIELD_LABELS } from "./Extraction";
import { Icon, type IconName } from "./Icon";
import { Chip, goodsStatus, StatCard, type Tone } from "./ui";

export type Severity = "blocking" | "review" | "ok" | "info";

export interface ControlItem {
  id: string;
  category: string;
  icon: IconName;
  title: string;
  description: string;
  severity: Severity;
  action: string;
  tab: string;
}

const SEVERITY: Record<Severity, { label: string; tone: Tone }> = {
  blocking: { label: "Bloquant", tone: "red" },
  review: { label: "À vérifier", tone: "amber" },
  ok: { label: "Conforme", tone: "green" },
  info: { label: "Information", tone: "blue" },
};

const SCOPE_TABS: Record<string, string> = {
  case: "apercu",
  revision: "apercu",
  document: "documents",
  goods_line: "marchandises",
};

export function controlItems(detail: CaseDetail): ControlItem[] {
  const rev = detail.revision;
  const items: ControlItem[] = [];

  // Les divergences sont détaillées plus bas, facture par facture.
  for (const b of rev.completeness.blocking.filter((x) => x.scope !== "divergence")) {
    items.push({
      id: `missing-${b.id}-${b.field}`,
      category: "Informations manquantes",
      icon: "file",
      title: b.message,
      description: `${b.label} : ${b.message} Tant que ce point reste ouvert, le dossier ne peut être ni calculé ni validé.`,
      severity: "blocking",
      action: "Compléter l'information dans le dossier.",
      tab: SCOPE_TABS[b.scope] ?? "donnees",
    });
  }
  for (const w of rev.completeness.warnings) {
    items.push({
      id: `warn-${w.id}-${w.field}-${w.message}`,
      category: "À examiner",
      icon: "alert",
      title: w.message,
      description: `${w.label} : ${w.message}`,
      severity: "review",
      action: "Vérifier la valeur et sa pièce justificative.",
      tab: "donnees",
    });
  }

  for (const inv of rev.invoices) {
    const name = `Facture ${inv.ordinal}${inv.invoice_number ? ` (${inv.invoice_number})` : ""}`;
    for (const d of (inv.divergences ?? []).filter((x) => x.state === "open")) {
      const field = FIELD_LABELS[d.field] ?? d.field;
      items.push({
        id: `div-${d.id}`,
        category: "Contradiction de lecture",
        icon: "alert",
        title: d.line_ordinal ? `Ligne ${d.line_ordinal}, ${field} : la relecture diffère` : `${name}, ${field} : la relecture diffère`,
        description:
          d.kind === "line_not_reread"
            ? `${name} : une ligne n'apparaît plus dans la nouvelle lecture. Elle est conservée.`
            : `${name} : valeur actuelle « ${String(d.current_value ?? "—")} », relecture « ${String(d.extracted_value ?? "—")} ».`,
        severity: "blocking",
        action: "Garder la valeur actuelle ou retenir la relecture, avec un motif.",
        tab: "donnees",
      });
    }
    const t = inv.totals_check;
    if (t && t.goods_lines > 0) {
      if (t.status === "gap") {
        items.push({
          id: `tot-${inv.id}`,
          category: "Écart de montants",
          icon: "calculator",
          title: `${name} : total imprimé ${t.printed_total ?? "?"}, total recalculé ${t.computed_total ?? "?"}`,
          description: `Écart de ${t.gap} ${inv.currency}. ${t.explanations.join(" ")} Rien n'a été corrigé automatiquement.`,
          severity: "review",
          action: "Retrouver la ligne, le frais ou la remise qui explique l'écart.",
          tab: "donnees",
        });
      } else if (t.status === "match") {
        items.push({
          id: `tot-${inv.id}`,
          category: "Montants",
          icon: "calculator",
          title: `${name} : total recalculé égal au total imprimé`,
          description: `Somme des lignes, frais, remises et taxes = ${t.printed_total} ${inv.currency}.`,
          severity: "ok",
          action: "Aucune action.",
          tab: "donnees",
        });
      } else {
        items.push({
          id: `tot-${inv.id}`,
          category: "Montants",
          icon: "calculator",
          title: `${name} : total non recalculable`,
          description: t.status === "incomplete" ? "Une ou plusieurs valeurs sont inconnues." : "Aucun total imprimé n'a été lu.",
          severity: "info",
          action: "Compléter les montants inconnus si nécessaire.",
          tab: "donnees",
        });
      }
    }
    const flagged = [...(inv.review_flags ?? []), ...inv.lines.flatMap((ln) => ln.review_flags ?? [])];
    if (flagged.length > 0) {
      items.push({
        id: `flags-${inv.id}`,
        category: "Lecture à vérifier",
        icon: "eye",
        title: `${name} : ${flagged.length} valeur(s) lue(s) avec un doute`,
        description: flagged.slice(0, 4).map((f) => f.message).join(" "),
        severity: "review",
        action: "Comparer chaque valeur à la pièce, puis la corriger si besoin.",
        tab: "donnees",
      });
    }
  }

  for (const g of rev.goods_lines) {
    const s = goodsStatus(g);
    items.push({
      id: `goods-${g.id}`,
      category: s.label === "Validé" ? "Classification" : "Code à traiter",
      icon: "box",
      title: `Marchandise ${g.ordinal}${g.description ? ` (${g.description})` : ""} : ${s.label.toLowerCase()}${s.code ? ` ${s.code}` : ""}`,
      description:
        s.label === "Validé"
          ? `Code ${s.code} confirmé par ${g.decision?.actor.email}, avec motif.`
          : "Le code doit être contrôlé contre le tarif puis confirmé avec un motif.",
      severity: s.label === "Validé" ? "ok" : "review",
      action: s.label === "Validé" ? "Aucune action." : "Ouvrir la marchandise et confirmer ou choisir le code.",
      tab: "marchandises",
    });
  }

  if (rev.target_edition?.warning) {
    items.push({
      id: "edition",
      category: "Tarif",
      icon: "book",
      title: `Tarif utilisé : ${rev.target_edition.label}`,
      description: rev.target_edition.warning,
      severity: "info",
      action: "Aucun calcul opérationnel tant que le tarif n'est pas vérifié.",
      tab: "apercu",
    });
  }
  const order: Severity[] = ["blocking", "review", "ok", "info"];
  return items.sort((a, b) => order.indexOf(a.severity) - order.indexOf(b.severity));
}

export function Controls({ detail, go }: { detail: CaseDetail; go: (tab: string) => void }) {
  const items = controlItems(detail);
  const [selectedId, setSelectedId] = useState<string | null>(items[0]?.id ?? null);
  const selected = items.find((i) => i.id === selectedId) ?? items[0] ?? null;
  const count = (s: Severity) => items.filter((i) => i.severity === s).length;
  const index = selected ? items.indexOf(selected) : -1;

  return (
    <>
      <div className="stats stats-4">
        <StatCard icon="alert" tone="red" label="Bloquants" value={count("blocking")} />
        <StatCard icon="alert" tone="amber" label="À vérifier" value={count("review")} />
        <StatCard icon="checkCircle" tone="green" label="Conformes" value={count("ok")} />
        <StatCard icon="info" tone="blue" label="Informations" value={count("info")} />
      </div>
      <div className="split-panel">
        <section className="card" aria-labelledby="controls-title">
          <h2 id="controls-title" className="card-title">Liste des contrôles ({items.length})</h2>
          {items.length === 0 ? (
            <p className="empty">Aucun contrôle pour l'instant : ajoutez et lisez une facture.</p>
          ) : (
            <div className="table-wrap">
              <table className="data selectable">
                <thead>
                  <tr><th scope="col">Catégorie</th><th scope="col">Contrôle</th><th scope="col">Sévérité</th><th scope="col">Statut</th></tr>
                </thead>
                <tbody>
                  {items.map((i) => (
                    <tr key={i.id} className={selected?.id === i.id ? "selected" : undefined} onClick={() => setSelectedId(i.id)}>
                      <td>
                        <span className={`cat cat-${SEVERITY[i.severity].tone}`}><Icon name={i.icon} size={16} /></span> {i.category}
                      </td>
                      <td>
                        <button type="button" className="row-button" onClick={() => setSelectedId(i.id)}>{i.title}</button>
                      </td>
                      <td><Chip tone={SEVERITY[i.severity].tone}>{SEVERITY[i.severity].label}</Chip></td>
                      <td>
                        {i.severity === "ok" ? <Chip tone="green">Résolu</Chip> : i.severity === "info" ? <Chip tone="gray">Information</Chip> : <Chip tone="red">Non résolu</Chip>}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </section>
        <section className="card side-panel" aria-label="Détail du contrôle">
          <div className="card-head">
            <h2 className="card-title">Détail du contrôle</h2>
            {items.length > 0 && (
              <span className="pager">
                <button type="button" className="icon-button" disabled={index <= 0} onClick={() => setSelectedId(items[index - 1].id)} aria-label="Contrôle précédent">
                  <Icon name="arrowLeft" size={16} />
                </button>
                {index + 1} sur {items.length}
                <button type="button" className="icon-button" disabled={index >= items.length - 1} onClick={() => setSelectedId(items[index + 1].id)} aria-label="Contrôle suivant">
                  <Icon name="arrowRight" size={16} />
                </button>
              </span>
            )}
          </div>
          {selected ? (
            <>
              <div className={`control-banner banner-${SEVERITY[selected.severity].tone}`}>
                <Icon name={selected.icon} size={22} />
                <div>
                  <strong>{selected.category}</strong>
                  <span>{selected.title}</span>
                </div>
                <Chip tone={SEVERITY[selected.severity].tone}>{SEVERITY[selected.severity].label}</Chip>
              </div>
              <h3>Description</h3>
              <p>{selected.description}</p>
              <h3>Action recommandée</h3>
              <p className="note-blue">{selected.action}</p>
              <button type="button" className="btn-primary btn-block" onClick={() => go(selected.tab)}>
                Ouvrir la section concernée <Icon name="arrowRight" />
              </button>
            </>
          ) : (
            <p className="empty">Aucun contrôle sélectionné.</p>
          )}
        </section>
      </div>
    </>
  );
}
