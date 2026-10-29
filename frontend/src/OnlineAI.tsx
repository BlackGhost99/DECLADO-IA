import { useEffect, useState, type FormEvent } from "react";
import { api, type AISettings, type Importer } from "./api";
import { usageLabel } from "./CaseDetail";
import { Icon } from "./Icon";
import { tr, type MessageKey } from "./i18n";
import { typeLabel } from "./pieceTypes";
import { Chip, errorText, fmtAmount, fmtDate, fmtDateTime } from "./ui";

const STATUS_TONE = { sent: "green", client_refused: "gray", cap_reached: "amber", failed: "red" } as const;

/** Coût estimé en dollars : inconnu reste inconnu, jamais zéro. */
export function aiCost(value: string | null, freeTier: boolean): string {
  if (freeTier) return "0";
  if (value === null) return "—";
  if (Number(value) > 0 && Number(value) < 0.01) return `< ${fmtAmount("0.01")}`;
  return fmtAmount(value, 2);
}

/** Onglet « IA en ligne » de l'administration : réglage de la société, réservé à son administrateur. */
export function AISettingsPanel({ organizationName, onManageClients }: { organizationName: string; onManageClients: () => void }) {
  const [data, setData] = useState<AISettings | null>(null);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api.aiSettings().then(
      (d) => {
        setData(d);
      },
      (err) => setError(errorText(err, tr("saveError"))),
    );
  }, []);

  async function save(change: Partial<Pick<AISettings, "enabled" | "mode">>) {
    if (!data) return;
    setBusy(true);
    setMessage(null);
    setError(null);
    try {
      const next = await api.saveAISettings({
        enabled: data.enabled,
        mode: data.mode,
        row_version: data.row_version,
        ...change,
      });
      setData(next);
      setMessage(tr("ai.saved"));
    } catch (err) {
      setError(errorText(err, tr("saveError")));
    } finally {
      setBusy(false);
    }
  }

  if (!data) return error ? <p role="alert" className="error">⚠ {error}</p> : <p className="muted">{tr("loading")}</p>;
  const { provider, usage } = data;
  const percent = usage.cap > 0 ? Math.min(100, Math.round((usage.sent / usage.cap) * 100)) : 100;
  const list = (title: string, icon: "arrowUpRight" | "x" | "shield", tone: "ok" | "no", keys: MessageKey[]) => (
    <div className={`ia-list ia-list-${tone}`}>
      <h3><Icon name={icon} size={16} /> {title}</h3>
      <ul>{keys.map((k) => <li key={k}>{tr(k)}</li>)}</ul>
    </div>
  );

  return (
    <>
      {message && <p role="status" className="note-blue small">{message}</p>}
      {error && <p role="alert" className="error">⚠ {error}</p>}
      <div className="ia-grid">
        <div className="ia-stack">
          <section className="card" aria-labelledby="ai-title">
            <h2 id="ai-title" className="card-title">{tr("ai.title")}</h2>
            <p className="muted small">{tr("ai.intro")}</p>
            <div className="ia-state">
              <div>
                <strong>{tr(data.enabled ? "ai.onFor" : "ai.offFor", { name: organizationName })}</strong>
                <small>{tr("ai.stateHint")}</small>
              </div>
              <label className="ia-switch">
                <input
                  type="checkbox"
                  checked={data.enabled}
                  disabled={busy || (!provider.configured && !data.enabled)}
                  onChange={(e) => void save({ enabled: e.target.checked })}
                />
                {tr(data.enabled ? "ai.on" : "ai.off")}
              </label>
            </div>
            {!provider.configured && <p className="note-amber small ia-gap">{tr("ai.notConfigured")}</p>}
            <fieldset className="ia-radio" disabled={busy}>
              <legend className="small-heading">{tr("ai.when")}</legend>
              {(["auto", "on_demand"] as const).map((mode) => (
                <label key={mode}>
                  <input type="radio" name="ai-mode" checked={data.mode === mode} onChange={() => void save({ mode })} />
                  <span>
                    <strong>{tr(mode === "auto" ? "ai.modeAuto" : "ai.modeDemand")}</strong>
                    <small>{tr(mode === "auto" ? "ai.modeAutoHint" : "ai.modeDemandHint")}</small>
                  </span>
                </label>
              ))}
            </fieldset>
          </section>
          <section className="card" aria-labelledby="ai-sent-title">
            <h2 id="ai-sent-title" className="card-title">{tr("ai.sentTitle")}</h2>
            <div className="ia-lists">
              {list(tr("ai.sent"), "arrowUpRight", "ok", ["ai.sent1", "ai.sent2", "ai.sent3"])}
              {list(tr("ai.never"), "x", "no", ["ai.never1", "ai.never2", "ai.never3", "ai.never4"])}
              {list(tr("ai.does"), "shield", "no", ["ai.does1", "ai.does2", "ai.does3", "ai.does4"])}
            </div>
            <p className="muted small ia-gap">{tr("ai.control")}</p>
          </section>
        </div>
        <div className="ia-stack">
          <section className="card">
            <h2 className="card-title">{tr("ai.service")}</h2>
            <p className="small">{tr("ai.managedByOperator")}</p>
            <p className="small muted">{tr("ai.place")}: {tr("ai.placeValue")}. {tr("ai.retentionValue")}.</p>
            {provider.free_tier && <p className="note-amber small" role="note">{tr("ai.freeTier")}</p>}
          </section>
          <section className="card" aria-labelledby="ai-cap-title">
            <h2 id="ai-cap-title" className="card-title">{tr("ai.cap")}</h2>
            <p className="small"><strong>{data.monthly_cap}</strong> {tr("ai.perMonth")}</p>
            <p className="muted small">{tr("ai.capOperator")}</p>
            <div className="ia-meter" role="progressbar" aria-valuemin={0} aria-valuemax={usage.cap} aria-valuenow={Math.min(usage.sent, usage.cap)} aria-label={tr("ai.usage", { sent: usage.sent, cap: usage.cap })}>
              <span style={{ width: `${percent}%` }} />
            </div>
            <p className="muted small">
              {tr("ai.usage", { sent: usage.sent, cap: usage.cap })}{" "}
              {tr("ai.capHint")}
            </p>
          </section>
          <section className="card" aria-labelledby="ai-refusing-title">
            <h2 id="ai-refusing-title" className="card-title">{tr("ai.refusing")}</h2>
            {data.refusing_clients.length === 0 ? (
              <p className="muted small">{tr("ai.refusingNone")}</p>
            ) : (
              <ul className="ia-plain">
                {data.refusing_clients.map((c) => (
                  <li key={c.id}>
                    <strong>{c.name}</strong>
                    {c.refused_at && <span className="block small muted">{tr("ai.refusedOn", { date: fmtDate(c.refused_at), name: c.refused_by ?? "—" })}</span>}
                  </li>
                ))}
              </ul>
            )}
            <p className="muted small ia-gap">
              {tr("ai.refusingHint")}{" "}
              <button type="button" className="source-link" onClick={onManageClients}>{tr("ai.manage")}</button>
            </p>
          </section>
        </div>
      </div>
      <section className="card ia-journal" aria-labelledby="ai-journal-title">
        <h2 id="ai-journal-title" className="card-title">{tr("ai.journal")}</h2>
        {data.journal.length === 0 ? (
          <p className="empty">{tr("ai.journalNone")}</p>
        ) : (
          <div className="table-wrap">
            <table className="data">
              <thead>
                <tr>
                  <th scope="col">{tr("ai.colDate")}</th><th scope="col">{tr("ai.colCase")}</th><th scope="col">{tr("ai.colPiece")}</th>
                  <th scope="col" className="num">{tr("ai.colAsked")}</th><th scope="col" className="num">{tr("ai.colFound")}</th>
                  <th scope="col">{tr("ai.colStatus")}</th>
                </tr>
              </thead>
              <tbody>
                {data.journal.map((r) => (
                  <tr key={r.id}>
                    <td className="nowrap">{fmtDateTime(r.created_at)}</td>
                    <td className="nowrap">{r.case_reference}</td>
                    <td>
                      {r.detected_type ? typeLabel({ code: r.detected_type }) : usageLabel(r.usage, r.usage)}
                      <span className="block small muted">{r.file_name}</span>
                    </td>
                    <td className="num">{r.requested}</td>
                    <td className="num">{r.status === "sent" ? r.found : "—"}</td>
                    <td title={r.error_message ?? undefined}>
                      <Chip tone={STATUS_TONE[r.status]}>{tr(`ai.status.${r.status}` as MessageKey)}</Chip>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>
    </>
  );
}

/** Refus du client : posé par un agent ou l'administrateur, levé seulement par l'administrateur. */
export function ImporterAIChoice({
  importer,
  isAdmin,
  onSaved,
  onClose,
}: {
  importer: Importer;
  isAdmin: boolean;
  onSaved: (updated: Importer) => void;
  onClose: () => void;
}) {
  const [refused, setRefused] = useState(Boolean(importer.ai_refused));
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const locked = Boolean(importer.ai_refused) && !isAdmin;

  async function submit(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      onSaved(await api.setImporterAIRefusal(importer.id, refused));
    } catch (err) {
      setError(errorText(err, tr("saveError")));
    } finally {
      setBusy(false);
    }
  }

  return (
    <form className="subcard ia-edit" onSubmit={submit} aria-label={`${tr("imp.edit")} : ${importer.name}`}>
      <h3>{importer.name}</h3>
      <label className="ia-check">
        <input type="checkbox" checked={refused} disabled={locked || busy} onChange={(e) => setRefused(e.target.checked)} />
        <span>
          <strong>{tr("imp.aiCheck")}</strong>
          <span className="block small muted">{tr("imp.aiCheckHint")}</span>
          {locked && <span className="block small muted">{tr("imp.aiAdminOnly")}</span>}
        </span>
      </label>
      <p className="muted small">{tr("imp.aiLogged")}</p>
      <div className="ia-note-row">
        <button type="submit" className="btn-primary btn-small-pad" disabled={busy || locked || refused === Boolean(importer.ai_refused)}>{tr("save")}</button>
        <button type="button" className="btn-small" onClick={onClose}>{tr("cancel")}</button>
      </div>
      {error && <p role="alert" className="error small">⚠ {error}</p>}
    </form>
  );
}
