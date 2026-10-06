import { api, ROLE_LABELS, type Me } from "./api";

interface Props {
  me: Me;
  onChange: (me: Me) => void;
  compact?: boolean;
}

export function OrganizationPicker({ me, onChange, compact }: Props) {
  const select = async (id: string) => onChange(await api.selectOrganization(id));

  if (compact) {
    return (
      <label className="inline">
        <span className="visually-hidden">Changer de société</span>
        <select value={me.active_organization_id ?? ""} onChange={(e) => void select(e.target.value)}>
          {me.memberships.map((m) => (
            <option key={m.organization.id} value={m.organization.id}>{m.organization.name}</option>
          ))}
        </select>
      </label>
    );
  }

  if (me.memberships.length === 0) {
    return <p role="alert">Votre compte n'est rattaché à aucune société active. Contactez votre administrateur.</p>;
  }

  return (
    <section className="card">
      <h1>Choisissez une société</h1>
      <ul className="plain">
        {me.memberships.map((m) => (
          <li key={m.organization.id}>
            <button type="button" onClick={() => void select(m.organization.id)}>
              {m.organization.name}
            </button>{" "}
            <span className="muted">{m.roles.map((r) => ROLE_LABELS[r]).join(", ")}</span>
          </li>
        ))}
      </ul>
    </section>
  );
}
