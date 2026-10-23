import type { ReactNode } from "react";
import { ApiError, type EditionBrief, type GoodsLine, type Revision, type UserBrief } from "./api";
import { Icon, type IconName } from "./Icon";

export type EditionOption = EditionBrief & { warning: string | null };

export function errorText(err: unknown, fallback: string): string {
  if (!(err instanceof ApiError)) return fallback;
  if (err.code === "REVISION_CONFLICT")
    return "Quelqu'un a modifié cet élément depuis votre ouverture. Rechargez pour voir sa version ; rien n'a été écrasé.";
  return err.message;
}

export const fmtDate = (iso: string) => new Date(iso).toLocaleDateString("fr-FR");
export const fmtDateTime = (iso: string) =>
  new Date(iso).toLocaleString("fr-FR", { dateStyle: "short", timeStyle: "short" });

/**
 * Montant décimal (texte) affiché à la française : « 61187.5 » → « 61 187,50 ».
 * Le calcul se fait sur le texte, jamais en nombre flottant ; une valeur inconnue reste inconnue.
 */
export function fmtAmount(value: string | null | undefined, decimals = 2): string {
  if (value === null || value === undefined || value === "") return "";
  const m = /^(-?)(\d+)(?:\.(\d+))?$/.exec(value.trim());
  if (!m) return value;
  const [, sign, int, frac = ""] = m;
  const grouped = int.replace(/\B(?=(\d{3})+(?!\d))/g, "\u202f");
  const dec = decimals > 0 ? `,${(frac + "0".repeat(decimals)).slice(0, Math.max(decimals, frac.replace(/0+$/, "").length))}` : frac.replace(/0+$/, "") ? `,${frac.replace(/0+$/, "")}` : "";
  return `${sign}${grouped}${dec}`;
}

/** Quantité : groupée, sans décimales ajoutées. */
export const fmtQty = (value: string | null | undefined) => fmtAmount(value, 0);

export function relativeTime(iso: string, now = Date.now()): string {
  const minutes = Math.round((now - new Date(iso).getTime()) / 60000);
  if (minutes < 1) return "à l'instant";
  if (minutes < 60) return `il y a ${minutes} min`;
  const hours = Math.round(minutes / 60);
  if (hours < 24) return `il y a ${hours} h`;
  const days = Math.round(hours / 24);
  return `il y a ${days} j`;
}

/** Nom affichable d'une personne : son nom s'il est connu, sinon son adresse. */
export const personName = (u: Pick<UserBrief, "email" | "full_name"> | null | undefined) =>
  u ? u.full_name || u.email : "";

export function initials(text: string): string {
  const base = text.includes("@") ? text.split("@")[0].replace(/[._-]+/g, " ") : text;
  const words = base.trim().split(/\s+/).filter(Boolean);
  return ((words[0]?.[0] ?? "?") + (words[1]?.[0] ?? "")).toUpperCase();
}

export type Tone = "green" | "amber" | "red" | "blue" | "gray";

const STATE_TONES: Record<string, Tone> = {
  draft: "gray",
  in_preparation: "blue",
  to_validate: "amber",
  to_correct: "red",
  validated: "green",
  archived: "gray",
};

export function Chip({ tone, children, icon }: { tone: Tone; children: ReactNode; icon?: IconName }) {
  return (
    <span className={`chip chip-${tone}`}>
      {icon && <Icon name={icon} size={14} />}
      {children}
    </span>
  );
}

export function StateChip({ state, label }: { state: string; label: string }) {
  return <Chip tone={STATE_TONES[state] ?? "gray"}>{label}</Chip>;
}

/** Carte de statistique : pictogramme coloré, libellé, valeur. */
export function StatCard({
  icon,
  tone,
  label,
  value,
  hint,
}: {
  icon: IconName;
  tone: Tone;
  label: string;
  value: ReactNode;
  hint?: ReactNode;
}) {
  return (
    <div className="stat">
      <span className={`stat-icon tone-${tone}`}>
        <Icon name={icon} size={24} />
      </span>
      <div>
        <div className="stat-label">{label}</div>
        <div className="stat-value">{value}</div>
        {hint && <div className="stat-hint">{hint}</div>}
      </div>
    </div>
  );
}

