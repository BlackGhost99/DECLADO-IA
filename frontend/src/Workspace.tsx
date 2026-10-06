import { useEffect, useState, type FormEvent } from "react";
import { api, ApiError, ROLE_LABELS, type Importer, type Member, type Membership } from "./api";

export function Workspace({ membership }: { membership: Membership }) {
  const canEdit = membership.roles.some((r) => r === "declarant" || r === "validator");
  const isAdmin = membership.roles.includes("org_admin");

  return (
    <>
      <p className="muted">
        Vos rôles : {membership.roles.map((r) => ROLE_LABELS[r]).join(", ") || "aucun"}.
        Les dossiers douaniers arrivent au lot 2 ; ce socle montre l'isolation des données par société.
      </p>
      <Importers canEdit={canEdit} />
      {isAdmin && <Members />}
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
      <h2 id="importers-title">Importateurs</h2>
      {items.length === 0 ? (
        <p className="muted">Aucun importateur pour cette société.</p>
      ) : (
        <table>
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
      )}
      {canEdit && (
        <form className="row" onSubmit={create}>
          <label>
            Nom
            <input required value={name} onChange={(e) => setName(e.target.value)} />
          </label>
          <label>
            NIF (facultatif)
            <input value={nif} onChange={(e) => setNif(e.target.value)} />
          </label>
          <button type="submit">Ajouter</button>
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
      <h2 id="members-title">Utilisateurs de la société</h2>
      <table>
        <thead>
          <tr><th scope="col">E-mail</th><th scope="col">Rôles</th><th scope="col">État</th></tr>
        </thead>
        <tbody>
          {members.map((m) => (
            <tr key={m.id}>
              <td>{m.email}</td>
              <td>{m.roles.map((r) => ROLE_LABELS[r]).join(", ")}</td>
              <td>{m.active ? "Actif" : "Désactivé"}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </section>
  );
}
