import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import type { ReactElement } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { CaseCalculation, TaxOverview } from "../src/api";
import { I18nProvider } from "../src/i18n";
import { CalcLinesTable, CalcTaxesTable, TaxesPanel } from "../src/Taxes";

function renderIn(element: ReactElement, locale = "fr") {
  localStorage.setItem("clairtransit.interface-locale", locale);
  return render(<I18nProvider>{element}</I18nProvider>);
}

function json(status: number, body: unknown) {
  return Promise.resolve(new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } }));
}

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

const row = (code: string, extra: Partial<TaxOverview["taxes"][number]> = {}): TaxOverview["taxes"][number] => ({
  code, label: code, base_kind: "value", scope: "article", common_rate: "1", distinct: 1, empty: 0, values: [["1", 10]],
  empty_means_none: false, status: "verified", amendment: null, note: "", ...extra,
});

function overview(canEdit: boolean): TaxOverview {
  return {
    schedule: { id: "s1", label: "Barème fictif", territory: "GA", source: "swd.xlsx", sheet: "TARIF", reference_sheet: "TEC",
      edition_id: "e1", imported_at: "2026-10-29T10:00:00Z", counts: { lines: 6 } },
    version: 1, rules_version: "2022-swd-1", can_edit: canEdit, formula: "",
    taxes: [
      row("DDI", { distinct: 4, values: [["10", 5], ["30", 4], ["20", 2], ["5", 1]] }),
      row("DA", { base_kind: "value_ddi", distinct: 2, values: [["25", 3], ["40", 1]], empty_means_none: true, status: "from_schedule" }),
      row("TCI"),
      row("RI", { scope: "declaration", common_rate: null, values: [], distinct: 0, status: "to_confirm" }),
      row("DSO", { values: [["3", 2], ["7.5", 1]], distinct: 2, status: "export_only" }),
    ],
    history: [], review: { tec_difference: 1, empty_tax: 2, national_subposition: 3 },
  };
}

