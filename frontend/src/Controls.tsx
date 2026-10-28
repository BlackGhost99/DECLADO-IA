// Contrôles du dossier : tout ce que le serveur signale déjà (manques, divergences, totaux, codes),
// réuni en une liste. Rien n'est inventé ici : chaque ligne vient d'une donnée de la révision.
import { useState } from "react";
import type { CaseDetail } from "./api";
import { fieldLabel } from "./Extraction";
import { tr, type MessageKey } from "./i18n";
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
  /** Conséquence pour la suite du dossier. */
  impact?: string;
  /** Pièces concernées, avec leur état. */
  documents?: { label: string; state: "present" | "missing" }[];
  /** Étapes concrètes pour résoudre le point. */
  steps?: string[];
}

const IMPACT: Record<Severity, MessageKey> = {
  blocking: "ctl.impactBlocking",
  review: "ctl.impactReview",
  ok: "ctl.impactOk",
  info: "ctl.impactInfo",
};

const SEVERITY: Record<Severity, { label: MessageKey; tone: Tone }> = {
  blocking: { label: "ctl.blocking", tone: "red" },
  review: { label: "ctl.review", tone: "amber" },
  ok: { label: "ctl.ok", tone: "green" },
  info: { label: "ctl.info", tone: "blue" },
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
  const docs = rev.documents.filter((d) => !d.replaced_by_id);
  const invoiceDocs = docs.filter((d) => d.usage === "invoice");

  if (invoiceDocs.length === 0) {
    items.push({
      id: "doc-invoice",
      category: tr("ctl.catMissingDocs"),
      icon: "file",
      title: tr("ctl.invoiceMissing"),
      description: tr("ctl.invoiceMissingText"),
      severity: "blocking",
      action: tr("ctl.addInvoice"),
      tab: "documents",
      documents: [{ label: tr("ctl.commercialInvoice"), state: "missing" }],
      steps: [tr("ctl.invoiceStep1"), tr("ctl.invoiceStep2"), tr("ctl.invoiceStep3")],
    });
  }
  for (const [usage, key] of [["transport", "ctl.docTransport"], ["packing_list", "ctl.docPacking"], ["origin", "ctl.docOrigin"]] as const) {
    if (!docs.some((d) => d.usage === usage)) {
      const label = tr(key);
      items.push({
        id: `doc-${usage}`,
        category: tr("ctl.catMissingDocs"),
        icon: "file",
        title: tr("ctl.docAbsent", { label }),
        description: tr("ctl.docAbsentText", { label }),
        severity: "info",
        action: tr("ctl.addIfAny"),
        tab: "documents",
        documents: [{ label, state: "missing" }],
      });
    }
  }

  // Les divergences sont détaillées plus bas, facture par facture.
  for (const b of rev.completeness.blocking.filter((x) => x.scope !== "divergence")) {
    items.push({
      id: `missing-${b.id}-${b.field}`,
      category: tr("ctl.catMissingInfo"),
      icon: "file",
      title: b.message,
      description: tr("ctl.missingText", { label: b.label, message: b.message }),
      severity: "blocking",
      action: tr("ctl.completeInfo"),
      tab: SCOPE_TABS[b.scope] ?? "donnees",
      steps: [tr("ctl.openSection"), tr("ctl.fillFrom", { label: b.label }), tr("ctl.saveGone")],
    });
  }
  for (const w of rev.completeness.warnings) {
    items.push({
      id: `warn-${w.id}-${w.field}-${w.message}`,
      category: tr("ctl.catReview"),
      icon: "alert",
      title: w.message,
      description: tr("ctl.labelMessage", { label: w.label, message: w.message }),
      severity: "review",
      action: tr("ctl.checkValue"),
      tab: "donnees",
    });
  }

  for (const inv of rev.invoices) {
    const name = `${tr("ctl.invoiceName", { n: inv.ordinal })}${inv.invoice_number ? ` (${inv.invoice_number})` : ""}`;
    for (const d of (inv.divergences ?? []).filter((x) => x.state === "open")) {
      const field = fieldLabel(d.field);
      items.push({
        id: `div-${d.id}`,
        category: tr("ctl.catContradictions"),
        icon: "alert",
        title: d.line_ordinal ? tr("ctl.lineDiffers", { line: d.line_ordinal, field }) : tr("ctl.invoiceDiffers", { name, field }),
        description:
          d.kind === "line_not_reread"
            ? tr("ctl.lineGone", { name })
            : tr("ctl.valuesDiffer", { name, current: String(d.current_value ?? "—"), reread: String(d.extracted_value ?? "—") }),
        severity: "blocking",
        action: tr("ctl.keepOrTake"),
        tab: "donnees",
        documents: invoiceDocs.filter((d) => d.id === inv.document_id).map((d) => ({ label: d.document.original_name, state: "present" as const })),
        steps: [tr("ctl.divStep1"), tr("ctl.divStep2"), tr("ctl.divStep3")],
      });
    }
    const t = inv.totals_check;
    if (t && t.goods_lines > 0) {
      if (t.status === "gap") {
        items.push({
          id: `tot-${inv.id}`,
          category: tr("ctl.catGap"),
          icon: "dollar",
          title: tr("ctl.gapTitle", { name, printed: t.printed_total ?? "?", computed: t.computed_total ?? "?" }),
          description: tr("ctl.gapText", { gap: t.gap ?? "?", currency: inv.currency, explanations: t.explanations.join(" ") }),
          severity: "review",
          action: tr("ctl.findGap"),
          tab: "donnees",
          documents: invoiceDocs.filter((d) => d.id === inv.document_id).map((d) => ({ label: d.document.original_name, state: "present" as const })),
          steps: [tr("ctl.gapStep1"), tr("ctl.gapStep2"), tr("ctl.gapStep3")],
        });
      } else if (t.status === "match") {
        items.push({
          id: `tot-${inv.id}`,
          category: tr("ctl.catAmounts"),
          icon: "calculator",
          title: tr("ctl.matchTitle", { name }),
          description: tr("ctl.matchText", { total: t.printed_total ?? "?", currency: inv.currency }),
          severity: "ok",
          action: tr("ctl.noAction"),
          tab: "donnees",
        });
      } else {
        items.push({
          id: `tot-${inv.id}`,
          category: tr("ctl.catAmounts"),
          icon: "calculator",
          title: tr("ctl.notComputable", { name }),
          description: t.status === "incomplete" ? tr("ctl.someUnknown") : tr("ctl.noPrinted"),
          severity: "info",
          action: tr("ctl.completeUnknown"),
          tab: "donnees",
        });
      }
    }
    const flagged = [...(inv.review_flags ?? []), ...inv.lines.flatMap((ln) => ln.review_flags ?? [])];
    if (flagged.length > 0) {
      items.push({
        id: `flags-${inv.id}`,
        category: tr("ctl.catReading"),
        icon: "eye",
        title: tr("ctl.doubtful", { name, count: flagged.length }),
        description: flagged.slice(0, 4).map((f) => f.message).join(" "),
        severity: "review",
        action: tr("ctl.compareFix"),
        tab: "donnees",
      });
    }
  }

  for (const g of rev.goods_lines) {
    const s = goodsStatus(g);
    // Comparé à la décision, jamais au libellé : celui-ci change avec la langue.
    const done = Boolean(g.decision?.is_current);
    items.push({
      id: `goods-${g.id}`,
      category: done ? tr("ctl.catClassification") : tr("ctl.catCodes"),
      icon: "tag",
      title: tr("ctl.goodsTitle", { n: g.ordinal, desc: g.description ? ` (${g.description})` : "", status: s.label.toLowerCase(), code: s.code ? ` ${s.code}` : "" }),
      description: done ? tr("ctl.codeConfirmed", { code: s.code, who: g.decision?.actor.email ?? "" }) : tr("ctl.codeToCheck"),
      severity: done ? "ok" : "review",
      action: done ? tr("ctl.noAction") : tr("ctl.openGoods"),
      tab: "marchandises",
      steps: done ? undefined : [tr("ctl.goodsStep1"), tr("ctl.goodsStep2"), tr("ctl.goodsStep3")],
    });
  }

  if (rev.target_edition?.warning) {
    items.push({
      id: "edition",
      category: tr("ctl.catTariff"),
      icon: "book",
      title: tr("ctl.tariffUsed", { label: rev.target_edition.label }),
      description: rev.target_edition.warning,
      severity: "info",
      action: tr("ctl.noOperational"),
      tab: "apercu",
    });
  }
  const order: Severity[] = ["blocking", "review", "ok", "info"];
  return items.sort((a, b) => order.indexOf(a.severity) - order.indexOf(b.severity));
}

