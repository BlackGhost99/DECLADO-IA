import { useEffect, useState, type ReactNode } from "react";
import { api, type CaseDetail, type CaseSummary, type Me, type Membership, type OrgAuditEvent } from "./api";
import { controlItems } from "./Controls";
import { PortScene } from "./Illustrations";
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
  const [details, setDetails] = useState<Record<string, CaseDetail>>({});
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
            (d) => setDetails((prev) => ({ ...prev, [c.id]: d })),
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
  const loaded = Object.values(details);
  const progress: Record<string, ReactNode> = Object.fromEntries(
    loaded.map((d) => [d.id, <ProgressBar key={d.id} value={progressOf(caseSteps(d.revision))} />]),
  );
  const blocking = loaded.reduce((n, d) => n + controlItems(d).filter((i) => i.severity === "blocking").length, 0);
  const goodsCount = loaded.reduce((n, d) => n + d.revision.goods_lines.length, 0);
  const decidedCount = loaded.reduce((n, d) => n + d.revision.goods_lines.filter((g) => g.decision?.is_current).length, 0);
  const docsCount = loaded.reduce((n, d) => n + d.revision.documents.filter((x) => !x.replaced_by_id).length, 0);
  const sample = Math.min(RECENT, all.length);

  return (
    <>
      <section className="hero">
        <PortScene />
        <div className="hero-main">
          <h1>ClairTransit</h1>
          <p className="hero-sub">Assistant de préparation douanière</p>
          <p className="hero-text">
            Transformez vos documents d’import en dossiers de dédouanement structurés, traçables et prêts à être vérifiés.
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
        <StatCard
          icon="folder"
          tone="green"
          label="Dossiers aujourd'hui"
          value={count((c) => new Date(c.created_at).toDateString() === today)}
          hint={cases ? `sur ${all.length} dossier(s) au total` : undefined}
        />
        <StatCard
          icon="clock"
          tone="blue"
          label="En traitement"
          value={count((c) => c.state === "draft" || c.state === "in_preparation")}
          hint={cases ? `dont ${all.filter((c) => !c.assigned_to).length} non affecté(s)` : undefined}
        />
        <StatCard icon="alert" tone="amber" label="À vérifier" value={count((c) => c.state === "to_validate" || c.state === "to_correct")} hint="en validation ou à corriger" />
        <StatCard icon="checkCircle" tone="green" label="Validés en interne" value={count((c) => c.state === "validated")} hint="par un responsable de la société" />
        <StatCard
          icon="bell"
          tone="red"
          label="Points bloquants"
          value={loaded.length ? blocking : "…"}
          hint={sample ? `dans les ${sample} dossier(s) récents` : undefined}
        />
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
            <div className="card-head">
              <h2 className="card-title">Activité récente</h2>
              <span className="muted small">journal de la société</span>
            </div>
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
          <div className="card-head">
            <h2 className="card-title">Activité et suivi</h2>
            <span className="muted small">{sample} dossier(s) récents</span>
          </div>
          <ul className="perf">
            <li>
              <span className="stat-icon tone-green"><Icon name="file" size={20} /></span>
              <span>Pièces reçues</span>
              <strong>{loaded.length ? docsCount : "…"}</strong>
            </li>
            <li>
              <span className="stat-icon tone-blue"><Icon name="box" size={20} /></span>
              <span>Marchandises préparées</span>
              <strong>{loaded.length ? goodsCount : "…"}</strong>
            </li>
            <li>
              <span className="stat-icon tone-green"><Icon name="checkCircle" size={20} /></span>
              <span>Codes validés</span>
              <strong>{loaded.length ? `${decidedCount} / ${goodsCount}` : "…"}</strong>
            </li>
            <li>
              <span className="stat-icon tone-gray"><Icon name="clock" size={20} /></span>
              <span>Temps moyen de préparation</span>
              <strong className="muted small">pas encore mesuré</strong>
            </li>
          </ul>
          <div className="edition-line">
            <Icon name="book" size={18} />
            <span>
              Tarif utilisé : <strong>{edition?.label ?? "aucune édition publiée"}</strong>
              {edition?.warning && <small className="block">{edition.publication_state === "operational" ? "" : "consultation historique, taux non vérifiés"}</small>}
            </span>
            <button type="button" className="link-arrow" onClick={() => navigate("/referentiel")}>
              Référentiel <Icon name="arrowRight" size={16} />
            </button>
          </div>
        </section>
      </div>
      <p className="visually-hidden">Connecté en tant que {me.full_name || me.email}</p>
    </>
  );
}
