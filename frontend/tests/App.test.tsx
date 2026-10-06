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

afterEach(() => vi.restoreAllMocks());

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
    expect(await screen.findByText("Comptoir Fictif Bêta")).toBeInTheDocument();
    const call = fetchMock.mock.calls.find(([u]) => String(u).endsWith("/me/active-organization"))!;
    expect((call[1]!.headers as Record<string, string>)["X-CSRFToken"]).toBe("tok123");
    await waitFor(() => expect(screen.getByText("Démonstration")).toBeInTheDocument());
  });
});
