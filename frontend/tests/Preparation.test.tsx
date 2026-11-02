import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { Administration } from "../src/Administration";

const org = { id: "a", name: "Transit Alpha (fictif)", is_demo: true, timezone: "Africa/Libreville", default_locale: "fr" as const };
const json = (body: unknown, status = 200) =>
  Promise.resolve(new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } }));

afterEach(() => vi.restoreAllMocks());

function mockApi() {
  return vi.spyOn(globalThis, "fetch").mockImplementation((input, init) => {
    const url = String(input);
    if (url.endsWith("/organization/preparation-settings"))
      return json({ regime: init?.method === "PUT" ? "IM7" : "IM4 (fictif)", entry_office: "Owendo", updated_at: null, updated_by: "Admin" });
    if (url.endsWith("/organization/exchange-rates")) {
      if (init?.method === "POST") return json({}, 201);
      return json({ results: [{ id: "r1", currency: "USD", rate: "605.5", valid_from: "2026-10-01", source: "BEAC (fictif)", created_at: "", created_by: "Valid Ateur" }] });
    }
    return json({ results: [], count: 0 });
  });
}

describe("Administration : préparation des dossiers", () => {
  it("montre les valeurs par défaut et les cours, sans modification pour un déclarant", async () => {
    mockApi();
    render(<Administration membership={{ organization: org, roles: ["declarant"] }} initialTab="preparation" />);
    expect(await screen.findByDisplayValue("IM4 (fictif)")).toBeDisabled();
    expect(await screen.findByText("1 USD = 605.5 FCFA")).toBeInTheDocument();
    expect(screen.getByText("BEAC (fictif)")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Enregistrer/ })).toBeNull();
    expect(screen.queryByLabelText("Cours (FCFA pour 1 unité)")).toBeNull();
  });

  it("laisse un validateur ajouter un cours daté et sourcé", async () => {
    document.cookie = "csrftoken=tok";
    const fetchMock = mockApi();
    render(<Administration membership={{ organization: org, roles: ["validator"] }} initialTab="preparation" />);
    await screen.findByText("1 USD = 605.5 FCFA");
    fireEvent.change(screen.getByLabelText("Devise"), { target: { value: "cny" } });
    fireEvent.change(screen.getByLabelText("Cours (FCFA pour 1 unité)"), { target: { value: "84,2" } });
    fireEvent.change(screen.getByLabelText("En vigueur à partir du"), { target: { value: "2026-11-01" } });
    fireEvent.change(screen.getByLabelText("Source du taux"), { target: { value: "Banque (fictif)" } });
    fireEvent.submit(screen.getByLabelText("Devise").closest("form")!);
    await waitFor(() => expect(fetchMock.mock.calls.some(([, i]) => i?.method === "POST")).toBe(true));
    const call = fetchMock.mock.calls.find(([, i]) => i?.method === "POST")!;
    expect(JSON.parse(String(call[1]!.body))).toEqual({ currency: "CNY", rate: "84.2", valid_from: "2026-11-01", source: "Banque (fictif)" });
  });
});
