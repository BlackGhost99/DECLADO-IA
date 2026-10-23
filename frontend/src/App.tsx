import { useCallback, useEffect, useState, type FormEvent, type ReactNode } from "react";
import { Administration } from "./Administration";
import { api, ApiError, ROLE_LABELS, type Me, type Membership } from "./api";
import { CaseDetailView, CASE_TABS } from "./CaseDetail";
import { CasePicker, Cases, NewCasePage } from "./Cases";
import { Dashboard } from "./Dashboard";
import { Icon, Logo, type IconName } from "./Icon";
import { LoginForm } from "./LoginForm";
import { OrganizationPicker } from "./OrganizationPicker";
import { ReferenceAdmin, TariffSearch } from "./Reference";
import { currentCase, navigate, useRoute, type Route } from "./router";
import { initials } from "./ui";

export default function App() {
  const [me, setMe] = useState<Me | null>(null);
  const [loading, setLoading] = useState(true);

  const refresh = useCallback(async () => {
    try {
      setMe(await api.me());
    } catch (err) {
      if (!(err instanceof ApiError && err.status === 401)) throw err;
      setMe(null);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  if (loading) return <p className="center">Chargement…</p>;
  if (!me) return <LoginForm onLoggedIn={setMe} />;

  const active = me.memberships.find((m) => m.organization.id === me.active_organization_id) ?? null;
  const logout = async () => {
    await api.logout();
    setMe(null);
  };

  if (!active && !(me.memberships.length === 0 && me.is_reference_manager)) {
    return (
      <main className="center">
        <OrganizationPicker me={me} onChange={setMe} />
      </main>
    );
  }

  return (
    <Layout me={me} active={active} onChangeOrg={setMe} onLogout={logout}>
      {(route) => <Page route={route} me={me} active={active} />}
    </Layout>
  );
}

interface NavItem {
  path: string;
  label: string;
  icon: IconName;
  /** Entrée liée au dossier ouvert : elle mène à l'onglet correspondant de ce dossier. */
  caseTab?: string;
}

const NAV_MAIN: NavItem[] = [
  { path: "", label: "Tableau de bord", icon: "home" },
  { path: "dossiers", label: "Mes dossiers", icon: "folder" },
  { path: "nouveau", label: "Nouveau dossier", icon: "plus" },
];

const NAV_CASE: NavItem[] = [
  { path: "documents", label: "Documents", icon: "file", caseTab: "documents" },
  { path: "marchandises", label: "Marchandises", icon: "box", caseTab: "marchandises" },
  { path: "recherche", label: "Recherche tarifaire", icon: "search" },
  { path: "calculs", label: "Calculs", icon: "calculator", caseTab: "calculs" },
  { path: "controles", label: "Contrôles", icon: "checkCircle", caseTab: "controles" },
  { path: "validation", label: "Validation", icon: "shield", caseTab: "validation" },
  { path: "export", label: "Export", icon: "upload", caseTab: "export" },
];

const NAV_ADMIN: NavItem[] = [
  { path: "referentiel", label: "Référentiel", icon: "book" },
  { path: "administration", label: "Administration", icon: "settings" },
];

function isActive(item: NavItem, route: Route): boolean {
  const [first, , tab] = route.parts;
  if (item.caseTab) return first === "dossiers" && tab === item.caseTab;
  if (item.path === "dossiers") return first === "dossiers" && (!tab || !NAV_CASE.some((n) => n.caseTab === tab));
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
    ? active.roles.map((r) => ROLE_LABELS[r]).join(", ") || "Aucun rôle"
    : "Gestionnaire du référentiel";

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
        <nav aria-label="Navigation principale">
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
                    {item.label}
                  </button>
                </li>
              ))}
            </ul>
          ))}
        </nav>
        <div className="sidebar-foot">
          <strong>CEMAC</strong>
          <span>Gabon · Cameroun · Congo · RCA · Guinée équatoriale · Tchad</span>
        </div>
      </aside>

      <div className="main-col">
        <header className="topbar">
          {active ? (
            <form role="search" className="topsearch" onSubmit={search}>
              <Icon name="search" />
              <input
                aria-label="Rechercher un dossier"
                placeholder="Rechercher un dossier, une référence…"
                value={query}
                onChange={(e) => setQuery(e.target.value)}
              />
            </form>
          ) : (
            <span />
          )}
          <div className="topbar-right">
            {active?.organization.is_demo && <span className="demo-flag">Démonstration · données fictives</span>}
            {active && me.memberships.length > 1 && <OrganizationPicker me={me} onChange={onChangeOrg} compact />}
            <span className="country" title="Territoire des dossiers">
              <span className="flag-ga" aria-hidden="true" />
              Gabon
            </span>
            <span className="user">
              <span className="avatar">{initials(name)}</span>
              <span className="user-text">
                <strong>{name}</strong>
                <small>
                  {roleLabel}
                  {active && ` · ${active.organization.name}`}
                </small>
              </span>
            </span>
            <button type="button" className="icon-button" onClick={onLogout} title="Se déconnecter">
              <Icon name="logout" />
              <span className="visually-hidden">Se déconnecter</span>
            </button>
          </div>
        </header>
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
      return <NewCasePage membership={active} />;
    case "recherche":
      return <TariffSearch />;
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
      return <p>Page introuvable.</p>;
  }
}
