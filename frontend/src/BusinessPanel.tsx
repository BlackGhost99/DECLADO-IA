import { useEffect, useState, type FormEvent } from "react";
import { api, ApiError, type BusinessProfile, type HabilitationKind, type PlatformCompanyDetail } from "./api";
import { tr, type MessageKey } from "./i18n";
import { CountrySelect, countryLabel, profileLabel, SecondaryProfiles } from "./Onboarding";
import { Chip } from "./ui";

const message = (error: unknown) => error instanceof ApiError ? error.message : tr("saveError");

export const HABILITATION_KINDS: [HabilitationKind, MessageKey][] = [
  ["customs_broker", "met.kind.customs_broker"],
  ["temporary_authorization", "met.kind.temporary_authorization"],
  ["own_account", "met.kind.own_account"],
  ["customs_expert", "met.kind.customs_expert"],
];
export const habilitationLabel = (kind: HabilitationKind) =>
  tr(HABILITATION_KINDS.find(([k]) => k === kind)?.[1] ?? "met.kind.customs_broker");
const STATUS: Record<string, ["green" | "amber" | "gray", MessageKey]> = {
  verified: ["green", "met.status.verified"],
  declared: ["amber", "met.status.declared"],
  revoked: ["gray", "met.status.revoked"],
};

/** MET-02, MET-03 : métiers secondaires et habilitations douanières d'une société, côté console. */
export function BusinessPanel({ detail, onUpdated }: { detail: PlatformCompanyDetail; onUpdated: (d: PlatformCompanyDetail) => void }) {
  const [secondary, setSecondary] = useState<BusinessProfile[]>(detail.secondary_profiles);
  const [reason, setReason] = useState("");
  const [kind, setKind] = useState<HabilitationKind>("customs_broker");
  const [country, setCountry] = useState(detail.country_code);
  const [reference, setReference] = useState("");
  const [from, setFrom] = useState("");
  const [until, setUntil] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  useEffect(() => setSecondary(detail.secondary_profiles), [detail.secondary_profiles, detail.row_version]);

  const run = async (call: () => Promise<PlatformCompanyDetail>, after?: () => void) => {
    setBusy(true);
    setError("");
    try {
      onUpdated(await call());
      after?.();
    } catch (err) { setError(message(err)); }
    finally { setBusy(false); }
  };
  const saveProfiles = (event: FormEvent) => {
    event.preventDefault();
    void run(() => api.updateCompanyProfiles(detail.id, { secondary_profiles: secondary, row_version: detail.row_version, reason: reason.trim() }),
      () => setReason(""));
  };
  const addHabilitation = (event: FormEvent) => {
    event.preventDefault();
    void run(() => api.addHabilitation(detail.id, { kind, country_code: country, reference: reference.trim(),
      valid_from: from || null, valid_until: until || null, note: "" }), () => { setReference(""); setFrom(""); setUntil(""); });
  };
  const decide = (id: string, version: number, action: "verify" | "revoke") =>
    void run(() => api.decideHabilitation(detail.id, id, action, { row_version: version, reason: reason.trim() }), () => setReason(""));
  const changed = secondary.slice().sort().join() !== detail.secondary_profiles.slice().sort().join();
  const reasonOk = reason.trim().length >= 8;
  const basis = detail.declaration_basis;

  return (
    <section className="console-panel console-history" aria-labelledby="met-title">
      <h4 id="met-title">{tr("met.title")}</h4>
      <p className="muted small">
        {profileLabel(detail.primary_profile)}
        {detail.secondary_profiles.length > 0 && ` + ${detail.secondary_profiles.map(profileLabel).join(", ")}`}
      </p>
      <Chip tone={basis ? "green" : "gray"}>
        {tr(basis === "profile" ? "met.basis.profile" : basis === "habilitation" ? "met.basis.habilitation" : "met.basis.none")}
      </Chip>
      <p className="muted small">{tr("met.principle")}</p>

      <form onSubmit={saveProfiles} className="console-cap-form">
        <div className="console-reason">
          <SecondaryProfiles primary={detail.primary_profile} value={secondary} onChange={setSecondary} />
        </div>
        <label className="console-reason">{tr("met.reasonLabel")}<textarea aria-label={tr("met.reasonLabel")} minLength={8} maxLength={500}
          value={reason} onChange={(e) => setReason(e.target.value)} placeholder={tr("met.reasonHint")} /></label>
        {error && <p className="error" role="alert">{error}</p>}
        <button className="btn-primary btn-small-pad" type="submit" disabled={busy || !reasonOk || !changed}>{tr("met.saveProfiles")}</button>
      </form>

      <h4>{tr("met.habilitations")}</h4>
      {detail.habilitations.length === 0 ? <p className="muted small">{tr("met.noHabilitation")}</p> :
        <ul className="console-admin-list">{detail.habilitations.map((h) => {
          const [tone, label] = STATUS[h.status] ?? STATUS.declared;
          return <li key={h.id}>
            <strong>{habilitationLabel(h.kind)} · {h.reference}</strong>
            <span className="muted small">{countryLabel(h.country_code)}
              {(h.valid_from || h.valid_until) && ` · ${h.valid_from ?? "…"} → ${h.valid_until ?? "…"}`}</span>
            <div className="console-admin-tags">
              <Chip tone={tone}>{tr(label)}</Chip>
              {h.status === "declared" && <button type="button" className="btn-outline-small" disabled={busy || !reasonOk}
                title={reasonOk ? undefined : tr("met.reasonFirst")} onClick={() => decide(h.id, h.row_version, "verify")}>{tr("met.verify")}</button>}
              {h.status !== "revoked" && <button type="button" className="btn-outline-small" disabled={busy || !reasonOk}
                title={reasonOk ? undefined : tr("met.reasonFirst")} onClick={() => decide(h.id, h.row_version, "revoke")}>{tr("met.revoke")}</button>}
            </div>
          </li>;
        })}</ul>}

      <form onSubmit={addHabilitation} className="console-cap-form" aria-label={tr("met.addHabilitation")}>
        <label>{tr("met.kind")}<select aria-label={tr("met.kind")} value={kind} onChange={(e) => setKind(e.target.value as HabilitationKind)}>
          {HABILITATION_KINDS.map(([k, l]) => <option key={k} value={k}>{tr(l)}</option>)}
        </select></label>
        <label>{tr("onb.country")}<CountrySelect id="hab-country" value={country} onChange={setCountry} /></label>
        <label className="console-reason">{tr("met.reference")}<input aria-label={tr("met.reference")} required maxLength={120}
          value={reference} onChange={(e) => setReference(e.target.value)} placeholder={tr("met.referenceHint")} /></label>
        <label>{tr("met.validFrom")}<input aria-label={tr("met.validFrom")} type="date" value={from} onChange={(e) => setFrom(e.target.value)} /></label>
        <label>{tr("met.validUntil")}<input aria-label={tr("met.validUntil")} type="date" value={until} onChange={(e) => setUntil(e.target.value)} /></label>
        <button className="btn-primary btn-small-pad" type="submit" disabled={busy || !reference.trim()}>{tr("met.addHabilitation")}</button>
      </form>
      <p className="muted small">{tr("met.verifyNote")}</p>
    </section>
  );
}
