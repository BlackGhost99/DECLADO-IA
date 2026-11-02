import { useState } from "react";
import { api, canDeclare, type CaseDetail, type Membership } from "./api";
import { Icon } from "./Icon";
import { tr } from "./i18n";
import { fmtDate } from "./ui";

type Act = (a: () => Promise<unknown>) => Promise<void>;

/** Fin de vie (WF-05, WF-06) : dépôt dans SYDONIA saisi par l'agent, archivage, sortie des archives. */
export function CaseLifecycle({ detail, membership, act }: { detail: CaseDetail; membership: Membership; act: Act }) {
  const rev = detail.revision;
  const [number, setNumber] = useState("");
  const [day, setDay] = useState("");
  const [reason, setReason] = useState("");
  const [open, setOpen] = useState<"lodge" | "archive" | "restore" | null>(null);
  const has = (...roles: string[]) => membership.roles.some((r) => roles.includes(r));
  const validated = rev.state === "validated";
  // Dépôt en douane : réservé à une société habilitée à déclarer (MET-04).
  const canLodge = validated && !rev.customs_declaration_number && canDeclare(membership) &&
    has("declarant", "validator", "org_admin");
  const canArchive = (validated || rev.is_editable) && has("validator", "org_admin");
  const canRestore = rev.state === "archived" && has("org_admin");
  const reasonNeeded = open === "restore" || (open === "archive" && !validated);
  const done = () => {
    setOpen(null);
    setNumber("");
    setDay("");
    setReason("");
  };
  const submit = () =>
    void act(async () => {
      if (open === "lodge") await api.lodge(detail.id, rev.row_version, number.trim(), day);
      else if (open) await api.workflow(detail.id, open, rev.row_version, reason.trim());
      done();
    });

  return (
    <>
      {rev.customs_declaration_number && (
        <p className="note-blue small">
          <Icon name="checkCircle" size={15} />{" "}
          {tr("life.lodgedInfo", { number: rev.customs_declaration_number, date: rev.lodged_on ? fmtDate(rev.lodged_on) : "—" })}
        </p>
      )}
      {rev.state === "archived" && <p className="note-amber small">{tr("life.archivedInfo")}</p>}
      {!open && canLodge && (
        <button type="button" className="btn-secondary btn-block btn-row" onClick={() => setOpen("lodge")}>
          <Icon name="flag" /> <span>{tr("life.lodge")}<small>{tr("life.lodgeHint")}</small></span> <Icon name="arrowRight" />
        </button>
      )}
      {!open && canArchive && (
        <button type="button" className="btn-secondary btn-block btn-row" onClick={() => setOpen("archive")}>
          <Icon name="archive" /> <span>{tr("life.archive")}<small>{tr(validated ? "life.archiveHint" : "life.abandonHint")}</small></span> <Icon name="arrowRight" />
        </button>
      )}
      {!open && canRestore && (
        <button type="button" className="btn-secondary btn-block btn-row" onClick={() => setOpen("restore")}>
          <Icon name="history" /> <span>{tr("life.restore")}<small>{tr("life.restoreHint")}</small></span> <Icon name="arrowRight" />
        </button>
      )}
      {open && (
        <form className="nc-form" aria-label={tr(`life.${open}`)} onSubmit={(e) => { e.preventDefault(); submit(); }}>
          {open === "lodge" ? (
            <>
              <label className="nc-field">
                <span className="nc-label">{tr("life.number")} *</span>
                <input type="text" required maxLength={60} value={number} onChange={(e) => setNumber(e.target.value)} />
              </label>
              <label className="nc-field">
                <span className="nc-label">{tr("life.lodgedOn")} *</span>
                <input type="date" required value={day} onChange={(e) => setDay(e.target.value)} />
              </label>
              <p className="muted small">{tr("life.notChecked")}</p>
            </>
          ) : (
            <label className="nc-field">
              <span className="nc-label">{tr("life.reason")}{reasonNeeded && " *"}</span>
              <textarea rows={2} required={reasonNeeded} maxLength={2000} value={reason} onChange={(e) => setReason(e.target.value)} />
            </label>
          )}
          <div className="tx-btns">
            <button type="button" className="btn-secondary" onClick={done}>{tr("cancel")}</button>
            <button type="submit" className="btn-primary">{tr(`life.${open}`)}</button>
          </div>
        </form>
      )}
    </>
  );
}
