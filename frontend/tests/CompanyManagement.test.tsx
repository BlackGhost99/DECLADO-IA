import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { CompanyManagement } from "../src/CompanyManagement";
import type { PlatformCompanyDetail } from "../src/api";
import { I18nProvider } from "../src/i18n";

const company: PlatformCompanyDetail = {
  id: "7a5c1bac-d710-4ba4-9106-8f8df4ee16e9",
  name: "Transit Test",
  primary_profile: "transit",
  secondary_profiles: [],
  capabilities: ["cases", "declaration", "documents", "tariff", "taxes"],
  declaration_basis: "profile",
  habilitations: [],
  country_code: "GA",
  default_locale: "fr",
  active: true,
  is_demo: false,
  max_users: 2,
  max_agencies: 1,
  row_version: 1,
  members: 2,
  agencies: 1,
  pending_invitations: 0,
  admin_invitation: null,
  created_at: new Date().toISOString(),
  administrators: [{ full_name: "Admin Test", email: "admin@example.test", active: true, mfa_enabled: true }],
  history: [],
};

afterEach(() => vi.restoreAllMocks());

describe("Console plateforme : gestion des sociétés", () => {
  it("affiche un quota complet puis laisse l'exploitant l'augmenter avec motif et version", async () => {
    const fetcher = vi.spyOn(globalThis, "fetch").mockImplementation((request, init) => {
      const url = String(request);
      if (url.endsWith("/platform/organizations/" + company.id)) {
        if (init?.method === "PATCH") {
          const data = JSON.parse(String(init.body));
          return Promise.resolve(new Response(JSON.stringify({
            ...company, max_users: data.max_users, row_version: 2,
          }), { status: 200, headers: { "Content-Type": "application/json" } }));
        }
        return Promise.resolve(new Response(JSON.stringify(company), {
          status: 200, headers: { "Content-Type": "application/json" },
        }));
      }
      return Promise.resolve(new Response("{}", { status: 200, headers: { "Content-Type": "application/json" } }));
    });

    render(<I18nProvider><CompanyManagement items={[company]} onRefresh={() => {}} onRenew={() => {}}
      onState={() => {}} /></I18nProvider>);

    expect(screen.getByText(/2 \/ 2/)).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Gérer" }));
    const input = await screen.findByRole("spinbutton", { name: "Limite d'utilisateurs" });
    // La fiche chargée remplit le formulaire : attendre son arrivée avant de saisir, sinon elle écrase la saisie.
    await screen.findByText("Admin Test");
    fireEvent.change(input, { target: { value: "5" } });
    fireEvent.change(screen.getByRole("textbox", { name: "Motif de la modification" }), {
      target: { value: "Demande du client par téléphone" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Enregistrer les capacités" }));

    await waitFor(() => expect(fetcher.mock.calls.some(([url, init]) => {
      if (!String(url).endsWith("/platform/organizations/" + company.id) || init?.method !== "PATCH") return false;
      const body = JSON.parse(String(init.body));
      return body.max_users === 5 && body.max_agencies === 1 && body.row_version === 1 &&
        body.reason === "Demande du client par téléphone";
    })).toBe(true));
    expect(await screen.findByText("Admin Test")).toBeInTheDocument();
  });

  it("demande une confirmation avant de suspendre une société", () => {
    const onState = vi.fn();
    render(<I18nProvider><CompanyManagement items={[company]} onRefresh={() => {}} onRenew={() => {}}
      onState={onState} /></I18nProvider>);
    fireEvent.click(screen.getByRole("button", { name: "Suspendre" }));
    expect(onState).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole("button", { name: "Confirmer" }));
    expect(onState).toHaveBeenCalledWith(company, "suspend");
  });
});

describe("Console plateforme : métiers et habilitations (MET-02, MET-03)", () => {
  it("n'ouvre pas la déclaration à un importateur et enregistre une habilitation à vérifier", async () => {
    const importer: PlatformCompanyDetail = {
      ...company, primary_profile: "importer", capabilities: ["cases", "documents", "estimates", "tariff", "taxes"],
      declaration_basis: null,
    };
    const calls: { url: string; method?: string; body?: unknown }[] = [];
    vi.spyOn(globalThis, "fetch").mockImplementation((request, init) => {
      const url = String(request);
      calls.push({ url, method: init?.method, body: init?.body ? JSON.parse(String(init.body)) : undefined });
      const json = (data: unknown, status = 200) =>
        Promise.resolve(new Response(JSON.stringify(data), { status, headers: { "Content-Type": "application/json" } }));
      if (url.endsWith("/habilitations") && init?.method === "POST") {
        return json({ ...importer, habilitations: [{ id: "h1", kind: "own_account", country_code: "GA", reference: "GA-FIC-1",
          valid_from: null, valid_until: null, status: "declared", note: "", verified_at: null, row_version: 1,
          created_at: new Date().toISOString() }] }, 201);
      }
      if (url.endsWith("/platform/organizations/" + company.id)) return json(importer);
      if (url.includes("/auth/csrf")) return Promise.resolve(new Response(null, { status: 204 }));
      return json([]);
    });
    render(<I18nProvider><CompanyManagement items={[importer]} onRefresh={() => undefined} onState={() => undefined} onRenew={() => undefined} /></I18nProvider>);
    fireEvent.click(screen.getByRole("button", { name: /Gérer/ }));
    expect(await screen.findByText("Pas de préparation de déclaration")).toBeTruthy();
    fireEvent.change(screen.getByRole("combobox", { name: "Type d'habilitation" }), { target: { value: "own_account" } });
    fireEvent.change(screen.getByRole("textbox", { name: "Référence de l'acte" }), { target: { value: "GA-FIC-1" } });
    fireEvent.click(screen.getByRole("button", { name: "Enregistrer l'habilitation" }));
    expect(await screen.findByText("À vérifier")).toBeTruthy();
    const posted = calls.find((c) => c.method === "POST" && c.url.endsWith("/habilitations"));
    expect(posted?.body).toMatchObject({ kind: "own_account", country_code: "GA", reference: "GA-FIC-1" });
    // Sans motif, l'exploitant ne peut pas marquer l'habilitation vérifiée.
    expect((screen.getByRole("button", { name: "Vérifiée" }) as HTMLButtonElement).disabled).toBe(true);
  });
});
