import { useEffect, useState, type ReactNode } from "react";
import { api, type CaseSummary, type Me, type Membership, type OrgAuditEvent } from "./api";
import { CaseTable, canEditCases } from "./Cases";
import { Icon } from "./Icon";
import { navigate } from "./router";
import {
  caseSteps,
  eventIcon,
  eventLabel,
  ProgressBar,
  progressOf,
  relativeTime,
  StatCard,
  Stepper,
  type EditionOption,
} from "./ui";

const RECENT = 6;

export function Dashboard({ membership, me }: { membership: Membership; me: Pick<Me, "id" | "full_name" | "email"> }) {
  const [cases, setCases] = useState<CaseSummary[] | null>(null);
  const [progress, setProgress] = useState<Record<string, ReactNode>>({});
  const [events, setEvents] = useState<OrgAuditEvent[] | null>(null);
  const [editions, setEditions] = useState<EditionOption[]>([]);
  const canSeeActivity = membership.roles.some((r) => r === "org_admin" || r === "validator");

  useEffect(() => {
    api.cases({}).then(
      (p) => {
        setCases(p.results);
        // L'avancement se lit dans chaque dossier : on ne l'estime pas à partir de l'état seul.
        for (const c of p.results.slice(0, RECENT)) {
          api.caseDetail(c.id).then(
            (d) => setProgress((prev) => ({ ...prev, [c.id]: <ProgressBar value={progressOf(caseSteps(d.revision))} /> })),
            () => undefined,
          );
        }
      },
      () => setCases([]),
    );
    api.editions().then((list) => setEditions(list.filter((e) => e.publication_state !== "withdrawn")), () => setEditions([]));
    if (canSeeActivity) api.auditEvents().then((p) => setEvents(p.results.slice(0, 6)), () => setEvents(null));
  }, [canSeeActivity]);

  const all = cases ?? [];
  const today = new Date().toDateString();
  const count = (pred: (c: CaseSummary) => boolean) => (cases ? all.filter(pred).length : "…");
  const edition = editions.find((e) => e.publication_state === "operational") ?? editions[0];

  return (
    <>
      <section className="hero">
        <div>
          <h1>ClairTransit</h1>
          <p className="hero-sub">Assistant de préparation douanière</p>
          <p className="hero-text">
            Des documents reçus au dossier préparé : chaque information garde sa source, chaque décision son auteur.
          </p>
        </div>
        <div className="hero-side">
          <strong>Gabon</strong>
          <span>et toute la région CEMAC</span>
          {canEditCases(membership) && (
            <button type="button" className="btn-primary" onClick={() => navigate("/nouveau")}>
              <Icon name="plus" /> Nouveau dossier
            </button>
          )}
        </div>
      </section>

      <div className="stats">
        <StatCard icon="folder" tone="green" label="Dossiers créés aujourd'hui" value={count((c) => new Date(c.created_at).toDateString() === today)} />
        <StatCard icon="clock" tone="blue" label="En traitement" value={count((c) => c.state === "draft" || c.state === "in_preparation")} />
        <StatCard icon="alert" tone="amber" label="À vérifier" value={count((c) => c.state === "to_validate" || c.state === "to_correct")} />
        <StatCard icon="checkCircle" tone="green" label="Validés en interne" value={count((c) => c.state === "validated")} />
        <StatCard icon="users" tone="red" label="Non affectés" value={count((c) => !c.assigned_to)} />
      </div>

      <div className={canSeeActivity ? "grid-2-1" : ""}>
        <section className="card">
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
            <CaseTable cases={all.slice(0, RECENT)} progress={progress} />
          )}
        </section>
        {canSeeActivity && (
          <section className="card">
            <h2 className="card-title">Activité récente</h2>
            {events === null || events.length === 0 ? (
              <p className="empty">Aucune activité.</p>
            ) : (
              <ul className="activity">
                {events.map((e) => (
                  <li key={e.id}>
                    <span className="activity-icon"><Icon name={eventIcon(e.event_type)} size={18} /></span>
                    <span>
                      <strong>{eventLabel(e.event_type)}</strong>
                      <small>{e.actor_email ?? "système"}</small>
                    </span>
                    <time dateTime={e.at}>{relativeTime(e.at)}</time>
                  </li>
                ))}
              </ul>
            )}
          </section>
        )}
      </div>

      <div className="grid-2-1">
        <section className="card">
          <h2 className="card-title">Étapes de préparation d'un dossier</h2>
          <Stepper
            steps={[
              { key: "a", label: "Documents reçus", detail: "facture, B/L, colisage", state: "todo" },
              { key: "b", label: "Extraction", detail: "lecture des pièces", state: "todo" },
              { key: "c", label: "Classification", detail: "codes SH", state: "todo" },
              { key: "d", label: "Calcul", detail: "droits et taxes, à venir", state: "later" },
              { key: "e", label: "Validation", detail: "contrôles", state: "todo" },
              { key: "f", label: "Export", detail: "dossier final, à venir", state: "later" },
            ]}
          />
        </section>
        <section className="card">
          <h2 className="card-title">Tarif utilisé</h2>
          {edition ? (
            <>
              <p className="big-line">{edition.label}</p>
              {edition.warning && <p className="note-amber small">{edition.warning}</p>}
              <button type="button" className="link-arrow" onClick={() => navigate("/referentiel")}>
                Ouvrir le référentiel <Icon name="arrowRight" size={16} />
              </button>
            </>
          ) : (
            <p className="empty">Aucune édition publiée.</p>
          )}
        </section>
      </div>
      <p className="visually-hidden">Connecté en tant que {me.full_name || me.email}</p>
    </>
  );
}
