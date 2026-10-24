import { useCallback, useEffect, useState, type FormEvent, type ReactNode } from "react";
import { Administration } from "./Administration";
import { api, ApiError, ROLE_LABELS, type Me, type Membership, type OrgAuditEvent } from "./api";
import { CaseDetailView, CASE_TABS } from "./CaseDetail";
import { CasePicker, Cases } from "./Cases";
import { NewCasePage } from "./NewCase";
import { Dashboard } from "./Dashboard";
import { Icon, Logo, type IconName } from "./Icon";
import cemacMap from "./assets/cemac-map.png";
import { LoginForm } from "./LoginForm";
import { MFAEnrollment } from "./MFAEnrollment";
import { OrganizationPicker } from "./OrganizationPicker";
import { ReferenceAdmin, TariffSearch } from "./Reference";
import { ScanScreens } from "./Scans";
import { currentCase, navigate, useRoute, type Route } from "./router";
import { eventIcon, eventLabel, initials, relativeTime } from "./ui";
import { LanguageSelector, tr, useBusinessLabels, useI18n, type MessageKey } from "./i18n";
import { useLocaleSync } from "./i18n/sync";

export default function App() {
  const { t } = useI18n();
  const { onAuthenticated, onSignedOut } = useLocaleSync();
  const [me, setMe] = useState<Me | null>(null);
  const [loading, setLoading] = useState(true);

  const refresh = useCallback(async () => {
    try {
      const profile = await api.me();
      setMe(profile);
      onAuthenticated(profile);
    } catch (err) {
      if (!(err instanceof ApiError && err.status === 401)) throw err;
      setMe(null);
      onSignedOut();
    } finally {
      setLoading(false);
    }
  }, [onAuthenticated, onSignedOut]);

  /** Tout changement de profil (connexion, MFA, société) réapplique la langue effective. */
  const signedIn = useCallback(
    (profile: Me) => {
      setMe(profile);
      onAuthenticated(profile);
    },
    [onAuthenticated],
  );

  useEffect(() => {
    void refresh();
  }, [refresh]);

  if (loading) return <p className="center">{t("loading")}</p>;
  if (!me) return <LoginForm onLoggedIn={signedIn} />;

  const logout = async () => {
    await api.logout();
    setMe(null);
    onSignedOut();
  };

  if (me.mfa_required_for_access && !me.mfa_enabled) {
    return <MFAEnrollment onComplete={signedIn} />;
  }
  if (me.mfa_required_for_access && !me.mfa_verified_session) {
    return (
      <main className="login-page">
        <section className="card login">
          <p>{tr("mfa.verifySession")}</p>
          <button type="button" className="btn-primary btn-block" onClick={() => void logout()}>
            {tr("mfa.signInAgain")}
          </button>
        </section>
      </main>
    );
  }

  const active = me.memberships.find((m) => m.organization.id === me.active_organization_id) ?? null;

  if (!active && !(me.memberships.length === 0 && me.is_reference_manager)) {
    return (
      <main className="center">
        <OrganizationPicker me={me} onChange={signedIn} />
      </main>
    );
  }

  return (
    <Layout me={me} active={active} onChangeOrg={signedIn} onLogout={logout}>
      {(route) => <Page route={route} me={me} active={active} />}
    </Layout>
  );
}

interface NavItem {
  path: string;
  label: MessageKey;
  icon: IconName;
  /** Entrée liée au dossier ouvert : elle mène à l'onglet correspondant de ce dossier. */
  caseTab?: string;
}

const NAV_MAIN: NavItem[] = [
  { path: "", label: "nav.dashboard", icon: "home" },
  { path: "dossiers", label: "nav.myCases", icon: "folder" },
  { path: "nouveau", label: "nav.newCase", icon: "plus" },
];

const NAV_CASE: NavItem[] = [
  { path: "documents", label: "nav.documents", icon: "file", caseTab: "documents" },
  { path: "marchandises", label: "nav.goods", icon: "box", caseTab: "marchandises" },
  { path: "recherche", label: "nav.tariffSearch", icon: "search" },
  { path: "calculs", label: "nav.calculations", icon: "calculator", caseTab: "calculs" },
  { path: "controles", label: "nav.controls", icon: "checkCircle", caseTab: "controles" },
  { path: "validation", label: "nav.validation", icon: "shield", caseTab: "validation" },
  { path: "export", label: "nav.export", icon: "upload", caseTab: "export" },
];

const NAV_ADMIN: NavItem[] = [
  { path: "referentiel", label: "nav.reference", icon: "book" },
  { path: "administration", label: "nav.administration", icon: "settings" },
];

const CEMAC: MessageKey[] = ["country.gabon", "country.cameroon", "country.congo", "country.car", "country.eqGuinea", "country.chad"];

