import { useEffect, useState, type ReactNode } from "react";
import {
  api,
  type CaseDetail,
  type CaseSummary,
  type Me,
  type Membership,
  type OrganizationOverview,
  type OrgAuditEvent,
} from "./api";
import portHero from "./assets/port-hero.png";
import { controlItems } from "./Controls";
import { Icon, type IconName } from "./Icon";
import { tr } from "./i18n";
import { navigate } from "./router";
import {
  caseSteps,
  eventIcon,
  eventLabel,
  personName,
  progressOf,
  relativeTime,
  StateChip,
  Stepper,
  type Step,
} from "./ui";

const RECENT = 6;

/** « Validateur Alpha » → « V. Alpha », comme dans les tableaux de suivi. */
export function shortName(full: string): string {
  const words = full.trim().split(/\s+/);
  return words.length > 1 ? `${words[0][0]}. ${words.slice(1).join(" ")}` : full;
}

const capitalize = (text: string) => text.charAt(0).toUpperCase() + text.slice(1);

/** Variation en pourcentage, seulement quand la période de comparaison existe. */
function trend(now: number, before: number): { text: string; dir: "up" | "down" | "flat" } | null {
  if (!before) return null;
  const pct = Math.round(((now - before) / before) * 100);
  return { text: `${pct > 0 ? "+" : ""}${pct}%`, dir: pct > 0 ? "up" : pct < 0 ? "down" : "flat" };
}

function Kpi({
  icon,
  tone,
  label,
  value,
  delta,
  note,
}: {
  icon: IconName;
  tone: string;
  label: string;
  value: ReactNode;
  delta: ReturnType<typeof trend> | string;
  note: string;
}) {
  return (
    <div className="kpi">
      <span className={`kpi-icon kpi-${tone}`}><Icon name={icon} size={26} /></span>
      <div>
        <div className="kpi-label">{label}</div>
        <div className="kpi-value">{value}</div>
        {typeof delta === "string" ? (
          <div className="kpi-delta kpi-delta-flat">{delta}</div>
        ) : delta ? (
          <div className={`kpi-delta kpi-delta-${delta.dir}`}>
            <Icon name={delta.dir === "down" ? "arrowDownRight" : "arrowUpRight"} size={14} /> {delta.text}
          </div>
        ) : (
          <div className="kpi-delta kpi-delta-flat">—</div>
        )}
        <div className="kpi-note">{note}</div>
      </div>
    </div>
  );
}

const DASH_STEPS = (): Omit<Step, "state">[] => [
  { key: "documents", label: tr("step.documents"), detail: tr("dash.receivedHint") },
  { key: "donnees", label: tr("step.extraction"), detail: tr("dash.readPdf") },
  { key: "marchandises", label: tr("step.classification"), detail: tr("dash.hsCode") },
  { key: "calculs", label: tr("step.calculation"), detail: tr("dash.dutiesTaxes") },
  { key: "validation", label: tr("step.validation"), detail: tr("dash.checks") },
  { key: "export", label: tr("step.export"), detail: tr("dash.finalCase") },
];

