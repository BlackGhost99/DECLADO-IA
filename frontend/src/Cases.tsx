import { useEffect, useState, type ReactNode } from "react";
import { api, type CaseSummary, type Importer, type Me, type Membership } from "./api";
import { Icon } from "./Icon";
import { navigate } from "./router";
import { errorText, fmtDate, initials, PageHeader, personName, relativeTime, StateChip } from "./ui";
import { tr, useBusinessLabels, type MessageKey } from "./i18n";

export const canEditCases = (m: Membership) => m.roles.some((r) => r === "declarant" || r === "validator");

export function Cases({ membership, me, initialQuery = "" }: { membership: Membership; me: Pick<Me, "id">; initialQuery?: string }) {
  const labels = useBusinessLabels();
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
      (err) => setError(errorText(err, tr("cases.loadFailed"))),
    );
  }, [filters]);

  const shown = view === "archives" ? cases.filter((c) => c.state === "archived") : cases.filter((c) => c.assigned_to?.id === me.id);

  return (
    <>
      <PageHeader title={tr("nav.myCases")} subtitle={tr("cases.subtitle")}>
        {canEditCases(membership) && (
          <button type="button" className="btn-primary" onClick={() => navigate("/nouveau")}>
            <Icon name="plus" /> {tr("nav.newCase")}
          </button>
        )}
      </PageHeader>
      <div className="case-tabs-bar" role="tablist" aria-label={tr("cases.views")}>
        {VIEWS.map(([key, label, icon]) => (
          <button key={key} type="button" role="tab" aria-selected={view === key} className={view === key ? "active" : ""} onClick={() => setView(key)}>
            <Icon name={icon} size={18} /> {tr(label)}
          </button>
        ))}
      </div>

      {view === "team" && <TeamOverview cases={cases} />}

      <section className="card cases-filter-card" aria-labelledby="cases-title">
        <h2 id="cases-title" className="visually-hidden">{tr("cases")}</h2>
        <form className="filters" role="search" onSubmit={(e) => e.preventDefault()}>
          <label>
            {tr("searchTitle")}
            <input value={filters.q} onChange={(e) => setFilters({ ...filters, q: e.target.value })} />
          </label>
          <label>
            {tr("status")}
            <select value={filters.state} onChange={(e) => setFilters({ ...filters, state: e.target.value })}>
              <option value="">{tr("all")}</option>
              {states.map(([value, label]) => (
                <option key={value} value={value}>{labels.state(value, label)}</option>
              ))}
            </select>
          </label>
          <label>
            {tr("agent")}
            <select value={filters.assigned_to} onChange={(e) => setFilters({ ...filters, assigned_to: e.target.value })}>
              <option value="">{tr("all")}</option>
              <option value={me.id}>{tr("me")}</option>
              <option value="none">{tr("unassigned")}</option>
            </select>
          </label>
          <label>
            {tr("cases.importer")}
            <select value={filters.importer} onChange={(e) => setFilters({ ...filters, importer: e.target.value })}>
              <option value="">{tr("all")}</option>
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
          <p className="empty">{view === "mine" ? tr("cases.noneMine") : tr("cases.noneArchived")}</p>
        ) : (
          <CaseTable cases={shown} />
        )}
      </section>
    </>
  );
}

const VIEWS: ["mine" | "team" | "archives", MessageKey, "file" | "users" | "archive"][] = [
  ["mine", "nav.myCases", "file"],
  ["team", "cases.teamView", "users"],
  ["archives", "cases.archives", "archive"],
];