export function PageHeader({ title, subtitle, children }: { title: ReactNode; subtitle?: ReactNode; children?: ReactNode }) {
  return (
    <div className="page-header">
      <div>
        <h1>{title}</h1>
        {subtitle && <p className="page-subtitle">{subtitle}</p>}
      </div>
      {children && <div className="page-actions">{children}</div>}
    </div>
  );
}

// ---- Étapes d'un dossier -------------------------------------------------------------------

export type StepState = "done" | "current" | "todo" | "later";
export interface Step {
  key: string;
  label: string;
  detail: string;
  state: StepState;
}

/**
 * Avancement réel d'une révision. Calcul et export n'existent pas encore : ils restent « à venir »
 * et ne sont jamais comptés comme faits.
 */
export function caseSteps(rev: Revision): Step[] {
  const docs = rev.documents.filter((d) => !d.replaced_by_id);
  const invoicesWithLines = rev.invoices.filter((i) => i.lines.length > 0);
  const goods = rev.goods_lines;
  const decided = goods.filter((g) => g.decision?.is_current).length;
  const validated = rev.state === "validated" || rev.state === "archived";

  const raw: Omit<Step, "state">[] = [
    { key: "documents", label: "Documents reçus", detail: docs.length ? `${docs.length} pièce(s)` : "facture, B/L…" },
    { key: "donnees", label: "Extraction", detail: invoicesWithLines.length ? `${invoicesWithLines.length} facture(s) lue(s)` : "lecture des pièces" },
    { key: "marchandises", label: "Classification", detail: goods.length ? `${decided} / ${goods.length} code(s) validé(s)` : "codes SH" },
    { key: "calculs", label: "Calcul", detail: "à venir" },
    { key: "validation", label: "Validation", detail: rev.state_label },
    { key: "export", label: "Export", detail: "à venir" },
  ];
  const done: Record<string, boolean> = {
    documents: docs.length > 0,
    donnees: invoicesWithLines.length > 0,
    marchandises: goods.length > 0 && decided === goods.length,
    validation: validated,
  };
  let currentSet = false;
  return raw.map((s) => {
    if (s.key === "calculs" || s.key === "export") return { ...s, state: "later" };
    if (done[s.key]) return { ...s, state: "done" };
    if (!currentSet) {
      currentSet = true;
      return { ...s, state: "current" };
    }
    return { ...s, state: "todo" };
  });
}

export function progressOf(steps: Step[]): number {
  return Math.round((steps.filter((s) => s.state === "done").length / steps.length) * 100);
}

export function Stepper({ steps, onSelect }: { steps: Step[]; onSelect?: (key: string) => void }) {
  return (
    <ol className="stepper">
      {steps.map((s, i) => (
        <li key={s.key} className={`step step-${s.state}`}>
          <button type="button" className="step-dot" onClick={() => onSelect?.(s.key)} disabled={!onSelect} aria-label={`Étape ${i + 1} : ${s.label}`}>
            {s.state === "done" ? <Icon name="check" size={16} /> : i + 1}
          </button>
          <span className="step-label">{s.label}</span>
          <span className="step-detail">{s.detail}</span>
        </li>
      ))}
    </ol>
  );
}

export function ProgressBar({ value }: { value: number }) {
  return (
    <span className="progress" role="progressbar" aria-valuenow={value} aria-valuemin={0} aria-valuemax={100}>
      <span className="progress-track">
        <span className="progress-fill" style={{ width: `${value}%` }} />
      </span>
      <span className="progress-value">{value}%</span>
    </span>
  );
}

// ---- Journal -----------------------------------------------------------------------------------