export function Dashboard({ membership, me }: { membership: Membership; me: Pick<Me, "id" | "full_name" | "email"> }) {
  const [cases, setCases] = useState<CaseSummary[] | null>(null);
  const [details, setDetails] = useState<Record<string, CaseDetail>>({});
  const [events, setEvents] = useState<OrgAuditEvent[] | null>(null);
  const [menu, setMenu] = useState<string | null>(null);
  const canSeeActivity = membership.roles.some((r) => r === "org_admin" || r === "validator");

  useEffect(() => {
    api.cases({}).then(
      (p) => {
        setCases(p.results);
        // L'avancement se lit dans chaque dossier : on ne l'estime pas à partir de l'état seul.
        for (const c of p.results.slice(0, RECENT)) {
          api.caseDetail(c.id).then(
            (d) => setDetails((prev) => ({ ...prev, [c.id]: d })),
            () => undefined,
          );
        }
      },
      () => setCases([]),
    );
    if (canSeeActivity) api.auditEvents().then((p) => setEvents(p.results.slice(0, 5)), () => setEvents(null));
  }, [canSeeActivity]);

  const all = cases ?? [];
  const day = (offset: number) => new Date(Date.now() - offset * 86400000).toDateString();
  const createdOn = (offset: number) => all.filter((c) => new Date(c.created_at).toDateString() === day(offset)).length;
  const count = (pred: (c: CaseSummary) => boolean) => (cases ? all.filter(pred).length : "…");
  const recent = all.slice(0, RECENT);
  const loaded = recent.map((c) => details[c.id]).filter(Boolean);
  const blocking = loaded.reduce((n, d) => n + controlItems(d).filter((i) => i.severity === "blocking").length, 0);
  const goodsCount = loaded.reduce((n, d) => n + d.revision.goods_lines.length, 0);
  const complete = loaded.filter((d) => !controlItems(d).some((i) => i.severity === "blocking")).length;
  const latest = recent[0] && details[recent[0].id];
  const latestSteps = latest ? caseSteps(latest.revision) : null;
  const steps: Step[] = DASH_STEPS().map((s, i) => ({ ...s, state: latestSteps?.[i].state ?? "todo" }));

  return (
    <div className="dash">
      <section className="hero">
        <img className="hero-art" src={portHero} alt="" />
        <div className="hero-main">
          <h1>ClairTransit</h1>
          <p className="hero-sub">{tr("dash.heroSub")}</p>
          <p className="hero-text">{tr("dash.heroText")}</p>
        </div>
        <div className="hero-side">
          <strong>{tr("country.gabon")}</strong>
          <span>{tr("dash.region")}</span>
          <i aria-hidden="true" />
        </div>
      </section>

      {membership.roles.includes("org_admin") && !membership.organization.is_demo && <SetupChecklist />}

      <div className="kpis">
        <Kpi icon="folder" tone="green" label={tr("dash.casesToday")} value={count((c) => new Date(c.created_at).toDateString() === day(0))}
          delta={trend(createdOn(0), createdOn(1))} note={tr("dash.vsYesterday")} />
        <Kpi icon="clock" tone="blue" label={tr("dash.inProgress")} value={count((c) => c.state === "draft" || c.state === "in_preparation")}
          delta={tr("dash.unassigned", { n: all.filter((c) => !c.assigned_to).length })} note={tr("dash.toTake")} />
        <Kpi icon="alert" tone="amber" label={tr("dash.toVerify")} value={count((c) => c.state === "to_validate" || c.state === "to_correct")}
          delta={tr("dash.inValidation")} note={tr("dash.orToCorrect")} />
        <Kpi icon="checkCircle" tone="green" label={tr("dash.validatedInternal")} value={count((c) => c.state === "validated")}
          delta={tr("dash.byManager")} note={tr("dash.internal")} />
        <Kpi icon="bell" tone="red" label={tr("dash.alerts")} value={loaded.length ? blocking : "…"}
          delta={tr("dash.blockingPoints")} note={tr("dash.recentCount", { n: recent.length })} />
      </div>

      <div className="dash-row">
        <section className="card dash-cases">
          <div className="card-head">
            <h2 className="card-title">{tr("dash.myRecent")}</h2>
            <button type="button" className="link-arrow" onClick={() => navigate("/dossiers")}>
              {tr("dash.seeAllCases")} <Icon name="arrowRight" size={16} />
            </button>
          </div>
          {cases === null ? (
            <p className="muted">{tr("loading")}</p>
          ) : all.length === 0 ? (
            <div className="empty onb-empty">
              <p>{tr("dash.noCaseYet")}</p>
              <button type="button" className="btn-primary" onClick={() => navigate("/nouveau")}>
                <Icon name="plus" size={18} /> {tr("onb.firstCase")}
              </button>
            </div>
          ) : (
            <table className="data dash-table">
              <thead>
                <tr>
                  <th scope="col">{tr("col.caseNumber")}</th>
                  <th scope="col">{tr("col.importerClient")}</th>
                  <th scope="col">{tr("col.type")}</th>
                  <th scope="col">{tr("col.progress")}</th>
                  <th scope="col">{tr("col.agent")}</th>
                  <th scope="col">{tr("col.status")}</th>
                  <th scope="col">{tr("col.created")}</th>
                  <th scope="col"><span className="visually-hidden">{tr("col.actions")}</span></th>
                </tr>
              </thead>
              <tbody>
                {recent.map((c) => {
                  const d = details[c.id];
                  const value = d ? progressOf(caseSteps(d.revision)) : null;
                  return (
                    <tr key={c.id}>
                      <td>
                        <button type="button" className="link-plain" onClick={() => navigate(`/dossiers/${c.id}`)}>{c.reference}</button>
                      </td>
                      <td className="ellipsis" title={c.importer?.name}>{c.importer?.name ?? <em className="muted">{tr("case.toFill")}</em>}</td>
                      <td>{tr("case.importation")}</td>
                      <td>
                        {value === null ? <span className="muted">…</span> : (
                          <span className="bar" role="progressbar" aria-valuenow={value} aria-valuemin={0} aria-valuemax={100}>
                            <span className="bar-track"><span className="bar-fill" style={{ width: `${value}%` }} /></span>
                            <span className="bar-value">{value}%</span>
                          </span>
                        )}
                      </td>
                      <td>{c.assigned_to ? shortName(personName(c.assigned_to)) : <span className="muted">{tr("case.unassigned")}</span>}</td>
                      <td><StateChip state={c.state} label={c.state_label} /></td>
                      <td className="muted">{relativeTime(c.created_at)}</td>
                      <td className="menu-wrap">
                        <button type="button" className="kebab" aria-label={tr("case.actionsFor", { ref: c.reference })} onClick={() => setMenu(menu === c.id ? null : c.id)}>
                          <Icon name="more" size={18} />
                        </button>
                        {menu === c.id && (
                          <ul className="menu menu-right" role="menu">
                            <li role="menuitem"><button type="button" onClick={() => navigate(`/dossiers/${c.id}`)}>{tr("case.open")}</button></li>
                            <li role="menuitem"><button type="button" onClick={() => navigate(`/dossiers/${c.id}/documents`)}>{tr("nav.documents")}</button></li>
                            <li role="menuitem"><button type="button" onClick={() => navigate(`/dossiers/${c.id}/controles`)}>{tr("nav.controls")}</button></li>
                          </ul>
                        )}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          )}
        </section>

        <section className="card dash-activity">
          <div className="card-head">
            <h2 className="card-title">{tr("activity.recent")}</h2>
            {canSeeActivity && (
              <button type="button" className="link-arrow" onClick={() => navigate("/administration")}>
                {tr("dash.seeAll")} <Icon name="arrowRight" size={16} />
              </button>
            )}
          </div>
          {!canSeeActivity ? (
            <p className="empty">{tr("dash.journalForManagers")}</p>
          ) : events === null || events.length === 0 ? (
            <p className="empty">{tr("activity.none")}</p>
          ) : (
            <ul className="feed">
              {events.map((e) => {
                const icon = eventIcon(e.event_type);
                const tone = icon === "alert" ? "amber" : icon === "file" ? "blue" : "green";
                return (
                  <li key={e.id}>
                    <span className={`feed-icon feed-${tone}`}><Icon name={icon} size={20} /></span>
                    <span className="feed-text">
                      <strong>{eventLabel(e.event_type)}</strong>
                      <small>{e.actor_email ?? tr("activity.system")}</small>
                    </span>
                    <time dateTime={e.at}>{capitalize(relativeTime(e.at))}</time>
                  </li>
                );
              })}
            </ul>
          )}
        </section>
      </div>

      <div className="dash-row dash-row-2">
        <section className="card dash-steps" title={latest ? tr("dash.latestProgress", { ref: latest.reference }) : undefined}>
          <h2 className="card-title">{tr("dash.stepsTitle")}</h2>
          <Stepper steps={steps} />
        </section>
        <section className="card dash-perf">
          <div className="card-head">
            <h2 className="card-title">{tr("dash.perfTitle")}</h2>
            <select aria-label={tr("dash.period")} defaultValue="recent">
              <option value="recent">{tr("dash.recentCases")}</option>
            </select>
          </div>
          <ul className="perf">
            <li>
              <span className="perf-icon"><Icon name="clock" size={20} /></span>
              <span>{tr("dash.avgTime")}</span>
              <strong>—</strong>
              <small>{tr("dash.notMeasured")}</small>
            </li>
            <li>
              <span className="perf-icon"><Icon name="file" size={20} /></span>
              <span>{tr("dash.completeCases")}</span>
              <strong>{loaded.length ? `${Math.round((complete / loaded.length) * 100)}%` : "…"}</strong>
              <small>{tr("dash.noBlocking")}</small>
            </li>
            <li>
              <span className="perf-icon"><Icon name="chart" size={20} /></span>
              <span>{tr("dash.goodsProcessed")}</span>
              <strong>{loaded.length ? goodsCount : "…"}</strong>
              <small>{tr("dash.itemLines")}</small>
            </li>
          </ul>
        </section>
      </div>
      <p className="visually-hidden">{tr("dash.signedInAs", { name: me.full_name || me.email })}</p>
    </div>
  );
}

type TodoState = "done" | "next";

function Todo({ state, title, text, action, onClick }: { state: TodoState; title: string; text: string; action?: string; onClick?: () => void }) {
  return (
    <li className={`onb-todo onb-todo-${state}`}>
      <span className="onb-todo-dot">{state === "done" && <Icon name="check" size={16} />}</span>
      <div>
        <strong>{title}</strong>
        <span>{text}</span>
      </div>
      {action && state !== "done" && (
        <button type="button" className="btn-primary btn-small-pad" onClick={onClick}>{action}</button>
      )}
    </li>
  );
}

/** Mise en route de la société, affichée à l'administrateur tant que l'équipe n'est pas en place. */
function SetupChecklist() {
  const [overview, setOverview] = useState<OrganizationOverview | null>(null);
  useEffect(() => {
    api.organizationOverview().then(setOverview, () => setOverview(null));
  }, []);
  if (!overview) return null;
  const agencies = overview.agencies > 0;
  const team = overview.members > 1 || overview.pending_invitations > 0;
  if (agencies && team) return null;
  return (
    <section className="card onb-setup" aria-labelledby="setup-title">
      <h2 id="setup-title" className="card-title">{tr("onb.setupChecklist")}</h2>
      <ol className="onb-todos">
        <Todo state="done" title={tr("onb.todoAccount")} text={tr("onb.todoAccountText")} />
        <Todo state="done" title={tr("onb.todoCompany")} text={tr("onb.todoCompanyText", { name: overview.name })} />
        <Todo state={agencies ? "done" : "next"} title={tr("adm.agencies")} text={tr("onb.todoAgencies")}
              action={tr("onb.addAgency")} onClick={() => navigate("/administration?onglet=agencies")} />
        <Todo state={team ? "done" : "next"} title={tr("onb.todoTeam")} text={tr("onb.todoTeamText")}
              action={tr("onb.invite")} onClick={() => navigate("/administration?onglet=users")} />
      </ol>
    </section>
  );
}
