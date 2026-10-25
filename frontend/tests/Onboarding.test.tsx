import { render as baseRender, screen, fireEvent, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import App from "../src/App";
import { api } from "../src/api";
import type { ReactElement } from "react";
import { I18nProvider } from "../src/i18n";

const render = (ui: ReactElement) => baseRender(ui, { wrapper: I18nProvider });

function json(status: number, body: unknown) {
  return Promise.resolve(new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } }));
}

const OPERATOR = {
  id: "op",
  email: "ops@example.test",
  full_name: "Exploitant",
  is_reference_manager: true,
  is_platform_operator: true,
  interface_locale: "fr",
  active_organization_id: null,
  memberships: [],
  mfa_enabled: true,
  mfa_verified_session: true,
  mfa_required_for_access: true,
};

afterEach(() => {
  vi.restoreAllMocks();
  window.location.hash = "";
  sessionStorage.clear();
});

describe("Mise en route", () => {
  it("ouvre la mise en service sur un serveur neuf, sans compte fictif", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockImplementation((input, init) => {
      const url = String(input);
      if (url.endsWith("/me")) return json(401, {});
      if (url.endsWith("/auth/setup") && (!init?.method || init.method === "GET")) return json(200, { needs_setup: true });
      return json(500, {});
    });
    render(<App />);
    expect(await screen.findByRole("heading", { name: /mise en service/i })).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText(/nom complet/i), { target: { value: "Exploitant" } });
    fireEvent.change(screen.getByLabelText(/e-mail/i), { target: { value: "ops@example.test" } });
    fireEvent.change(screen.getByLabelText(/^mot de passe/i), { target: { value: "un-mot-de-passe-long" } });
    fireEvent.change(screen.getByLabelText(/confirmer/i), { target: { value: "autre-mot-de-passe" } });
    fireEvent.click(screen.getByRole("button", { name: /créer le compte/i }));
    expect(await screen.findByRole("alert")).toHaveTextContent(/pas identiques/i);
    expect(fetchMock.mock.calls.some(([, init]) => init?.method === "POST")).toBe(false);
  });

  it("propose de demander l'ouverture d'un espace depuis la connexion", async () => {
    vi.spyOn(globalThis, "fetch").mockImplementation((input) => {
      const url = String(input);
      if (url.endsWith("/auth/setup")) return json(200, { needs_setup: false });
      return json(401, {});
    });
    render(<App />);
    fireEvent.click(await screen.findByRole("link", { name: /demander l'ouverture/i }));
    expect(await screen.findByRole("heading", { name: /demander un espace/i })).toBeInTheDocument();
  });

  it("active une invitation : l'invité choisit lui-même son mot de passe", async () => {
    window.location.hash = "#/activation/jeton-test";
    const fetchMock = vi.spyOn(globalThis, "fetch").mockImplementation((input) => {
      const url = String(input);
      if (url.endsWith("/me")) return json(401, {});
      if (url.endsWith("/auth/setup")) return json(200, { needs_setup: false });
      if (url.endsWith("/auth/invitations/lookup")) {
        return json(200, {
          organization_name: "Transit Exemple",
          email: "agent@example.test",
          full_name: "",
          roles: ["declarant"],
          agency_name: null,
          expires_at: "2026-10-27T10:00:00Z",
          existing_account: false,
        });
      }
      return json(400, { code: "INVITATION_INVALID", message: "Lien refusé." });
    });
    render(<App />);
    expect(await screen.findByText(/chez Transit Exemple/)).toBeInTheDocument();
    expect(screen.getByDisplayValue("agent@example.test")).toHaveAttribute("readonly");
    const lookup = fetchMock.mock.calls.find(([url]) => String(url).endsWith("/auth/invitations/lookup"));
    expect(JSON.parse(String(lookup?.[1]?.body))).toEqual({ token: "jeton-test" });
  });

  it("ferme d'abord la session ouverte avant d'activer un autre compte", async () => {
    window.location.hash = "#/activation/jeton-test";
    let signedIn = true;
    const fetchMock = vi.spyOn(globalThis, "fetch").mockImplementation((input, init) => {
      const url = String(input);
      if (url.endsWith("/me")) return signedIn ? json(200, OPERATOR) : json(401, {});
      if (url.endsWith("/auth/logout") && init?.method === "POST") {
        signedIn = false;
        return Promise.resolve(new Response(null, { status: 204 }));
      }
      if (url.endsWith("/auth/setup")) return json(200, { needs_setup: false });
      if (url.endsWith("/auth/invitations/lookup")) {
        return json(200, {
          organization_name: "Transit Exemple",
          email: "agent@example.test",
          full_name: "",
          roles: ["declarant"],
          agency_name: null,
          expires_at: "2026-10-27T10:00:00Z",
          existing_account: false,
        });
      }
      return json(404, {});
    });
    render(<App />);
    expect(await screen.findByText(/connecté au compte ops@example.test/)).toBeInTheDocument();
    expect(screen.queryByLabelText(/choisissez un mot de passe/i)).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /fermer cette session et continuer/i }));
    expect(await screen.findByLabelText(/choisissez un mot de passe/i)).toBeInTheDocument();
    expect(fetchMock.mock.calls.some(([url, init]) => String(url).endsWith("/auth/logout") && init?.method === "POST")).toBe(true);
  });

  it("explique qu'un lien d'invitation n'est plus valable", async () => {
    window.location.hash = "#/activation/perime";
    vi.spyOn(globalThis, "fetch").mockImplementation((input) => {
      const url = String(input);
      if (url.endsWith("/auth/invitations/lookup")) return json(404, { code: "INVITATION_INVALID", message: "x" });
      if (url.endsWith("/auth/setup")) return json(200, { needs_setup: false });
      return json(401, {});
    });
    render(<App />);
    expect(await screen.findByRole("alert")).toHaveTextContent(/n'est plus valable/i);
  });

  it("ne déclare pas un lien périmé quand le serveur ne répond pas", async () => {
    window.location.hash = "#/activation/jeton-test";
    vi.spyOn(globalThis, "fetch").mockImplementation((input) => {
      const url = String(input);
      if (url.endsWith("/auth/invitations/lookup")) return json(502, {});
      if (url.endsWith("/auth/setup")) return json(200, { needs_setup: false });
      return json(401, {});
    });
    render(<App />);
    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent(/impossible de vérifier ce lien/i);
    expect(alert).not.toHaveTextContent(/n'est plus valable/i);
  });

  it("revient à la connexion quand la session a pris fin pendant l'utilisation", async () => {
    let signedIn = true;
    vi.spyOn(globalThis, "fetch").mockImplementation((input) => {
      const url = String(input);
      if (url.endsWith("/me")) return signedIn ? json(200, OPERATOR) : json(401, {});
      if (url.endsWith("/auth/setup")) return json(200, { needs_setup: false });
      if (url.includes("/platform/")) return signedIn ? json(200, []) : json(401, { code: "NOT_AUTHENTICATED" });
      return json(404, {});
    });
    render(<App />);
    expect(await screen.findByRole("heading", { name: /sociétés clientes/i, level: 1 })).toBeInTheDocument();
    signedIn = false;
    await expect(api.platformOrganizations()).rejects.toThrow();
    expect(await screen.findByRole("status")).toHaveTextContent(/session a pris fin/i);
    expect(screen.getByRole("button", { name: /se connecter/i })).toBeInTheDocument();
  });

  it("ouvre la console de l'exploitant et affiche le lien après acceptation d'une demande", async () => {
    const pending = {
      id: "r1",
      company_name: "Transit Exemple",
      primary_profile: "transit",
      country_code: "GA",
      registration_number: "RCCM-TEST",
      contact_name: "Awa",
      contact_role: "",
      contact_email: "awa@example.test",
      contact_phone: "",
      preferred_locale: "fr",
      status: "pending",
      decision_note: "",
      created_at: new Date().toISOString(),
    };
    const fetchMock = vi.spyOn(globalThis, "fetch").mockImplementation((input, init) => {
      const url = String(input);
      if (url.endsWith("/me")) return json(200, OPERATOR);
      if (url.includes("/platform/access-requests/r1/accept") && init?.method === "POST") {
        return json(201, {
          invitation: { id: "i1", email: pending.contact_email, full_name: "Awa", token: "jeton-admin", email_status: "sent" },
        });
      }
      if (url.includes("/platform/access-requests")) return json(200, [pending]);
      if (url.endsWith("/platform/organizations")) return json(200, []);
      return json(404, {});
    });
    render(<App />);
    expect(await screen.findByRole("heading", { name: /sociétés clientes/i, level: 1 })).toBeInTheDocument();
    fireEvent.click(await screen.findByRole("button", { name: /accepter/i }));
    expect(await screen.findByText(/lien d'activation pour Awa/i)).toBeInTheDocument();
    expect(screen.getByText(/#\/activation\/jeton-admin$/)).toBeInTheDocument();
    expect(screen.getByText(/e-mail contenant ce lien a été envoyé à awa@example.test/i)).toBeInTheDocument();
    await waitFor(() =>
      expect(fetchMock.mock.calls.some(([url]) => String(url).includes("/platform/access-requests/r1/accept"))).toBe(true),
    );
  });
});
