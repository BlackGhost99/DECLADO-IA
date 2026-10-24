import { useCallback, useEffect, useState } from "react";
import { api, ApiError, type Me } from "./api";
import { LoginForm } from "./LoginForm";
import { MFAEnrollment } from "./MFAEnrollment";
import { OrganizationPicker } from "./OrganizationPicker";
import { Reference } from "./Reference";
import { Workspace } from "./Workspace";
import { LanguageSelector, useI18n } from "./i18n";
import { useLocaleSync } from "./i18n/sync";

export default function App() {
  const { t } = useI18n();
  const {onAuthenticated,onSignedOut}=useLocaleSync();
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

  useEffect(() => {
    void refresh();
  }, [refresh]);

  if (loading) return <p className="center">{t("loading")}</p>;
  if (!me) return <LoginForm onLoggedIn={(profile) => { setMe(profile); onAuthenticated(profile); }} />;

  if (me.mfa_required_for_access && !me.mfa_enabled) {
    return <MFAEnrollment onComplete={(profile) => { setMe(profile); onAuthenticated(profile); }} />;
  }
  if (me.mfa_required_for_access && !me.mfa_verified_session) {
    return <main className="center"><div className="card"><p>Session à vérifier par MFA.</p>
      <button onClick={() => void api.logout().then(() => setMe(null))}>Se reconnecter</button>
    </div></main>;
  }
  const active = me.memberships.find((m) => m.organization.id === me.active_organization_id);
  const logout = async () => {
    await api.logout();
    setMe(null);
    onSignedOut();
  };

  return (
    <div className="shell">
      <header className="topbar">
        <strong>ClairTransit</strong>
        {active && (
          <span className="org">
            {active.organization.name}
            {active.organization.is_demo && <span className="badge">{t("demo")}</span>}
          </span>
        )}
        <span className="spacer" />
        {me.memberships.length > 1 && active && (
          <OrganizationPicker me={me} onChange={(profile) => { setMe(profile); onAuthenticated(profile); }} compact />
        )}
        <LanguageSelector />
        <span>{me.email}</span>
        <button type="button" onClick={logout}>
          {t("logout")}
        </button>
      </header>
      <main>
        {active ? (
          <Workspace key={active.organization.id} membership={active} me={me} />
        ) : me.memberships.length === 0 && me.is_reference_manager ? (
          <Reference />
        ) : (
          <OrganizationPicker me={me} onChange={(profile) => { setMe(profile); onAuthenticated(profile); }} />
        )}
      </main>
    </div>
  );
}
