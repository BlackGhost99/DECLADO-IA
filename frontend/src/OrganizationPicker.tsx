import { api, ROLE_LABELS, type Me } from "./api";
import { useBusinessLabels, useI18n } from "./i18n";

interface Props {
  me: Me;
  onChange: (me: Me) => void;
  compact?: boolean;
}

export function OrganizationPicker({ me, onChange, compact }: Props) {
  const { t } = useI18n();
  const labels = useBusinessLabels();
  const select = async (id: string) => onChange(await api.selectOrganization(id));

  if (compact) {
    return (
      <label className="inline">
        <span className="visually-hidden">{t("orgSwitch")}</span>
        <select value={me.active_organization_id ?? ""} onChange={(e) => void select(e.target.value)}>
          {me.memberships.map((m) => (
            <option key={m.organization.id} value={m.organization.id}>{m.organization.name}</option>
          ))}
        </select>
      </label>
    );
  }

  if (me.memberships.length === 0) {
    return <p role="alert">{t("orgNone")}</p>;
  }

  return (
    <section className="card org-picker">
      <h1>{t("orgChoose")}</h1>
      <ul className="plain">
        {me.memberships.map((m) => (
          <li key={m.organization.id}>
            <button type="button" className="btn-primary" onClick={() => void select(m.organization.id)}>
              {m.organization.name}
            </button>{" "}
            <span className="muted">{m.roles.map((r) => labels.role(r, ROLE_LABELS[r])).join(", ")}</span>
          </li>
        ))}
      </ul>
    </section>
  );
}
