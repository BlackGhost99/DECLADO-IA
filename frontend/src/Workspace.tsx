import { useEffect, useState, type FormEvent } from "react";
import { api, ApiError, ROLE_LABELS, type Importer, type Me, type Member, type Membership } from "./api";
import { Cases } from "./Cases";
import { DocumentPolicies } from "./DocumentPolicies";
import { Reference } from "./Reference";
import { useI18n } from "./i18n";

export function Workspace({ membership, me }: { membership: Membership; me: Pick<Me, "id"> }) {
  const { t } = useI18n();
  const canEdit = membership.roles.some((r) => r === "declarant" || r === "validator");
  const isAdmin = membership.roles.includes("org_admin");

  const [tab, setTab] = useState<"cases" | "reference" | "importers" | "documents">("cases");

  return (
    <>
      <p className="muted">
        {t("roles")} {membership.roles.map((r) => ROLE_LABELS[r]).join(", ") || t("none")}.
      </p>
      <div role="tablist" className="tabs">
        <button type="button" role="tab" aria-selected={tab === "cases"} onClick={() => setTab("cases")}>
          {t("cases")}
        </button>
        <button type="button" role="tab" aria-selected={tab === "reference"} onClick={() => setTab("reference")}>
          {t("reference")}
        </button>
        <button type="button" role="tab" aria-selected={tab === "documents"} onClick={() => setTab("documents")}>
          {t("documents")}
        </button>
        <button type="button" role="tab" aria-selected={tab === "importers"} onClick={() => setTab("importers")}>
          {t("importers")}
        </button>
      </div>
      {tab === "cases" ? (
        <Cases membership={membership} me={me} />
      ) : tab === "reference" ? (
        <Reference />
      ) : tab === "documents" ? (
        <DocumentPolicies isAdmin={isAdmin} />
      ) : (
        <>
          <Importers canEdit={canEdit} />
          {isAdmin && <Members />}
        </>
      )}
    </>
  );
}

function Importers({ canEdit }: { canEdit: boolean }) {
  const { t } = useI18n();
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
          : t("importerSaved"),
      );
      setName("");
      setNif("");
      await load();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : t("saveError"));
    }
  }

  return (
    <section className="card" aria-labelledby="importers-title">
      <h2 id="importers-title">{t("importers")}</h2>
      {items.length === 0 ? (
        <p className="muted">{t("importerNone")}</p>
      ) : (
        <table>
          <thead>
            <tr><th scope="col">{t("name")}</th><th scope="col">{t("identifiers")}</th></tr>
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
            {t("name")}
            <input required value={name} onChange={(e) => setName(e.target.value)} />
          </label>
          <label>
            {t("optionalTax")}
            <input value={nif} onChange={(e) => setNif(e.target.value)} />
          </label>
          <button type="submit">{t("add")}</button>
        </form>
      )}
      {message && <p role="status">{message}</p>}
      {error && <p role="alert" className="error">⚠ {error}</p>}
    </section>
  );
}

function Members() {
  const { t } = useI18n();
  const [members, setMembers] = useState<Member[]>([]);
  useEffect(() => {
    void api.members().then((p) => setMembers(p.results));
  }, []);

  return (
    <section className="card" aria-labelledby="members-title">
      <h2 id="members-title">{t("orgUsers")}</h2>
      <table>
        <thead>
          <tr><th scope="col">E-mail</th><th scope="col">{t("rolesHeader")}</th><th scope="col">{t("status")}</th></tr>
        </thead>
        <tbody>
          {members.map((m) => (
            <tr key={m.id}>
              <td>{m.email}</td>
              <td>{m.roles.map((r) => ROLE_LABELS[r]).join(", ")}</td>
              <td>{m.active ? t("active") : t("inactive")}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </section>
  );
}
