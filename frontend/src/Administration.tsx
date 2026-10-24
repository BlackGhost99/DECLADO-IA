import { useEffect, useState, type FormEvent } from "react";
import { api, ApiError, ROLE_LABELS, type Importer, type Member, type Membership } from "./api";
import { DocumentPolicies } from "./DocumentPolicies";
import { Icon } from "./Icon";
import { Chip, initials, PageHeader } from "./ui";

/** Administration de la société : importateurs pour tous, utilisateurs pour l'administrateur. */
export function Administration({ membership }: { membership: Membership }) {
  const canEdit = membership.roles.some((r) => r === "declarant" || r === "validator");
  const isAdmin = membership.roles.includes("org_admin");
  const [tab, setTab] = useState<"importers" | "documents" | "users">("importers");

  return (
    <>
      <PageHeader title="Administration" subtitle={`Paramètres de ${membership.organization.name}.`} />
      <div role="tablist" className="tabs">
        <button type="button" role="tab" aria-selected={tab === "importers"} onClick={() => setTab("importers")}>
          <Icon name="folder" size={18} /> Importateurs
        </button>
        <button type="button" role="tab" aria-selected={tab === "documents"} onClick={() => setTab("documents")}>
          <Icon name="file" size={18} /> Pièces du dossier
        </button>
        {isAdmin && (
          <button type="button" role="tab" aria-selected={tab === "users"} onClick={() => setTab("users")}>
            <Icon name="users" size={18} /> Utilisateurs
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
          ? `Importateur enregistré. Doublon possible : ${dups.map((d) => d.name).join(", ")}. Vérifiez avant de l'utiliser.`
          : "Importateur enregistré.",
      );
      setName("");
      setNif("");
      await load();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Enregistrement impossible.");
    }
  }

  return (
    <section className="card" aria-labelledby="importers-title">
      <h2 id="importers-title" className="card-title">Importateurs (clients)</h2>
      {items.length === 0 ? (
        <p className="empty">Aucun importateur pour cette société.</p>
      ) : (
        <div className="table-wrap">
          <table className="data">
            <thead>
              <tr><th scope="col">Nom</th><th scope="col">Identifiants</th></tr>
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
            Nom
            <input required value={name} onChange={(e) => setName(e.target.value)} />
          </label>
          <label>
            NIF (facultatif)
            <input value={nif} onChange={(e) => setNif(e.target.value)} />
          </label>
          <div className="form-end">
            <button type="submit" className="btn-primary"><Icon name="plus" /> Ajouter</button>
          </div>
        </form>
      )}
      {message && <p role="status">{message}</p>}
      {error && <p role="alert" className="error">⚠ {error}</p>}
    </section>
  );
}

function Members() {
  const [members, setMembers] = useState<Member[]>([]);
  useEffect(() => {
    void api.members().then((p) => setMembers(p.results));
  }, []);

  return (
    <section className="card" aria-labelledby="members-title">
      <h2 id="members-title" className="card-title">Utilisateurs de la société</h2>
      <p className="muted small">Un compte n'est jamais supprimé : il est désactivé et son historique reste attribué.</p>
      <div className="table-wrap">
        <table className="data">
          <thead>
            <tr><th scope="col">Utilisateur</th><th scope="col">Rôles</th><th scope="col">État</th></tr>
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
                <td>{m.roles.map((r) => ROLE_LABELS[r]).join(", ")}</td>
                <td>{m.active ? <Chip tone="green">Actif</Chip> : <Chip tone="gray">Désactivé</Chip>}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}
