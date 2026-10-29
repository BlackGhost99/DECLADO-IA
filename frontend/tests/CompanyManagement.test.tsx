import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { CompanyManagement } from "../src/CompanyManagement";
import type { PlatformCompanyDetail } from "../src/api";
import { I18nProvider } from "../src/i18n";

const company: PlatformCompanyDetail = {
  id: "7a5c1bac-d710-4ba4-9106-8f8df4ee16e9",
  name: "Transit Test",
  primary_profile: "transit",
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