/** Pays de la CEMAC : seul le Gabon est ouvert ; les autres sont annoncés, jamais simulés. */
function CountryMenu() {
  const [open, setOpen] = useState(false);
  return (
    <div className="menu-wrap">
      <button type="button" className="country" aria-expanded={open} aria-haspopup="menu" onClick={() => setOpen(!open)}>
        <span className="flag-ga" aria-hidden="true" />
        {tr("country.gabon")}
        <Icon name="chevronDown" size={16} />
      </button>
      {open && (
        <ul className="menu" role="menu" aria-label={tr("country.menu")}>
          {CEMAC.map((c) => (
            <li key={c} role="menuitem" aria-disabled={c !== "country.gabon"} className={c === "country.gabon" ? "current" : "disabled"}>
              {tr(c)}
              <small>{c === "country.gabon" ? tr("country.active") : tr("country.soon")}</small>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

/** Cloche : les derniers événements de la société (journal réel), visibles des responsables. */
function Notifications({ membership }: { membership: Membership }) {
  const allowed = membership.roles.some((r) => r === "org_admin" || r === "validator");
  const [open, setOpen] = useState(false);
  const [events, setEvents] = useState<OrgAuditEvent[] | null>(null);
  useEffect(() => {
    if (open && allowed && events === null) api.auditEvents().then((p) => setEvents(p.results.slice(0, 8)), () => setEvents([]));
  }, [open, allowed, events]);
  return (
    <div className="menu-wrap">
      <button type="button" className="icon-button bell" aria-expanded={open} onClick={() => setOpen(!open)} title={tr("notif.title")}>
        <Icon name="bell" size={22} />
        <span className="visually-hidden">{tr("notif.title")}</span>
      </button>
      {open && (
        <div className="menu menu-wide" role="dialog" aria-label={tr("notif.title")}>
          <strong className="menu-title">{tr("activity.recent")}</strong>
          {!allowed ? (
            <p className="muted small">{tr("notif.personalSoon")}</p>
          ) : events === null ? (
            <p className="muted small">{tr("loading")}</p>
          ) : events.length === 0 ? (
            <p className="muted small">{tr("activity.none")}</p>
          ) : (
            <ul className="activity">
              {events.map((e) => (
                <li key={e.id}>
                  <span className="activity-icon"><Icon name={eventIcon(e.event_type)} size={16} /></span>
                  <span>
                    <strong>{eventLabel(e.event_type)}</strong>
                    <small>{e.actor_email ?? tr("activity.system")}</small>
                  </span>
                  <time dateTime={e.at}>{relativeTime(e.at)}</time>
                </li>
              ))}
            </ul>
          )}
        </div>
      )}
    </div>
  );
}

/** Utilisateur connecté : société, changement de société et déconnexion. */
function UserMenu({
  name,
  roleLabel,
  me,
  active,
  onChangeOrg,
  onLogout,
}: {
  name: string;
  roleLabel: string;
  me: Me;
  active: Membership | null;
  onChangeOrg: (me: Me) => void;
  onLogout: () => void;
}) {
  const { t } = useI18n();
  const [open, setOpen] = useState(false);
  return (
    <div className="menu-wrap">
      <button type="button" className="user" aria-haspopup="menu" aria-expanded={open} onClick={() => setOpen(!open)}>
        <span className="avatar">{initials(name)}</span>
        <span className="user-text">
          <strong>{name}</strong>
          <small>{roleLabel}</small>
        </span>
        <Icon name="chevronDown" size={18} className="user-chevron" />
      </button>
      {open && (
        <div className="menu menu-right user-menu" role="menu" aria-label={tr("account.menu")}>
          {active && <p className="menu-title">{active.organization.name}</p>}
          {active && me.memberships.length > 1 && <OrganizationPicker me={me} onChange={onChangeOrg} compact />}
          <button type="button" role="menuitem" onClick={onLogout}>
            <Icon name="logout" size={16} /> {t("logout")}
          </button>
        </div>
      )}
    </div>
  );
}

function isActive(item: NavItem, route: Route): boolean {
  const [first, , tab] = route.parts;
  // La numérisation fait partie des documents du dossier.
  const caseTab = tab === "numerisation" ? "documents" : tab;
  if (item.caseTab) return first === "dossiers" && caseTab === item.caseTab;
  if (item.path === "dossiers") return first === "dossiers" && (!caseTab || !NAV_CASE.some((n) => n.caseTab === caseTab));
  return (first ?? "") === item.path;
}

function Layout({
  me,
  active,
  onChangeOrg,
  onLogout,
  children,
}: {
  me: Me;
  active: Membership | null;
  onChangeOrg: (me: Me) => void;
  onLogout: () => void;
  children: (route: Route) => ReactNode;
}) {
  const { t } = useI18n();
  const labels = useBusinessLabels();
  const route = useRoute();
  const [query, setQuery] = useState("");
  const referenceOnly = !active;
  const groups = referenceOnly
    ? [[NAV_CASE[2]], [NAV_ADMIN[0]]]
    : [NAV_MAIN, NAV_CASE, NAV_ADMIN];

  function go(item: NavItem) {
    const caseId = currentCase();
    navigate(item.caseTab && caseId ? `/dossiers/${caseId}/${item.caseTab}` : `/${item.path}`);
  }

  function search(event: FormEvent) {
    event.preventDefault();
    navigate(`/dossiers?q=${encodeURIComponent(query)}`);
  }

  const name = me.full_name || me.email;
  const roleLabel = active
    ? active.roles.map((r) => labels.role(r, ROLE_LABELS[r])).join(", ") || tr("role.none")
    : tr("role.referenceManager");

  return (
    <div className="app">
      <aside className="sidebar">
        <a href="#/" className="brand">
          <Logo />
          <span>
            <strong>ClairTransit</strong>
            <small>Customs AI</small>
          </span>
        </a>
        <nav aria-label={tr("nav.main")}>
          {groups.map((group, i) => (
            <ul key={i} className="nav-group">
              {group.map((item) => (
                <li key={item.path}>
                  <button
                    type="button"
                    className={`nav-item${isActive(item, route) ? " active" : ""}`}
                    aria-current={isActive(item, route) ? "page" : undefined}
                    onClick={() => go(item)}
                  >
                    <Icon name={item.icon} />
                    {tr(item.label)}
                    {NAV_ADMIN.includes(item) && <Icon name="chevronRight" size={16} className="nav-chevron" />}
                  </button>
                </li>
              ))}
            </ul>
          ))}
        </nav>
        <div className="sidebar-foot">
          <img src={cemacMap} alt="" width={98} height={120} />
          <div>
            <strong>CEMAC</strong>
            <ul>
              {CEMAC.map((c) => (
                <li key={c}>{tr(c)}</li>
              ))}
            </ul>
          </div>
        </div>
      </aside>

      <div className="main-col">
        <header className="topbar">
          {active ? (
            <form role="search" className="topsearch" onSubmit={search}>
              <Icon name="search" />
              <input
                aria-label={tr("search.caseLabel")}
                placeholder={tr("search.casePlaceholder")}
                value={query}
                onChange={(e) => setQuery(e.target.value)}
              />
            </form>
          ) : (
            <span />
          )}
          <div className="topbar-right">
            {active?.organization.is_demo && <span className="demo-flag">{t("demo")} · {tr("demo.fictitious")}</span>}
            <div className="topbar-lang">
              <LanguageSelector />
            </div>
            {active && <Notifications membership={active} />}
            <UserMenu name={name} roleLabel={roleLabel} me={me} active={active} onChangeOrg={onChangeOrg} onLogout={onLogout} />
          </div>
        </header>
        <div className="country-slot">
          <CountryMenu />
        </div>
        <main className="content">{children(route)}</main>
      </div>
    </div>
  );
}

function Page({ route, me, active }: { route: Route; me: Me; active: Membership | null }) {
  const [first, id, tab] = route.parts;

  if (!active) {
    return first === "referentiel" ? <ReferenceAdmin canSeeImports={me.is_reference_manager} /> : <TariffSearch />;
  }

  switch (first ?? "") {
    case "":
      return <Dashboard membership={active} me={me} />;
    case "dossiers":
      if (id && tab === "numerisation") {
        return <ScanScreens key={id} caseId={id} rest={route.parts.slice(3)} membership={active} />;
      }
      if (id) {
        return (
          <CaseDetailView
            key={id}
            caseId={id}
            tab={CASE_TABS.some((t) => t.key === tab) ? tab : "apercu"}
            me={me}
            membership={active}
          />
        );
      }
      return <Cases membership={active} me={me} initialQuery={route.query.get("q") ?? ""} />;
    case "nouveau":
      return <NewCasePage membership={active} me={me} />;
    case "recherche":
      return <TariffSearch initialQuery={route.query.get("q") ?? ""} />;
    case "referentiel":
      return <ReferenceAdmin canSeeImports={me.is_reference_manager} />;
    case "administration":
      return <Administration membership={active} />;
    case "documents":
    case "marchandises":
    case "calculs":
    case "controles":
    case "validation":
    case "export":
      return <CasePicker tab={first} me={me} />;
    default:
      return <p>{tr("page.notFound")}</p>;
  }
}
