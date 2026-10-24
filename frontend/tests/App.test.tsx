import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import App from "../src/App";

const me = {
  id: "u1",
  email: "multi@demo.demo",
  full_name: "Multi",
  is_reference_manager: false,
  memberships: [
    { organization: { id: "a", name: "Transit Alpha (démo)", is_demo: true, timezone: "Africa/Libreville" }, roles: ["declarant"] },
    { organization: { id: "b", name: "Transit Bêta (démo)", is_demo: true, timezone: "Africa/Libreville" }, roles: ["declarant"] },
  ],
  active_organization_id: null,
};

function json(status: number, body: unknown) {
  return Promise.resolve(new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } }));
}

afterEach(() => {
  vi.restoreAllMocks();
  window.location.hash = "";
  sessionStorage.clear();
});

describe("App", () => {
  it("affiche le formulaire de connexion quand la session est absente", async () => {
    vi.spyOn(globalThis, "fetch").mockImplementation(() => json(401, { code: "NOT_AUTHENTICATED" }));
    render(<App />);
    expect(await screen.findByRole("heading", { name: /connexion/i })).toBeInTheDocument();
  });

  it("affiche l'erreur de l'API sans révéler si le compte existe", async () => {
    vi.spyOn(globalThis, "fetch").mockImplementation((input) => {
      const url = String(input);
      if (url.endsWith("/me")) return json(401, {});
      if (url.endsWith("/auth/csrf")) return Promise.resolve(new Response(null, { status: 204 }));
      return json(400, { code: "INVALID_CREDENTIALS", message: "Identifiants incorrects." });
    });
    render(<App />);
    fireEvent.change(await screen.findByLabelText(/e-mail/i), { target: { value: "x@y.z" } });
    fireEvent.change(screen.getByLabelText(/mot de passe/i), { target: { value: "bad" } });
    fireEvent.click(screen.getByRole("button", { name: /se connecter/i }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Identifiants incorrects.");
  });

  it("demande de choisir une société quand il y en a plusieurs, et envoie le jeton CSRF", async () => {
    document.cookie = "csrftoken=tok123";
    const fetchMock = vi.spyOn(globalThis, "fetch").mockImplementation((input, init) => {
      const url = String(input);
      if (url.endsWith("/me")) return json(200, me);
      if (url.endsWith("/me/active-organization")) return json(200, { ...me, active_organization_id: "b" });
      if (url.endsWith("/importers")) return json(200, { count: 1, results: [{ id: "i", name: "Comptoir Fictif Bêta", identifiers: { nif: "DEMO-B-0001" }, contacts: [], address: "", notes: "", row_version: 1 }] });
      return json(404, { code: "NOT_FOUND", message: url, init });
    });
    render(<App />);
    fireEvent.click(await screen.findByRole("button", { name: "Transit Bêta (démo)" }));
    fireEvent.click(await screen.findByRole("button", { name: "Administration" }));
    expect(await screen.findByText("Comptoir Fictif Bêta")).toBeInTheDocument();
    const call = fetchMock.mock.calls.find(([u]) => String(u).endsWith("/me/active-organization"))!;
    expect((call[1]!.headers as Record<string, string>)["X-CSRFToken"]).toBe("tok123");
    await waitFor(() => expect(screen.getByText(/Démonstration · données fictives/)).toBeInTheDocument());
  });

  it("affiche la fiche d'un code avec l'avertissement historique et la valeur inconnue", async () => {
    const node = {
      id: "n1", code: "01019000", code_display: "0101.90.00", kind: "tariff_line", label: "Autres", declarable: true,
      label_raw: "Autres", label_damaged: false, label_available: true, validation_state: "extracted",
      full_path: "01 › 01.01 › 0101.90 › Autres",
      edition: { id: "e", label: "Jeu F CSV", publication_state: "consultation",
        warning: "Consultation historique : non validée.",
        source: { title: "f.csv", kind_label: "Export CSV", is_derived_copy: true, provenance_note: "" } },
      ancestors: [{ id: "p", code: "01", code_display: "01", kind: "chapter", label: "", declarable: false }],
      children: [], evidence: { record_id: "r", location: "CSV A3:F3", page_index: null, printed_page: "", cell_range: "A3:F3", line: null },
      occurrences: [], notes: [], related_notes: [], same_code_in_other_editions: [], issues: [],
      rate_observations: { warning: "Vide = inconnu (≠ 0).", items: [{ column: "TVA", raw_value: "", value: null, quality: "unknown" }] },
    };
    vi.spyOn(globalThis, "fetch").mockImplementation((input) => {
      const url = String(input);
      if (url.endsWith("/me")) return json(200, { ...me, active_organization_id: "a" });
      if (url.includes("/tariffs/search")) return json(200, { results: [{ ...node, reason: "texte", edition: node.edition }] });
      if (url.includes("/tariffs/nodes/")) return json(200, node);
      return json(404, {});
    });
    render(<App />);
    fireEvent.click(await screen.findByRole("button", { name: "Recherche tarifaire" }));
    fireEvent.change(await screen.findByLabelText(/code, préfixe/i), { target: { value: "autres" } });
    fireEvent.click(screen.getByRole("button", { name: "Rechercher" }));
    fireEvent.click(await screen.findByRole("button", { name: /0101\.90\.00/ }));
    expect(await screen.findByRole("note")).toHaveTextContent("Consultation historique");
    expect(screen.getByText("inconnu (vide)")).toBeInTheDocument();
  });
});