export const EVENT_LABELS: Record<string, string> = {
  "auth.login": "Connexion",
  "case.created": "Dossier créé",
  "case.updated": "Dossier modifié",
  "case.assigned": "Dossier affecté",
  "case.document_attached": "Pièce ajoutée",
  "case.document_replaced": "Pièce remplacée",
  "revision.updated": "Informations du dossier modifiées",
  "document.stored": "Document enregistré",
  "document.extraction_requested": "Lecture demandée",
  "document.extraction_failed": "Lecture en échec",
  "extraction.run": "Lecture terminée",
  "extraction.divergence_resolved": "Divergence tranchée",
  "invoice.created": "Facture ajoutée",
  "invoice.updated": "Facture modifiée",
  "invoice.extracted": "Facture lue",
  "invoice_line.created": "Ligne ajoutée",
  "invoice_line.updated": "Ligne corrigée",
  "invoice_line.code_observed": "Code relevé sur une ligne",
  "goods_line.created": "Marchandise préparée",
  "goods_line.updated": "Marchandise modifiée",
  "goods_line.code_checked": "Code contrôlé",
  "goods_line.code_decided": "Code validé",
  "importer.created": "Importateur ajouté",
  "importer.updated": "Importateur modifié",
  "membership.created": "Utilisateur ajouté",
  "membership.deactivated": "Utilisateur désactivé",
  "membership.roles_changed": "Rôles modifiés",
  "user.deactivated": "Compte désactivé",
  "tariff.edition_published": "Édition du tarif publiée",
  "tariff.edition_withdrawn": "Édition du tarif retirée",
  "tariff.issue_resolved": "Anomalie du tarif résolue",
  "tariff.node_corrected": "Code du tarif corrigé",
};

export const eventLabel = (type: string) => EVENT_LABELS[type] ?? type;

export function eventIcon(type: string): IconName {
  if (type.includes("failed")) return "alert";
  if (type.startsWith("goods_line.code_decided")) return "checkCircle";
  if (type.startsWith("case.document") || type.startsWith("document")) return "file";
  if (type.startsWith("extraction") || type.startsWith("invoice")) return "eye";
  if (type.startsWith("goods_line")) return "box";
  if (type.startsWith("case")) return "folder";
  return "history";
}

/** Statut de classement d'une marchandise, tel que l'agent doit le lire. */
export function goodsStatus(g: GoodsLine): { tone: Tone; label: string; code: string } {
  const check = g.latest_check;
  if (g.decision?.is_current) return { tone: "green", label: "Validé", code: g.decision.selected_code_display };
  if (g.decision) return { tone: "red", label: "À revoir", code: g.decision.selected_code_display };
  if (!check) return { tone: "gray", label: "À contrôler", code: "" };
  if (!check.is_current || check.human_confirmation === "stale") return { tone: "amber", label: "À recontrôler", code: check.observed_code ?? "" };
  if (check.recognition_status === "recognized") return { tone: "amber", label: "À valider", code: check.node?.code_display ?? check.observed_code ?? "" };
  return { tone: "amber", label: "À vérifier", code: check.observed_code ?? "" };
}

/** Somme exacte de montants décimaux écrits en texte (jamais en flottant). */
export function addDecimals(values: string[]): string {
  const scale = Math.max(0, ...values.map((v) => (v.split(".")[1] ?? "").length));
  const toInt = (v: string) => {
    const [i, f = ""] = v.replace(/^-/, "").split(".");
    const n = BigInt(i + f.padEnd(scale, "0"));
    return v.startsWith("-") ? -n : n;
  };
  const sum = values.reduce((acc, v) => acc + toInt(v), 0n);
  const neg = sum < 0n;
  const digits = (neg ? -sum : sum).toString().padStart(scale + 1, "0");
  const out = scale ? `${digits.slice(0, -scale)}.${digits.slice(-scale)}` : digits;
  return neg ? `-${out}` : out;
}