export function Controls({ detail, go }: { detail: CaseDetail; go: (tab: string) => void }) {
  const items = controlItems(detail);
  const [selectedId, setSelectedId] = useState<string | null>(items[0]?.id ?? null);
  const [search, setSearch] = useState("");
  const [severity, setSeverity] = useState<Severity | "">("");
  const shown = items.filter(
    (i) => (!severity || i.severity === severity) && (!search.trim() || `${i.category} ${i.title}`.toLowerCase().includes(search.trim().toLowerCase())),
  );
  const selected = shown.find((i) => i.id === selectedId) ?? shown[0] ?? null;
  const count = (s: Severity) => items.filter((i) => i.severity === s).length;
  const index = selected ? shown.indexOf(selected) : -1;

  return (
    <>
      <div className="stats stats-4">
        <StatCard icon="alert" tone="red" label={tr("ctl.statBlocking")} value={count("blocking")} hint={tr("ctl.statBlockingHint")} />
        <StatCard icon="alert" tone="amber" label={tr("ctl.review")} value={count("review")} hint={tr("ctl.statReviewHint")} />
        <StatCard icon="checkCircle" tone="green" label={tr("ctl.statOk")} value={count("ok")} hint={tr("ctl.statOkHint")} />
        <StatCard icon="info" tone="blue" label={tr("ctl.statInfo")} value={count("info")} hint={tr("ctl.statInfoHint")} />
      </div>
      <div className="split-panel">
        <section className="card" aria-labelledby="controls-title">
          <div className="card-head">
            <h2 id="controls-title" className="card-title">{tr("ctl.list", { count: items.length })}</h2>
            <div className="table-tools">
              <label className="search-mini">
                <Icon name="search" size={16} />
                <input aria-label={tr("ctl.search")} placeholder={`${tr("ctl.search")}…`} value={search} onChange={(e) => setSearch(e.target.value)} />
              </label>
              <label className="filter-mini">
                <Icon name="filter" size={16} />
                <select aria-label={tr("ctl.filter")} value={severity} onChange={(e) => setSeverity(e.target.value as Severity | "")}>
                  <option value="">{tr("allOperations")}</option>
                  {(Object.keys(SEVERITY) as Severity[]).map((k) => (
                    <option key={k} value={k}>{tr(SEVERITY[k].label)}</option>
                  ))}
                </select>
              </label>
            </div>
          </div>
          {items.length === 0 ? (
            <p className="empty">{tr("ctl.empty")}</p>
          ) : (
            <div className="table-wrap">
              <table className="data selectable">
                <thead>
                  <tr><th scope="col">#</th><th scope="col">{tr("ctl.category")}</th><th scope="col">{tr("ctl.anomaly")}</th><th scope="col">{tr("ctl.severity")}</th><th scope="col">{tr("cases.statusCol")}</th></tr>
                </thead>
                <tbody>
                  {shown.map((i) => (
                    <tr key={i.id} className={selected?.id === i.id ? "selected" : undefined} onClick={() => setSelectedId(i.id)}>
                      <td className="muted">{items.indexOf(i) + 1}</td>
                      <td>
                        <span className="cat-cell">
                          <span className={`cat cat-${SEVERITY[i.severity].tone}`}><Icon name={i.icon} size={16} /></span>
                          <span className="small">{i.category}</span>
                        </span>
                      </td>
                      <td>
                        <button type="button" className="row-button" onClick={() => setSelectedId(i.id)}>{i.title}</button>
                      </td>
                      <td><Chip tone={SEVERITY[i.severity].tone}>{tr(SEVERITY[i.severity].label)}</Chip></td>
                      <td>
                        {i.severity === "ok" ? <Chip tone="green">{tr("ctl.resolved")}</Chip> : i.severity === "info" ? <Chip tone="gray">{tr("ctl.info")}</Chip> : <Chip tone="red">{tr("ctl.unresolved")}</Chip>}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </section>
        <section className="card side-panel" aria-label={tr("ctl.detail")}>
          <div className="card-head">
            <h2 className="card-title">{tr("ctl.detail")}</h2>
            {shown.length > 0 && (
              <span className="pager">
                <button type="button" className="icon-button" disabled={index <= 0} onClick={() => setSelectedId(shown[index - 1].id)} aria-label={tr("ctl.prev")}>
                  <Icon name="arrowLeft" size={16} />
                </button>
                {tr("ctl.pageOf", { i: index + 1, n: shown.length })}
                <button type="button" className="icon-button" disabled={index >= shown.length - 1} onClick={() => setSelectedId(shown[index + 1].id)} aria-label={tr("ctl.next")}>
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
                <Chip tone={SEVERITY[selected.severity].tone}>{tr(SEVERITY[selected.severity].label)}</Chip>
              </div>
              <h3>{tr("ctl.description")}</h3>
              <p>{selected.description}</p>
              <h3>{tr("ctl.impact")}</h3>
              <p>{selected.impact ?? tr(IMPACT[selected.severity])}</p>
              {selected.documents && selected.documents.length > 0 && (
                <>
                  <h3>{tr("ctl.docsConcerned")} <span className="count-badge">{selected.documents.length}</span></h3>
                  <ul className="doc-mini">
                    {selected.documents.map((d) => (
                      <li key={d.label}>
                        <span className="doc-type doc-pdf"><Icon name="file" size={16} /></span>
                        <span>
                          <strong>{d.label}</strong>
                          <small>{d.state === "missing" ? tr("ctl.docRequired") : tr("ctl.caseDoc")}</small>
                        </span>
                        <Chip tone={d.state === "missing" ? "red" : "green"}>{d.state === "missing" ? tr("ctl.missing") : tr("ctl.present")}</Chip>
                      </li>
                    ))}
                  </ul>
                </>
              )}
              <h3>{tr("ctl.recommended")}</h3>
              <div className="note-blue">
                {selected.steps ? (
                  <ol className="steps-list">
                    {selected.steps.map((st) => (
                      <li key={st}>{st}</li>
                    ))}
                  </ol>
                ) : (
                  selected.action
                )}
              </div>
              <button type="button" className="btn-primary btn-block" onClick={() => go(selected.tab)}>
                <Icon name="file" /> {tr("ctl.openSectionBtn")} <Icon name="arrowRight" />
              </button>
              <div className="actions-row two">
                <button type="button" className="btn-secondary" disabled title={tr("ctl.resolveHint")}>
                  <Icon name="checkCircle" size={18} /> {tr("ctl.markResolved")}
                </button>
                <button type="button" className="btn-secondary" disabled title={tr("ctl.requestHint")}>
                  <Icon name="upload" size={18} /> {tr("ctl.request")}
                </button>
              </div>
              <p className="muted small">{tr("ctl.bothSoon")}</p>
            </>
          ) : (
            <p className="empty">{tr("ctl.noneSelected")}</p>
          )}
        </section>
      </div>
    </>
  );
}
