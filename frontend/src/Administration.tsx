import { useEffect, useState, type FormEvent } from "react";
import { api, ApiError, ROLE_LABELS, type Importer, type Member, type Membership } from "./api";
import { DocumentPolicies } from "./DocumentPolicies";
import { Icon } from "./Icon";
import { tr, useBusinessLabels } from "./i18n";
import { Chip, initials, PageHeader } from "./ui";

/** Administration de la société : importateurs pour tous, utilisateurs pour l'administrateur. */
export function Administration({ membership }: { membership: Membership }) {
  const canEdit = membership.roles.some((r) => r === "declarant" || r === "validator");
  const isAdmin = membership.roles.includes("org_admin");
  const [tab, setTab] = useState<"importers" | "documents" | "users">("importers");

  return (
    <>
      <PageHeader title={tr("nav.administration")} subtitle={tr("adm.settingsOf", { name: membership.organization.name })} />
      <div role="tablist" className="tabs">
        <button type="button" role="tab" aria-selected={tab === "importers"} onClick={() => setTab("importers")}>
          <Icon name="folder" size={18} /> {tr("importers")}
        </button>
        <button type="button" role="tab" aria-selected={tab === "documents"} onClick={() => setTab("documents")}>
          <Icon name="file" size={18} /> {tr("adm.caseDocs")}
        </button>
        {isAdmin && (
          <button type="button" role="tab" aria-selected={tab === "users"} onClick={() => setTab("users")}>
            <Icon name="users" size={18} /> {tr("adm.users")}
          </button>
        )}
      </div>
      {tab === "importers" ? (
        <Importers canEdit={canEdit} />
      ) : tab === "documents" ? (
        <DocumentPolicies isAdmin={isAdmin} />
      ) : (
        <Members />
      )}
    </>
  );
}

function Importers({ canEdit }: { canEdit: boolean }) {
  const [items, setItems] = useState<Importer[]>([]);
  const [name, setName] = useState("");
  const [nif, setNif] = useState("");
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = async () => setItems((await api.importers()).results);
  useEffect(() => {
    void load();
  }, []);

  async function create(event: FormEvent) {
    event.preventDefault();
    setError(null);
    setMessage(null);
    try {
      const created = await api.createImporter({ name, identifiers: nif ? { nif } : {} });
      const dups = created.possible_duplicates ?? [];
      setMessage(
        dups.length
          ? tr("adm.duplicate", { names: dups.map((d) => d.name).join(", ") })
          : tr("importerSaved"),
      );
      setName("");
      setNif("");
      await load();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : tr("saveError"));
    }
  }

  return (
    <section className="card" aria-labelledby="importers-title">
      <h2 id="importers-title" className="card-title">{tr("adm.importersClients")}</h2>
      {items.length === 0 ? (
        <p className="empty">{tr("importerNone")}</p>
      ) : (
        <div className="table-wrap">
          <table className="data">
            <thead>
              <tr><th scope="col">{tr("name")}</th><th scope="col">{tr("identifiers")}</th></tr>
            </thead>
            <tbody>
              {items.map((i) => (
                <tr key={i.id}>
                  <td>{i.name}</td>
                  <td>{Object.entries(i.identifiers).map(([k, v]) => `${k.toUpperCase()} ${v}`).join(" · ")}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {canEdit && (
        <form className="form-grid" onSubmit={create}>
          <label>
            {tr("name")}
            <input required value={name} onChange={(e) => setName(e.target.value)} />
          </label>
          <label>
            {tr("optionalTax")}
            <input value={nif} onChange={(e) => setNif(e.target.value)} />
          </label>
          <div className="form-end">
            <button type="submit" className="btn-primary"><Icon name="plus" /> {tr("add")}</button>
          </div>
        </form>
      )}
      {message && <p role="status">{message}</p>}
      {error && <p role="alert" className="error">⚠ {error}</p>}
    </section>
  );
}

function Members() {
  const labels = useBusinessLabels();
  const [members, setMembers] = useState<Member[]>([]);
  useEffect(() => {
    void api.members().then((p) => setMembers(p.results));
  }, []);

  return (
    <section className="card" aria-labelledby="members-title">
      <h2 id="members-title" className="card-title">{tr("orgUsers")}</h2>
      <p className="muted small">{tr("adm.neverDeleted")}</p>
      <div className="table-wrap">
        <table className="data">
          <thead>
            <tr><th scope="col">{tr("adm.user")}</th><th scope="col">{tr("rolesHeader")}</th><th scope="col">{tr("status")}</th></tr>
          </thead>
          <tbody>
            {members.map((m) => (
              <tr key={m.id}>
                <td>
                  <span className="person">
                    <span className="avatar small-avatar">{initials(m.full_name || m.email)}</span>
                    <span>
                      {m.full_name || m.email}
                      {m.full_name && <span className="block small muted">{m.email}</span>}
                    </span>
                  </span>
                </td>
                <td>{m.roles.map((r) => labels.role(r, ROLE_LABELS[r] ?? r)).join(", ")}</td>
                <td>{m.active ? <Chip tone="green">{tr("active")}</Chip> : <Chip tone="gray">{tr("inactive")}</Chip>}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}
