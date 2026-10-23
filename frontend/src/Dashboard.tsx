import { useEffect, useState, type ReactNode } from "react";
import { api, type CaseDetail, type CaseSummary, type Me, type Membership, type OrgAuditEvent } from "./api";
import portHero from "./assets/port-hero.png";
import { controlItems } from "./Controls";
import { Icon, type IconName } from "./Icon";
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

const DASH_STEPS: Omit<Step, "state">[] = [
  { key: "documents", label: "Documents reçus", detail: "BL, facture, packing list…" },
  { key: "donnees", label: "Extraction", detail: "Lecture PDF" },
  { key: "marchandises", label: "Classification", detail: "Code SH" },
  { key: "calculs", label: "Calcul", detail: "Droits et taxes" },
  { key: "validation", label: "Validation", detail: "Contrôles" },
  { key: "export", label: "Export", detail: "Dossier final" },
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
  const steps: Step[] = DASH_STEPS.map((s, i) => ({ ...s, state: latestSteps?.[i].state ?? "todo" }));

  return (
    <div className="dash">
      <section className="hero">
        <img className="hero-art" src={portHero} alt="" />
        <div className="hero-main">
          <h1>ClairTransit</h1>
          <p className="hero-sub">Assistant de préparation douanière</p>
          <p className="hero-text">
            Transformez vos documents import en dossiers de dédouanement complets, vérifiés et prêts à préparer.
          </p>
        </div>
        <div className="hero-side">
          <strong>Gabon</strong>
          <span>et toute la région CEMAC</span>
          <i aria-hidden="true" />
        </div>
      </section>

      <div className="kpis">
        <Kpi icon="folder" tone="green" label="Dossiers aujourd'hui" value={count((c) => new Date(c.created_at).toDateString() === day(0))}
          delta={trend(createdOn(0), createdOn(1))} note="vs hier" />
        <Kpi icon="clock" tone="blue" label="En traitement" value={count((c) => c.state === "draft" || c.state === "in_preparation")}
          delta={`${all.filter((c) => !c.assigned_to).length} non affecté(s)`} note="à prendre en charge" />
        <Kpi icon="alert" tone="amber" label="À vérifier" value={count((c) => c.state === "to_validate" || c.state === "to_correct")}
          delta="en validation" note="ou à corriger" />
        <Kpi icon="checkCircle" tone="green" label="Validés en interne" value={count((c) => c.state === "validated")}
          delta="par un responsable" note="interne à la société" />
        <Kpi icon="bell" tone="red" label="Alertes" value={loaded.length ? blocking : "…"}
          delta="points bloquants" note={`${recent.length} dossiers récents`} />
      </div>

      <div className="dash-row">
        <section className="card dash-cases">
          <div className="card-head">
            <h2 className="card-title">Mes dossiers récents</h2>
            <button type="button" className="link-arrow" onClick={() => navigate("/dossiers")}>
              Voir tous les dossiers <Icon name="arrowRight" size={16} />
            </button>
          </div>
          {cases === null ? (
            <p className="muted">Chargement…</p>
          ) : all.length === 0 ? (
            <p className="empty">Aucun dossier pour l'instant.</p>
          ) : (
            <table className="data dash-table">
              <thead>
                <tr>
                  <th scope="col">N° Dossier</th>
                  <th scope="col">Importateur / Client</th>
                  <th scope="col">Type</th>
                  <th scope="col">Progression</th>
                  <th scope="col">Agent</th>
                  <th scope="col">Statut</th>
                  <th scope="col">Créé</th>
                  <th scope="col"><span className="visually-hidden">Actions</span></th>
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
                      <td className="ellipsis" title={c.importer?.name}>{c.importer?.name ?? <em className="muted">à renseigner</em>}</td>
                      <td>Importation</td>
                      <td>
                        {value === null ? <span className="muted">…</span> : (
                          <span className="bar" role="progressbar" aria-valuenow={value} aria-valuemin={0} aria-valuemax={100}>
                            <span className="bar-track"><span className="bar-fill" style={{ width: `${value}%` }} /></span>
                            <span className="bar-value">{value}%</span>
                          </span>
                        )}
                      </td>
                      <td>{c.assigned_to ? shortName(personName(c.assigned_to)) : <span className="muted">non affecté</span>}</td>
                      <td><StateChip state={c.state} label={c.state_label} /></td>
                      <td className="muted">{relativeTime(c.created_at)}</td>
                      <td className="menu-wrap">
                        <button type="button" className="kebab" aria-label={`Actions ${c.reference}`} onClick={() => setMenu(menu === c.id ? null : c.id)}>
                          <Icon name="more" size={18} />
                        </button>
                        {menu === c.id && (
                          <ul className="menu menu-right" role="menu">
                            <li role="menuitem"><button type="button" onClick={() => navigate(`/dossiers/${c.id}`)}>Ouvrir le dossier</button></li>
                            <li role="menuitem"><button type="button" onClick={() => navigate(`/dossiers/${c.id}/documents`)}>Documents</button></li>
                            <li role="menuitem"><button type="button" onClick={() => navigate(`/dossiers/${c.id}/controles`)}>Contrôles</button></li>
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
            <h2 className="card-title">Activité récente</h2>
            {canSeeActivity && (
              <button type="button" className="link-arrow" onClick={() => navigate("/administration")}>
                Voir tout <Icon name="arrowRight" size={16} />
              </button>
            )}
          </div>
          {!canSeeActivity ? (
            <p className="empty">Le journal de la société est visible des responsables.</p>
          ) : events === null || events.length === 0 ? (
            <p className="empty">Aucune activité.</p>
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
                      <small>{e.actor_email ?? "système"}</small>
                    </span>
                    <time dateTime={e.at}>{relativeTime(e.at).replace(/^il y a /, "Il y a ")}</time>
                  </li>
                );
              })}
            </ul>
          )}
        </section>
      </div>

      <div className="dash-row dash-row-2">
        <section className="card dash-steps" title={latest ? `Avancement du dossier le plus récent, ${latest.reference}` : undefined}>
          <h2 className="card-title">Étapes de préparation d'un dossier</h2>
          <Stepper steps={steps} />
        </section>
        <section className="card dash-perf">
          <div className="card-head">
            <h2 className="card-title">Gains et performance</h2>
            <select aria-label="Période" defaultValue="recent">
              <option value="recent">Dossiers récents</option>
            </select>
          </div>
          <ul className="perf">
            <li>
              <span className="perf-icon"><Icon name="clock" size={20} /></span>
              <span>Temps moyen estimé</span>
              <strong>—</strong>
              <small>pas encore mesuré</small>
            </li>
            <li>
              <span className="perf-icon"><Icon name="file" size={20} /></span>
              <span>Dossiers complets</span>
              <strong>{loaded.length ? `${Math.round((complete / loaded.length) * 100)}%` : "…"}</strong>
              <small>sans point bloquant</small>
            </li>
            <li>
              <span className="perf-icon"><Icon name="chart" size={20} /></span>
              <span>Marchandises traitées</span>
              <strong>{loaded.length ? goodsCount : "…"}</strong>
              <small>lignes d'articles</small>
            </li>
          </ul>
        </section>
      </div>
      <p className="visually-hidden">Connecté en tant que {me.full_name || me.email}</p>
    </div>
  );
}
