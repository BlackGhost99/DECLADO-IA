import { useEffect, useState, type FormEvent, type ReactNode } from "react";
import { api, ApiError, type CaseSummary, type Importer, type Me, type Membership } from "./api";
import { Icon } from "./Icon";
import { navigate } from "./router";
import { errorText, fmtDate, initials, PageHeader, personName, relativeTime, StateChip, type EditionOption } from "./ui";

export const canEditCases = (m: Membership) => m.roles.some((r) => r === "declarant" || r === "validator");

export function Cases({ membership, me, initialQuery = "" }: { membership: Membership; me: Pick<Me, "id">; initialQuery?: string }) {
  const [cases, setCases] = useState<CaseSummary[]>([]);
  const [states, setStates] = useState<[string, string][]>([]);
  const [importers, setImporters] = useState<Importer[]>([]);
  const [filters, setFilters] = useState({ state: "", assigned_to: "", importer: "", q: initialQuery });
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api.importers().then((p) => setImporters(p.results), () => setImporters([]));
  }, []);

  useEffect(() => {
    setFilters((f) => ({ ...f, q: initialQuery }));
  }, [initialQuery]);

  useEffect(() => {
    api.cases(filters).then(
      (page) => {
        setCases(page.results);
        setStates(page.states);
      },
      (err) => setError(errorText(err, "Chargement impossible.")),
    );
  }, [filters]);

  return (
    <>
      <PageHeader title="Mes dossiers" subtitle="Retrouvez les dossiers de votre société, leur état et leur agent.">
        {canEditCases(membership) && (
          <button type="button" className="btn-primary" onClick={() => navigate("/nouveau")}>
            <Icon name="plus" /> Nouveau dossier
          </button>
        )}
      </PageHeader>
      <section className="card" aria-labelledby="cases-title">
        <h2 id="cases-title" className="visually-hidden">Dossiers</h2>
        <form className="filters" role="search" onSubmit={(e) => e.preventDefault()}>
          <label>
            Référence ou titre
            <input value={filters.q} onChange={(e) => setFilters({ ...filters, q: e.target.value })} />
          </label>
          <label>
            État
            <select value={filters.state} onChange={(e) => setFilters({ ...filters, state: e.target.value })}>
              <option value="">Tous</option>
              {states.map(([value, label]) => (
                <option key={value} value={value}>{label}</option>
              ))}
            </select>
          </label>
          <label>
            Agent
            <select value={filters.assigned_to} onChange={(e) => setFilters({ ...filters, assigned_to: e.target.value })}>
              <option value="">Tous</option>
              <option value={me.id}>Moi</option>
              <option value="none">Non affectés</option>
            </select>
          </label>
          <label>
            Importateur
            <select value={filters.importer} onChange={(e) => setFilters({ ...filters, importer: e.target.value })}>
              <option value="">Tous</option>
              {importers.map((i) => (
                <option key={i.id} value={i.id}>{i.name}</option>
              ))}
            </select>
          </label>
        </form>
        {error && <p role="alert" className="error">⚠ {error}</p>}
        {cases.length === 0 ? (
          <p className="empty">Aucun dossier.</p>
        ) : (
          <CaseTable cases={cases} />
        )}
      </section>
    </>
  );
}

const MODE_SHORT: Record<string, string> = { demo: "Démonstration", historical: "Simulation", operational: "Opérationnel" };

