import { useEffect, useState, type ReactNode } from "react";
import { api, type CaseSummary, type Importer, type Me, type Membership } from "./api";
import { Icon } from "./Icon";
import { navigate } from "./router";
import { errorText, fmtDate, initials, PageHeader, personName, relativeTime, StateChip } from "./ui";

export const canEditCases = (m: Membership) => m.roles.some((r) => r === "declarant" || r === "validator");

export function Cases({ membership, me, initialQuery = "" }: { membership: Membership; me: Pick<Me, "id">; initialQuery?: string }) {
  const [cases, setCases] = useState<CaseSummary[]>([]);
  const [states, setStates] = useState<[string, string][]>([]);
  const [importers, setImporters] = useState<Importer[]>([]);
  const [filters, setFilters] = useState({ state: "", assigned_to: "", importer: "", q: initialQuery });
  const [view, setView] = useState<"mine" | "team" | "archives">("team");
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

  const shown = view === "archives" ? cases.filter((c) => c.state === "archived") : cases.filter((c) => c.assigned_to?.id === me.id);

  return (
    <>
      <PageHeader title="Mes dossiers" subtitle="Suivez l'avancement des dossiers de votre équipe.">
        {canEditCases(membership) && (
          <button type="button" className="btn-primary" onClick={() => navigate("/nouveau")}>
            <Icon name="plus" /> Nouveau dossier
          </button>
        )}
      </PageHeader>
      <div className="case-tabs-bar" role="tablist" aria-label="Vues des dossiers">
        {VIEWS.map(([key, label, icon]) => (
          <button key={key} type="button" role="tab" aria-selected={view === key} className={view === key ? "active" : ""} onClick={() => setView(key)}>
            <Icon name={icon} size={18} /> {label}
          </button>
        ))}
      </div>

      {view === "team" && <TeamOverview cases={cases} />}

      <section className="card cases-filter-card" aria-labelledby="cases-title">
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
        {view === "team" ? (
          <CasesKanban cases={cases.filter((c) => c.state !== "archived")} />
        ) : shown.length === 0 ? (
          <p className="empty">{view === "mine" ? "Aucun dossier ne vous est affecté." : "Aucun dossier archivé."}</p>
        ) : (
          <CaseTable cases={shown} />
        )}
      </section>
    </>
  );
}

const VIEWS: ["mine" | "team" | "archives", string, "file" | "users" | "archive"][] = [
  ["mine", "Mes dossiers", "file"],
  ["team", "Vue équipe", "users"],
  ["archives", "Archives", "archive"],
];

/** Une colonne par état réel du dossier : aucune étape n'est déduite. */
const BOARD_COLUMNS: { state: string; label: string; tone: string }[] = [
  { state: "draft", label: "Brouillons", tone: "gray" },
  { state: "in_preparation", label: "En préparation", tone: "blue" },
  { state: "to_correct", label: "À corriger", tone: "red" },
  { state: "to_validate", label: "À valider", tone: "amber" },
  { state: "validated", label: "Validés en interne", tone: "green" },
];

function TeamOverview({ cases }: { cases: CaseSummary[] }) {
  const open = cases.filter((c) => c.state !== "archived");
  const people = new Map<string, number>();
  for (const c of open) {
    const name = personName(c.assigned_to);
    if (name) people.set(name, (people.get(name) ?? 0) + 1);
  }
  const unassigned = open.filter((c) => !c.assigned_to).length;
  const max = Math.max(1, ...people.values());
  return (
    <div className="team-overview">
      <div className="stats stats-3 team-kpis">
        <StatMini icon="folder" tone="green" label="Dossiers en cours" value={open.length} />
        <StatMini icon="alert" tone="red" label="À corriger" value={open.filter((c) => c.state === "to_correct").length} />
        <StatMini icon="checkCircle" tone="green" label="Validés en interne" value={open.filter((c) => c.state === "validated").length} />
      </div>
      <aside className="card team-load-card" aria-labelledby="team-load-title">
        <div className="card-head">
          <h2 id="team-load-title" className="card-title">Charge de l'équipe</h2>
          <span className="muted small">{unassigned} non affecté(s)</span>
        </div>
        {people.size === 0 ? (
          <p className="empty">Aucun dossier affecté.</p>
        ) : (
          <ul className="team-load">
            {[...people.entries()].sort((a, b) => b[1] - a[1]).map(([name, count]) => (
              <li key={name}>
                <span className="avatar small-avatar">{initials(name)}</span>
                <span className="team-person">
                  <strong>{name}</strong>
                  <span className="load-track"><span className="load-fill" style={{ width: `${Math.round((count / max) * 100)}%` }} /></span>
                </span>
                <strong className="load-count">{count}</strong>
              </li>
            ))}
          </ul>
        )}
      </aside>
    </div>
  );
}

function StatMini({ icon, tone, label, value }: { icon: "folder" | "alert" | "checkCircle"; tone: "green" | "red"; label: string; value: number }) {
  return (
    <div className="stat">
      <span className={`stat-icon tone-${tone}`}><Icon name={icon} size={22} /></span>
      <div>
        <div className="stat-label">{label}</div>
        <div className="stat-value">{value}</div>
      </div>
    </div>
  );
}

function CasesKanban({ cases }: { cases: CaseSummary[] }) {
  return (
    <div className="kanban" aria-label="Dossiers par état">
      {BOARD_COLUMNS.map((column) => {
        const rows = cases.filter((c) => c.state === column.state);
        return (
          <section key={column.state} className={`kanban-column kanban-${column.tone}`} aria-label={column.label}>
            <header className="kanban-head">
              <span>{column.label}</span>
              <span className="count-badge">{rows.length}</span>
            </header>
            <div className="kanban-list">
              {rows.length === 0 ? (
                <div className="kanban-empty">Aucun dossier</div>
              ) : (
                rows.map((c) => (
                  <button type="button" key={c.id} className="kanban-card" onClick={() => navigate(`/dossiers/${c.id}`)}>
                    <strong className="code">{c.reference}</strong>
                    <span className="kanban-importer">{c.importer?.name ?? c.title ?? "Importateur à renseigner"}</span>
                    <small>{MODE_SHORT[c.mode] ?? c.mode}</small>
                    <span className="kanban-meta">
                      <span className="person">
                        <span className="avatar small-avatar">{personName(c.assigned_to) ? initials(personName(c.assigned_to)) : "?"}</span>
                        <small>{personName(c.assigned_to) || "Non affecté"}</small>
                      </span>
                      <small>{relativeTime(c.created_at)}</small>
                    </span>
                  </button>
                ))
              )}
            </div>
          </section>
        );
      })}
    </div>
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