/** Une colonne par état réel du dossier : aucune étape n'est déduite. */
const BOARD_COLUMNS: { state: string; label: MessageKey; tone: string }[] = [
  { state: "draft", label: "board.draft", tone: "gray" },
  { state: "in_preparation", label: "board.preparing", tone: "blue" },
  { state: "to_correct", label: "board.toCorrect", tone: "red" },
  { state: "to_validate", label: "board.toValidate", tone: "amber" },
  { state: "validated", label: "board.validated", tone: "green" },
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
        <StatMini icon="folder" tone="green" label={tr("board.inProgress")} value={open.length} />
        <StatMini icon="alert" tone="red" label={tr("board.toCorrect")} value={open.filter((c) => c.state === "to_correct").length} />
        <StatMini icon="checkCircle" tone="green" label={tr("board.validated")} value={open.filter((c) => c.state === "validated").length} />
      </div>
      <aside className="card team-load-card" aria-labelledby="team-load-title">
        <div className="card-head">
          <h2 id="team-load-title" className="card-title">{tr("board.teamLoad")}</h2>
          <span className="muted small">{tr("dash.unassigned", { n: unassigned })}</span>
        </div>
        {people.size === 0 ? (
          <p className="empty">{tr("board.noneAssigned")}</p>
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
    <div className="kanban" aria-label={tr("board.byState")}>
      {BOARD_COLUMNS.map((column) => {
        const rows = cases.filter((c) => c.state === column.state);
        return (
          <section key={column.state} className={`kanban-column kanban-${column.tone}`} aria-label={tr(column.label)}>
            <header className="kanban-head">
              <span>{tr(column.label)}</span>
              <span className="count-badge">{rows.length}</span>
            </header>
            <div className="kanban-list">
              {rows.length === 0 ? (
                <div className="kanban-empty">{tr("board.noCase")}</div>
              ) : (
                rows.map((c) => (
                  <button type="button" key={c.id} className="kanban-card" onClick={() => navigate(`/dossiers/${c.id}`)}>
                    <strong className="code">{c.reference}</strong>
                    <span className="kanban-importer">{c.importer?.name ?? c.title ?? capitalize(tr("case.importerToFill"))}</span>
                    <small>{modeShort(c.mode)}</small>
                    <span className="kanban-meta">
                      <span className="person">
                        <span className="avatar small-avatar">{personName(c.assigned_to) ? initials(personName(c.assigned_to)) : "?"}</span>
                        <small>{personName(c.assigned_to) || tr("board.unassignedOne")}</small>
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

const MODE_SHORT: Record<string, MessageKey> = { demo: "modeDemo", historical: "mode.simulation", operational: "modeOperational" };
const modeShort = (mode: string) => (MODE_SHORT[mode] ? tr(MODE_SHORT[mode]) : mode);
const capitalize = (text: string) => text.charAt(0).toUpperCase() + text.slice(1);

export function CaseTable({ cases, progress }: { cases: CaseSummary[]; progress?: Record<string, ReactNode> }) {
  return (
    <div className="table-wrap">
      <table className={`data${progress ? " case-table-compact" : ""}`}>
        <thead>
          <tr>
            <th scope="col">{tr("cases.caseNo")}</th>
            <th scope="col">{tr("cases.importerTitle")}</th>
            {!progress && <th scope="col">{tr("cases.type")}</th>}
            {progress && <th scope="col">{tr("cases.progress")}</th>}
            <th scope="col">{tr("agent")}</th>
            <th scope="col">{tr("cases.statusCol")}</th>
            <th scope="col">{tr("cases.created")}</th>
            <th scope="col"><span className="visually-hidden">{tr("cases.open")}</span></th>
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
                {c.importer?.name ?? <em className="muted">{tr("case.importerToFill")}</em>}
                {c.title && !progress && <div className="muted small">{c.title}</div>}
              </td>
              {!progress && <td>{modeShort(c.mode)}</td>}
              {progress && <td>{progress[c.id] ?? <span className="muted">…</span>}</td>}
              <td className="agent-cell" title={personName(c.assigned_to) || undefined}>
                {personName(c.assigned_to) ? (
                  progress ? <span className="avatar small-avatar">{initials(personName(c.assigned_to))}</span> : personName(c.assigned_to)
                ) : (
                  <span className="muted">{tr("case.unassigned")}</span>
                )}
              </td>
              <td>
                <StateChip state={c.state} label={c.state_label} />
              </td>
              <td title={fmtDate(c.created_at)} className="nowrap muted">{relativeTime(c.created_at)}</td>
              <td>
                <button type="button" className="icon-button" onClick={() => navigate(`/dossiers/${c.id}`)} title={tr("cases.openRef", { ref: c.reference })}>
                  <Icon name="chevronRight" size={18} />
                  <span className="visually-hidden">{tr("cases.openRef", { ref: c.reference })}</span>
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
const TAB_TITLES: Record<string, MessageKey> = {
  documents: "tab.documents",
  marchandises: "tab.goods",
  calculs: "tab.calculations",
  controles: "tab.controls",
  validation: "tab.validation",
  export: "tab.export",
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
      <PageHeader title={TAB_TITLES[tab] ? tr(TAB_TITLES[tab]) : tab} subtitle={tr("cases.pick")} />
      <section className="card">
        {cases === null ? (
          <p className="muted">{tr("loading")}</p>
        ) : cases.length === 0 ? (
          <p className="empty">
            {tr("cases.noneMine")}{" "}
            <button type="button" className="link" onClick={() => navigate("/dossiers")}>{tr("dash.seeAllCases")}</button>
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
