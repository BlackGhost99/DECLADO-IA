import { useEffect, useState, type FormEvent } from "react";
import { api, type CaseSummary, type Importer, type Me, type Membership } from "./api";
import { CaseDetailView } from "./CaseDetail";
import { errorText, type EditionOption } from "./ui";
import { useI18n } from "./i18n";

export function Cases({ membership, me }: { membership: Membership; me: Pick<Me, "id"> }) {
  const { t, locale } = useI18n();
  const canEdit = membership.roles.some((r) => r === "declarant" || r === "validator");
  const [cases, setCases] = useState<CaseSummary[]>([]);
  const [states, setStates] = useState<[string, string][]>([]);
  const [importers, setImporters] = useState<Importer[]>([]);
  const [editions, setEditions] = useState<EditionOption[]>([]);
  const [filters, setFilters] = useState({ state: "", assigned_to: "", importer: "", q: "" });
  const [openId, setOpenId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function load() {
    try {
      const page = await api.cases(filters);
      setCases(page.results);
      setStates(page.states);
    } catch (err) {
      setError(errorText(err, "Chargement impossible."));
    }
  }

  useEffect(() => {
    api.importers().then((p) => setImporters(p.results), () => setImporters([]));
    api.editions().then(
      (list) => setEditions(list.filter((e) => e.publication_state !== "withdrawn")),
      () => setEditions([]),
    );
  }, []);

  useEffect(() => {
    void load();
  }, [filters]);

  if (openId) {
    return (
      <CaseDetailView
        caseId={openId}
        me={me}
        membership={membership}
        editions={editions}
        onBack={() => {
          setOpenId(null);
          void load();
        }}
      />
    );
  }

  return (
    <>
      <section className="card" aria-labelledby="cases-title">
        <h2 id="cases-title">{t("cases")}</h2>
        <form className="row" role="search" onSubmit={(e) => e.preventDefault()}>
          <label>
            {t("searchTitle")}
            <input value={filters.q} onChange={(e) => setFilters({ ...filters, q: e.target.value })} />
          </label>
          <label>
            {t("status")}
            <select value={filters.state} onChange={(e) => setFilters({ ...filters, state: e.target.value })}>
              <option value="">{t("all")}</option>
              {states.map(([value, label]) => (
                <option key={value} value={value}>{label}</option>
              ))}
            </select>
          </label>
          <label>
            {t("agent")}
            <select value={filters.assigned_to} onChange={(e) => setFilters({ ...filters, assigned_to: e.target.value })}>
              <option value="">{t("all")}</option>
              <option value={me.id}>{t("me")}</option>
              <option value="none">{t("unassigned")}</option>
            </select>
          </label>
          <label>
            {t("importers")}
            <select value={filters.importer} onChange={(e) => setFilters({ ...filters, importer: e.target.value })}>
              <option value="">{t("all")}</option>
              {importers.map((i) => (
                <option key={i.id} value={i.id}>{i.name}</option>
              ))}
            </select>
          </label>
        </form>
        {error && <p role="alert" className="error">⚠ {error}</p>}
        {cases.length === 0 ? (
          <p className="muted">{t("noCases")}</p>
        ) : (
          <table>
            <thead>
              <tr>
                <th scope="col">{t("referenceCol")}</th><th scope="col">{t("title")}</th><th scope="col">{t("importers")}</th>
                <th scope="col">{t("agent")}</th><th scope="col">{t("status")}</th><th scope="col">{t("createdOn")}</th>
              </tr>
            </thead>
            <tbody>
              {cases.map((c) => (
                <tr key={c.id}>
                  <td>
                    <button type="button" className="link code" onClick={() => setOpenId(c.id)}>{c.reference}</button>
                  </td>
                  <td>{c.title}</td>
                  <td>{c.importer?.name ?? <em className="muted">{t("notProvided")}</em>}</td>
                  <td>{c.assigned_to?.email ?? <span className="muted">—</span>}</td>
                  <td>{c.state_label}</td>
                  <td>{new Date(c.created_at).toLocaleDateString(locale)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </section>
      {canEdit && <NewCase importers={importers} editions={editions} onCreated={(id) => setOpenId(id)} />}
    </>
  );
}

function NewCase({
  importers,
  editions,
  onCreated,
}: {
  importers: Importer[];
  editions: EditionOption[];
  onCreated: (id: string) => void;
}) {
  const { t } = useI18n();
  const [form, setForm] = useState({ title: "", importer_id: "", target_edition_id: "", planned_declaration_date: "", regime: "" });
  const [error, setError] = useState<string | null>(null);

  async function submit(event: FormEvent) {
    event.preventDefault();
    setError(null);
    try {
      const data = Object.fromEntries(Object.entries(form).filter(([, v]) => v));
      onCreated((await api.createCase(data)).id);
    } catch (err) {
      setError(errorText(err, "Création impossible."));
    }
  }

  return (
    <section className="card" aria-labelledby="new-case-title">
      <h2 id="new-case-title">{t("newCase")}</h2>
      <p className="muted small">{t("draftInfo")}</p>
      <form className="row" onSubmit={submit}>
        <label>
          Titre
          <input value={form.title} onChange={(e) => setForm({ ...form, title: e.target.value })} />
        </label>
        <label>
          Importateur
          <select value={form.importer_id} onChange={(e) => setForm({ ...form, importer_id: e.target.value })}>
            <option value="">{t("later")}</option>
            {importers.map((i) => (
              <option key={i.id} value={i.id}>{i.name}</option>
            ))}
          </select>
        </label>
        <label>
          Édition du référentiel
          <select value={form.target_edition_id} onChange={(e) => setForm({ ...form, target_edition_id: e.target.value })}>
            <option value="">{t("later")}</option>
            {editions.map((e) => (
              <option key={e.id} value={e.id}>{e.label}</option>
            ))}
          </select>
        </label>
        <label>
          Date de déclaration prévue
          <input type="date" value={form.planned_declaration_date} onChange={(e) => setForm({ ...form, planned_declaration_date: e.target.value })} />
        </label>
        <label>
          Régime
          <input value={form.regime} onChange={(e) => setForm({ ...form, regime: e.target.value })} placeholder="ex. C100 (fictif)" />
        </label>
        <button type="submit">{t("createCase")}</button>
      </form>
      {error && <p role="alert" className="error">⚠ {error}</p>}
    </section>
  );
}
