import { useEffect, useState, type FormEvent } from "react";
import { api, type PlatformAIOrganization, type PlatformAISettings } from "./api";
import { tr } from "./i18n";
import { aiCost } from "./OnlineAI";
import { Chip, errorText } from "./ui";

/** Vue exploitant : configuration du service et quotas, sans dossiers ni clients. */
export function PlatformAIPanel() {
  const [data, setData] = useState<PlatformAISettings | null>(null);
  const [error, setError] = useState("");
  useEffect(() => {
    api.platformAISettings().then(setData, (err) => setError(errorText(err, tr("saveError"))));
  }, []);
  if (!data) return error ? <p role="alert" className="error">{error}</p> : <p className="muted">{tr("loading")}</p>;
  const { provider } = data;
  return (
    <section className="card ia-journal" aria-labelledby="platform-ai-title">
      <h2 id="platform-ai-title" className="card-title">{tr("ai.platformTitle")}</h2>
      <dl className="ia-kv">
        <dt>{tr("ai.provider")}</dt><dd>{provider.label ?? tr("ai.noProvider")}</dd>
        <dt>{tr("ai.model")}</dt><dd>{provider.model ?? "—"}</dd>
        <dt>{tr("ai.key")}</dt><dd><Chip tone={provider.configured ? "green" : "gray"}>{tr(provider.configured ? "ai.keyOk" : "ai.keyMissing")}</Chip></dd>
        <dt>{tr("ai.place")}</dt><dd>{tr("ai.placeValue")}</dd>
        <dt>{tr("ai.retention")}</dt><dd>{tr("ai.retentionValue")}</dd>
        <dt>{tr("ai.personal")}</dt><dd>{tr("ai.personalValue")}</dd>
      </dl>
      <p className="note-blue small">{tr("ai.keyNote")}</p>
      {provider.free_tier && <p className="note-amber small">{tr("ai.freeTier")}</p>}
      <h3 className="card-title">{tr("ai.quotasTitle")}</h3>
      <p className="muted small">{tr("ai.quotaHelp")}</p>
      <div className="ia-stack">
        {data.organizations.map((org) => <Quota key={org.id} organization={org}
          onSaved={(next) => setData((old) => old && ({ ...old, organizations: old.organizations.map((o) => o.id === next.id ? next : o) }))} />)}
      </div>
    </section>
  );
}

function Quota({ organization: org, onSaved }: { organization: PlatformAIOrganization; onSaved: (next: PlatformAIOrganization) => void }) {
  const [cap, setCap] = useState(String(org.monthly_cap));
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [saved, setSaved] = useState(false);
  async function save(event: FormEvent) {
    event.preventDefault();
    const value = Number(cap);
    if (!cap.trim() || !Number.isInteger(value) || value < 0 || value > 100000) return;
    setBusy(true); setError(""); setSaved(false);
    try {
      onSaved(await api.savePlatformAIQuota(org.id, { monthly_cap: value, row_version: org.row_version }));
      setSaved(true);
    } catch (err) { setError(errorText(err, tr("saveError"))); }
    finally { setBusy(false); }
  }
  return (
    <form className="card" onSubmit={(event) => void save(event)} aria-label={org.name}>
      <h4>{org.name}</h4>
      <div className="ia-row">
        <label htmlFor={`quota-${org.id}`}>{tr("ai.cap")}</label>
        <input id={`quota-${org.id}`} type="number" required min={0} max={100000} step={1} value={cap} onChange={(e) => setCap(e.target.value)} />
        <span>{tr("ai.perMonth")}</span>
        <button className="btn-small" type="submit" disabled={busy || cap === String(org.monthly_cap)}>{tr("save")}</button>
      </div>
      <p className="small muted">{tr("ai.usage", { sent: org.usage.sent, cap: org.monthly_cap })} {org.usage.cost_estimate === null
        ? tr("ai.costUnknown") : tr("ai.cost", { cost: aiCost(org.usage.cost_estimate, false) })}</p>
      {saved && <p role="status">{tr("ai.saved")}</p>}
      {error && <p role="alert" className="error">{error}</p>}
    </form>
  );
}