export function CaseTable({ cases, progress }: { cases: CaseSummary[]; progress?: Record<string, ReactNode> }) {
  return (
    <div className="table-wrap">
      <table className={`data${progress ? " case-table-compact" : ""}`}>
        <thead>
          <tr>
            <th scope="col">N° dossier</th>
            <th scope="col">Importateur / titre</th>
            {!progress && <th scope="col">Type</th>}
            {progress && <th scope="col">Progression</th>}
            <th scope="col">Agent</th>
            <th scope="col">Statut</th>
            <th scope="col">Créé</th>
            <th scope="col"><span className="visually-hidden">Ouvrir</span></th>
          </tr>
        </thead>
        <tbody>
          {cases.map((c) => (
            <tr key={c.id}>
              <td>
                <button type="button" className="link code" onClick={() => navigate(`/dossiers/${c.id}`)}>
                  {c.reference}
                </button>
              </td>
              <td className="importer-cell" title={c.title || undefined}>
                {c.importer?.name ?? <em className="muted">importateur à renseigner</em>}
                {c.title && !progress && <div className="muted small">{c.title}</div>}
              </td>
              {!progress && <td>{MODE_SHORT[c.mode] ?? c.mode}</td>}
              {progress && <td>{progress[c.id] ?? <span className="muted">…</span>}</td>}
              <td className="agent-cell" title={personName(c.assigned_to) || undefined}>
                {personName(c.assigned_to) ? (
                  progress ? <span className="avatar small-avatar">{initials(personName(c.assigned_to))}</span> : personName(c.assigned_to)
                ) : (
                  <span className="muted">non affecté</span>
                )}
              </td>
              <td>
                <StateChip state={c.state} label={c.state_label} />
              </td>
              <td title={fmtDate(c.created_at)} className="nowrap muted">{relativeTime(c.created_at)}</td>
              <td>
                <button type="button" className="icon-button" onClick={() => navigate(`/dossiers/${c.id}`)} title={`Ouvrir ${c.reference}`}>
                  <Icon name="chevronRight" size={18} />
                  <span className="visually-hidden">Ouvrir {c.reference}</span>
                </button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

/**
 * Nouveau dossier : on dépose la facture, le dossier est créé et la lecture démarre aussitôt.
 * Tout le reste (importateur, édition, régime) peut attendre : les manques sont listés dans le dossier.
 */
export function NewCasePage({ membership }: { membership: Membership }) {
  const [importers, setImporters] = useState<Importer[]>([]);
  const [editions, setEditions] = useState<EditionOption[]>([]);
  const [form, setForm] = useState({ title: "", importer_id: "", target_edition_id: "", planned_declaration_date: "", regime: "" });
  const [file, setFile] = useState<File | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api.importers().then((p) => setImporters(p.results), () => setImporters([]));
    api.editions().then(
      (list) => {
        const usable = list.filter((e) => e.publication_state !== "withdrawn");
        setEditions(usable);
        // Le tarif en service est choisi par défaut ; il reste modifiable dans le dossier.
        const preferred = usable.find((e) => e.publication_state === "operational") ?? usable[0];
        if (preferred) setForm((f) => (f.target_edition_id ? f : { ...f, target_edition_id: preferred.id }));
      },
      () => setEditions([]),
    );
  }, []);

  if (!canEditCases(membership)) {
    return <p className="empty">Votre rôle ne permet pas de créer un dossier.</p>;
  }

  async function submit(event: FormEvent) {
    event.preventDefault();
    setError(null);
    try {
      setBusy("Création du dossier…");
      const data = Object.fromEntries(Object.entries(form).filter(([, v]) => v));
      const created = await api.createCase(data);
      if (!file) {
        navigate(`/dossiers/${created.id}/documents`);
        return;
      }
      setBusy("Envoi de la facture…");
      let link;
      try {
        link = await api.uploadDocument(created.id, file, "invoice", "", crypto.randomUUID());
      } catch (err) {
        if (!(err instanceof ApiError && err.code === "DUPLICATE_DOCUMENT")) throw err;
        // Fichier déjà connu de la société : on rattache la pièce existante, sans nouveau dépôt.
        const existing = (err.details.existing as { id: string }[] | undefined)?.[0];
        if (!existing) throw err;
        link = await api.reuseDocument(created.id, existing.id, "invoice");
      }
      if (link.document.readability === "ok") {
        setBusy("Lancement de la lecture…");
        await api.extract(link.id, { ocr: link.document.mime.startsWith("image/") }).catch(() => undefined);
      }
      navigate(`/dossiers/${created.id}/documents`);
    } catch (err) {
      setError(errorText(err, "Création impossible."));
      setBusy(null);
    }
  }

  const selectedImporter = importers.find((i) => i.id === form.importer_id) ?? null;
  const selectedEdition = editions.find((e) => e.id === form.target_edition_id) ?? null;
  const importerNif = selectedImporter?.identifiers?.nif ?? selectedImporter?.identifiers?.NIF ?? "—";

  return (
    <>
      <nav className="breadcrumb" aria-label="Fil d’Ariane">
        <button type="button" className="link" onClick={() => navigate("/dossiers")}>
          Mes dossiers
        </button>
        <Icon name="chevronRight" size={14} />
        <span>Nouveau dossier</span>
      </nav>
      <PageHeader
        title="Nouveau dossier"
        subtitle="Créez un nouveau dossier d’importation avec l’assistance de ClairTransit."
      />
      <form className="new-case-shell" onSubmit={submit} aria-labelledby="new-case-title">
        <h2 id="new-case-title" className="visually-hidden">Nouveau dossier</h2>

        <div className="new-case-main">
          <ol className="new-case-steps" aria-label="Étapes de création du dossier">
            <li className="active">
              <span className="new-case-step-dot">1</span>
              <strong>Informations du client</strong>
            </li>
            <li>
              <span className="new-case-step-dot">2</span>
              <strong>Type d’importation</strong>
            </li>
            <li>
              <span className="new-case-step-dot">3</span>
              <strong>Documents initiaux</strong>
            </li>
            <li>
              <span className="new-case-step-dot">4</span>
              <strong>Confirmation</strong>
            </li>
          </ol>

          <section className="card new-case-card">
            <div className="new-case-section-head">
              <div>
                <h2>1. Informations du client</h2>
                <p>Renseignez les informations disponibles. Les éléments manquants pourront être complétés dans le dossier.</p>
              </div>
            </div>
            <div className="form-grid new-case-form-grid">
              <label>
                Importateur / Client
                <select value={form.importer_id} onChange={(e) => setForm({ ...form, importer_id: e.target.value })}>
                  <option value="">À renseigner plus tard</option>
                  {importers.map((i) => (
                    <option key={i.id} value={i.id}>{i.name}</option>
                  ))}
                </select>
                {selectedImporter && (
                  <span className="input-help">
                    NIF : {importerNif}
                  </span>
                )}
              </label>
              <label>
                Titre du dossier
                <input value={form.title} onChange={(e) => setForm({ ...form, title: e.target.value })} placeholder="ex. Générateurs avril" />
              </label>
              <label>
                Type d’opération
                <input value="Importation" readOnly aria-readonly="true" />
              </label>
              <label>
                Territoire
                <input value="Gabon" readOnly aria-readonly="true" />
              </label>
              <label>
                Date de déclaration prévue
                <input type="date" value={form.planned_declaration_date} onChange={(e) => setForm({ ...form, planned_declaration_date: e.target.value })} />
              </label>
              <label>
                Tarif utilisé
                <select value={form.target_edition_id} onChange={(e) => setForm({ ...form, target_edition_id: e.target.value })}>
                  <option value="">À choisir plus tard</option>
                  {editions.map((e) => (
                    <option key={e.id} value={e.id}>{e.label}</option>
                  ))}
                </select>
              </label>
            </div>
          </section>

          <section className="card new-case-card">
            <div className="new-case-section-head">
              <div>
                <h2>3. Documents initiaux</h2>
                <p>Ajoutez la facture principale pour lancer la lecture du dossier.</p>
              </div>
              <span className="chip chip-green">{file ? "1 fichier" : "0 fichier"}</span>
            </div>
            <label className={`dropzone new-case-dropzone${file ? " has-file" : ""}`}>
              <span className="dropzone-icon"><Icon name="upload" size={30} /></span>
              <strong>{file ? file.name : "Glissez-déposez votre facture ici"}</strong>
              <span className="muted">ou cliquez pour parcourir vos fichiers</span>
              <small>PDF, JPG, PNG, Excel · la pièce peut aussi être ajoutée après création</small>
              <input
                type="file"
                accept=".pdf,.png,.jpg,.jpeg,.xlsx"
                aria-label="Facture"
                onChange={(e) => setFile(e.target.files?.[0] ?? null)}
              />
            </label>
          </section>

          {error && <p role="alert" className="error">⚠ {error}</p>}
        </div>

        <aside className="new-case-side" aria-label="Résumé du dossier">
          <section className="card new-case-summary-card">
            <div className="card-head">
              <h2 className="card-title">Résumé du dossier</h2>
              <span className="chip chip-green">Brouillon</span>
            </div>
            <dl className="summary-list">
              <div><dt>Importateur / Client</dt><dd>{selectedImporter?.name ?? "À renseigner"}</dd></div>
              <div><dt>NIF / Référence</dt><dd>{importerNif}</dd></div>
              <div><dt>Type d’opération</dt><dd>Importation</dd></div>
              <div><dt>Territoire</dt><dd><span className="flag-inline"><span className="flag-ga" /> Gabon</span></dd></div>
              <div><dt>Date prévue</dt><dd>{form.planned_declaration_date || "À renseigner"}</dd></div>
              <div><dt>Tarif</dt><dd>{selectedEdition?.label ?? "À choisir"}</dd></div>
            </dl>
          </section>

          <section className="card new-case-summary-card">
            <div className="card-head">
              <h2 className="card-title">Documents initiaux</h2>
              <span className="chip chip-green">{file ? "1 fichier" : "0 fichier"}</span>
            </div>
            {file ? (
              <div className="new-case-file-row">
                <span className="doc-type doc-pdf">DOC</span>
                <span>
                  <strong>{file.name}</strong>
                  <small>Facture commerciale</small>
                </span>
                <Icon name="checkCircle" size={18} />
              </div>
            ) : (
              <p className="note-blue small">Vous pourrez ajouter les autres documents après la création du dossier.</p>
            )}
          </section>

          <div className="new-case-actions">
            <button type="button" className="btn-secondary" onClick={() => navigate("/dossiers")}>Annuler</button>
            <button type="submit" className="btn-primary" disabled={busy !== null}>
              {busy ?? (file ? "Créer et lire la facture" : "Créer le dossier")}
              {!busy && <Icon name="arrowRight" />}
            </button>
          </div>
        </aside>
      </form>
    </>

const TAB_TITLES: Record<string, string> = {
  documents: "Documents",
  marchandises: "Marchandises",
  calculs: "Calculs",
  controles: "Contrôles",
  validation: "Validation",
  export: "Export",
};

/** Entrée de la barre latérale sans dossier ouvert : on choisit d'abord le dossier. */
export function CasePicker({ tab, me }: { tab: string; me: Pick<Me, "id"> }) {
  const [cases, setCases] = useState<CaseSummary[] | null>(null);
  useEffect(() => {
    api.cases({ assigned_to: me.id }).then(
      (p) => setCases(p.results),
      () => setCases([]),
    );
  }, [me.id]);
  return (
    <>
      <PageHeader title={TAB_TITLES[tab] ?? tab} subtitle="Choisissez le dossier à ouvrir." />
      <section className="card">
        {cases === null ? (
          <p className="muted">Chargement…</p>
        ) : cases.length === 0 ? (
          <p className="empty">
            Aucun dossier ne vous est affecté.{" "}
            <button type="button" className="link" onClick={() => navigate("/dossiers")}>Voir tous les dossiers</button>
          </p>
        ) : (
          <ul className="picker">
            {cases.map((c) => (
              <li key={c.id}>
                <button type="button" onClick={() => navigate(`/dossiers/${c.id}/${tab}`)}>
                  <span className="code">{c.reference}</span>
                  <span>{c.importer?.name ?? c.title}</span>
                  <StateChip state={c.state} label={c.state_label} />
                  <Icon name="chevronRight" />
                </button>
              </li>
            ))}
          </ul>
        )}
      </section>
    </>
  );
}
