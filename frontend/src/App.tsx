import { useCallback, useEffect, useState } from "react";
import { api, ApiError, type Me } from "./api";
import { LoginForm } from "./LoginForm";
import { OrganizationPicker } from "./OrganizationPicker";
import { Reference } from "./Reference";
import { Workspace } from "./Workspace";

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

  const active = me.memberships.find((m) => m.organization.id === me.active_organization_id);
  const logout = async () => {
    await api.logout();
    setMe(null);
  };

  return (
    <div className="shell">
      <header className="topbar">
        <strong>ClairTransit</strong>
        {active && (
          <span className="org">
            {active.organization.name}
            {active.organization.is_demo && <span className="badge">Démonstration</span>}
          </span>
        )}
        <span className="spacer" />
        {me.memberships.length > 1 && active && (
          <OrganizationPicker me={me} onChange={setMe} compact />
        )}
        <span>{me.email}</span>
        <button type="button" onClick={logout}>
          Se déconnecter
        </button>
      </header>
      <main>
        {active ? (
          <Workspace key={active.organization.id} membership={active} />
        ) : me.memberships.length === 0 && me.is_reference_manager ? (
          <Reference />
        ) : (
          <OrganizationPicker me={me} onChange={setMe} />
        )}
      </main>
    </div>
  );
}
