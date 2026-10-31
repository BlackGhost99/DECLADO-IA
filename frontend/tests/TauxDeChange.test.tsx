import { render as baseRender, screen, fireEvent, waitFor, cleanup } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { ReactElement } from "react";
import { CaseDetailView } from "../src/CaseDetail";
import { I18nProvider } from "../src/i18n";

const render = (ui: ReactElement) => baseRender(ui, { wrapper: I18nProvider });

const membership = {
  organization: { id: "a", name: "Transit Alpha (démo)", is_demo: true, timezone: "Africa/Libreville", default_locale: "fr" as const },
  roles: ["declarant" as const],
};
const edition = { id: "e1", label: "Jeu F CSV", publication_state: "consultation", warning: null };
const revision = {
  id: "r1", revision_no: 1, state: "draft", state_label: "Brouillon", mode: "demo", mode_label: "Démonstration",
  territory: "GA", planned_declaration_date: "2026-10-30", regime: "IM4", origin_country: "", is_editable: true, row_version: 4,
  prefilled: [],
  target_edition: edition, documents: [], invoices: [], goods_lines: [],
  completeness: { blocking: [], warnings: [], complete: true },
  status_note: "« Validé en interne » ne vaudra jamais acceptation par la douane.",
};
const detail = {
  id: "c1", reference: "DOS-2026-0003", title: "Préparation", importer: null, assigned_to: null,
  created_by: { id: "u1", email: "declarant@alpha.demo", full_name: "" }, created_at: "2026-10-30T10:00:00Z",
  row_version: 1, state: "draft", state_label: "Brouillon", mode: "demo", revision_no: 1, revision,
};

function json(status: number, body: unknown) {
  return Promise.resolve(new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } }));
}

const calc = {
  warning: "", demo: true, mode: "demo", rules_version: "1", taxes_version: 1, schedule: null, date: "2026-10-31",
  date_is_planned: true, provisional: false, provisional_reasons: [], exchange_rates: {}, missing_rates: ["USD"],
  pieces: { freight: [], insurance: [] }, articles: [], total_value: null, global_taxes: [],
  totals: { total: null, known_total: null, by_tax: {} }, notes: {},
};

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

describe("Taux de change saisi pour le dossier", () => {
  it("demande le taux d'une devise sans parité fixe et l'enregistre avec sa source", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockImplementation((input, init) => {
      const url = String(input);
      if (url.endsWith("/cases/c1")) return json(200, detail);
      if (url.endsWith("/cases/c1/calculation")) return json(200, calc);
      if (url.endsWith("/tariffs/editions")) return json(200, [edition]);
      if (url.endsWith("/revisions/r1") && init?.method === "PATCH") return json(200, revision);
      if (url.endsWith("/importers")) return json(200, { count: 0, results: [] });
      if (url.endsWith("/audit")) return json(200, { results: [] });
      return json(404, {});
    });
    render(<CaseDetailView caseId="c1" tab="calculs" membership={membership} me={{ id: "u1" }} />);
    expect(await screen.findByText(/Devise sans taux de change : USD/)).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText("1 USD en FCFA"), { target: { value: "602,15" } });
    fireEvent.change(screen.getByLabelText("Source du taux"), { target: { value: "Cours fictif" } });
    fireEvent.click(screen.getByRole("button", { name: "Enregistrer les taux" }));
    await waitFor(() => {
      const patch = fetchMock.mock.calls.find(([, init]) => init?.method === "PATCH");
      expect(patch).toBeDefined();
      expect(JSON.parse(String(patch![1]!.body))).toMatchObject({
        exchange_rates: { USD: { rate: "602.15", source: "Cours fictif" } },
        row_version: 4,
      });
    });
  });
});