describe("Taxes et règles", () => {
  it("montre le barème sans bouton Modifier pour une société, l'inconnu comme inconnu (TAX-03, T69)", async () => {
    vi.spyOn(globalThis, "fetch").mockImplementation(() => json(200, overview(false)));
    renderIn(<TaxesPanel />);
    const table = await screen.findByRole("table");
    expect(within(table).getByText("Droit de douane import").closest("tr")).toHaveTextContent("5 à 30 % selon le code");
    expect(within(table).getByText("Droit d'accise").closest("tr")).toHaveTextContent("valeur + DDI");
    expect(within(table).getByText("Redevance informatique").closest("tr")).toHaveTextContent("taux à confirmer");
    expect(within(table).getByText("Droit de sortie").closest("tr")).toHaveTextContent("Export seulement");
    expect(screen.queryByRole("button", { name: "Modifier" })).toBeNull();
    expect(screen.getByText(/Seul l'admin ClairTransit modifie un taux/)).toBeInTheDocument();
    expect(screen.getByText("Droit de douane différent du TEC 2022").closest("li")).toHaveTextContent("1");
  });

  it("l'admin ClairTransit modifie un taux unique pour tous les codes, daté et sourcé (TAX-04, T69)", async () => {
    document.cookie = "csrftoken=tok";
    const fetchMock = vi.spyOn(globalThis, "fetch").mockImplementation((_input, init) => {
      if ((init as RequestInit | undefined)?.method === "POST") return json(201, { sequence: 1 });
      return json(200, overview(true));
    });
    renderIn(<TaxesPanel />);
    const tci = (await screen.findByText("Taxe communautaire d'intégration")).closest("tr") as HTMLElement;
    fireEvent.click(within(tci).getByRole("button", { name: "Modifier" }));
    expect(screen.getByRole("radio", { name: /Tous les codes/ })).toBeChecked();
    fireEvent.change(screen.getByLabelText(/Nouveau taux/), { target: { value: "1,5" } });
    fireEvent.change(screen.getByLabelText(/Date d'effet/), { target: { value: "2027-01-01" } });
    fireEvent.change(screen.getByLabelText(/Référence du texte/), { target: { value: "Loi de finances fictive" } });
    fireEvent.change(screen.getByLabelText(/Motif/), { target: { value: "Essai fictif" } });
    fireEvent.click(screen.getByRole("button", { name: "Enregistrer la modification" }));
    await waitFor(() => expect(fetchMock.mock.calls.some(([, i]) => (i as RequestInit | undefined)?.method === "POST")).toBe(true));
    const [url, init] = fetchMock.mock.calls.find(([, i]) => (i as RequestInit | undefined)?.method === "POST")!;
    expect(String(url)).toMatch(/\/fiscal\/amendments$/);
    expect(JSON.parse(String((init as RequestInit).body))).toEqual({
      tax: "TCI", scope: "all", hs_code: "", rate: "1.5", effective_from: "2027-01-01",
      source_kind: "finance_law", source_reference: "Loi de finances fictive", reason: "Essai fictif",
    });
  });
});

const tax = (code: string, amount: string | null, rate: string | null, extra = {}) => ({
  code, base_kind: "value" as const, base: "1000", rate, amount, reason: amount === null ? "Taux inconnu." : "",
  rate_status: rate === null ? ("unknown" as const) : ("known" as const), source: "schedule" as const, cell: "G2", ...extra,
});

const calc: CaseCalculation = {
  warning: "", demo: true, mode: "demo", rules_version: "2022-swd-1", taxes_version: 1,
  schedule: { label: "Barème fictif", source: "swd.xlsx" }, date: "2026-10-29", date_is_planned: false,
  provisional: false, provisional_reasons: [], pieces: { freight: [], insurance: [] },
  articles: [{
    goods_line_id: "g1", ordinal: 1, description: "Selles fictives", hs_code: "42010000", code_status: "confirmed",
    value: { xaf: "549070", invoice: "549070", freight: null, insurance: null, notes: [] }, cumulative_rate: null,
    taxes: [
      tax("DDI", "54907", "10"), tax("DA", "0", "0", { rate_status: "none" }), tax("TVA", null, null),
      tax("TCI", "5491", "1"), tax("CCI", "2197", "0.4"), tax("OAD", "275", "0.05"), tax("CSS", null, null), tax("CAF", "1099", "0.2"),
    ],
    total: null, known_total: "63969", unknown: ["TVA", "CSS"],
  }],
  total_value: "549070",
  global_taxes: [tax("RI", null, null, { reason: "Taux à saisir par l'admin ClairTransit." })],
  totals: { total: null, known_total: "63969", by_tax: { DDI: "54907", DA: "0", TVA: null, TCI: "5491", CCI: "2197", OAD: "275", CSS: null, CAF: "1099", RI: null } },
  notes: {},
};

describe("Calcul d'un dossier", () => {
  it("affiche chaque taxe avec son taux et son montant, et une taxe inconnue sans zéro (TAX-05, TAX-06, T70)", () => {
    renderIn(<><CalcTaxesTable calc={calc} /><CalcLinesTable calc={calc} /></>);
    const [taxes, lines] = screen.getAllByRole("table");
    expect(within(taxes).getByText("Droit de douane import").closest("tr")).toHaveTextContent("10 %");
    expect(within(taxes).getByText("Droit de douane import").closest("tr")).toHaveTextContent("54 907 FCFA");
    expect(within(taxes).getByText("Taxe sur la valeur ajoutée").closest("tr")).toHaveTextContent("Taux inconnu.");
    expect(within(taxes).getByText("Droit d'accise").closest("tr")).toHaveTextContent("pas d'accise");
    expect(within(taxes).getByText("Redevance informatique").closest("tr")).toHaveTextContent("Taux à saisir");
    const article = within(lines).getByText("Selles fictives").closest("tr") as HTMLElement;
    expect(article).toHaveTextContent("4201.00.00");
    expect(article).toHaveTextContent("549 070");
    expect(article).not.toHaveTextContent(/Total.*0$/);
    expect(screen.getByText(/données fictives/)).toBeInTheDocument();
  });

  it("existe en arabe, sans traduire codes ni montants", () => {
    renderIn(<CalcTaxesTable calc={calc} />, "ar");
    expect(screen.getByText("رسم جمركي على الاستيراد").closest("tr")).toHaveTextContent("DDI");
    expect(screen.getByText("رسم جمركي على الاستيراد").closest("tr")).toHaveTextContent("54");
  });
});
