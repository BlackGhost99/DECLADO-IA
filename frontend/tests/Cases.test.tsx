import { render, screen, fireEvent, waitFor, cleanup } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { Cases } from "../src/Cases";
import { I18nProvider } from "../src/i18n";
import { decimalInput } from "../src/CaseDetail";

const membership = {
  organization: { id: "a", name: "Transit Alpha (démo)", is_demo: true, timezone: "Africa/Libreville", default_locale: "fr" as const },
  roles: ["declarant" as const],
};

const check = {
  id: "chk1",
  observed_code: "0101.10.00",
  observed_field: "HS Code",
  normalized_code: "01011000",
  target_edition_id: "e1",
  target_edition_label: "Jeu F CSV",
  recognition_status: "recognized",
  recognition_label: "Retrouvé dans le référentiel",
  node: { id: "n1", code: "01011000", code_display: "0101.10.00", label: "Chevaux", full_path: "01 › Chevaux", declarable: true },
  is_current: true,
  human_confirmation: "pending",
  operational_applicability: "unverified",
  findings: [{ code: "HISTORICAL_REFERENCE", severity: "blocking_for_operational_calculation", message: "Édition publiée pour consultation historique." }],
  checked_at: "2026-10-06T10:00:00Z",
  checked_by: "declarant@alpha.demo",
};

const revision = {
  id: "r1", revision_no: 1, state: "draft", state_label: "Brouillon", mode: "demo", mode_label: "Démonstration",
  territory: "GA", planned_declaration_date: null, regime: "", is_editable: true, row_version: 1,
  target_edition: { id: "e1", label: "Jeu F CSV", publication_state: "consultation", warning: "Consultation historique." },
  documents: [],
  invoices: [{
    id: "i1", ordinal: 1, supplier_name: "Fournisseur fictif", invoice_number: "F-1", invoice_date: null, currency: "EUR",
    incoterm: "", declared_total: null, document_id: null, row_version: 1,
    lines: [{
      id: "l1", ordinal: 1, source_reference: "12345678", description_raw: "Chevaux fictifs", quantity: "2", unit: "NMB",
      unit_price: "1500", amount: "3000", origin_country: "FR", entry_origin_label: "Saisi", evidence_document_id: null,
      evidence_page: null, evidence_note: "", row_version: 1, goods_line_ids: ["g1"], code_history: [],
      codes: [{ id: "o1", field_label: "HS Code", raw_code: "0101.10.00", normalized_code: "01011000", code_kind: "customs",
        code_kind_label: "Code douanier", created_by: "x", created_at: "", superseded_at: null }],
    }],
  }],
  goods_lines: [{
    id: "g1", ordinal: 1, description: "Chevaux fictifs", origin_country: "FR", regime: "", row_version: 3,
    sources: [{ invoice_line_id: "l1", invoice_ordinal: 1, line_ordinal: 1, assigned_quantity: "2", assigned_value: "3000" }],
    latest_check: check, decision: null, decision_count: 0,
  }],
  completeness: { blocking: [{ scope: "case", id: "c1", label: "DOS-2026-0001", field: "importer", message: "Importateur à renseigner." }], warnings: [], complete: false },
  status_note: "« Validé en interne » ne vaudra jamais acceptation par la douane.",
};

const detail = {
  id: "c1", reference: "DOS-2026-0001", title: "Chevaux", importer: null, assigned_to: null,
  created_by: { id: "u1", email: "declarant@alpha.demo", full_name: "" }, created_at: "2026-10-06T10:00:00Z",
  row_version: 1, state: "draft", state_label: "Brouillon", mode: "demo", revision_no: 1, revision,
};

function json(status: number, body: unknown) {
  return Promise.resolve(new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } }));
}

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

describe("Dossiers", () => {
  it("garde les codes en texte et convertit la virgule décimale", () => {
    expect(decimalInput("1 500,25")).toBe("1500.25");
    expect(decimalInput("")).toBeNull();
    expect(decimalInput("0101")).toBe("0101");
  });

  it("affiche le contrôle du code présent et envoie une confirmation motivée liée au contrôle", async () => {
    document.cookie = "csrftoken=tok";
    const fetchMock = vi.spyOn(globalThis, "fetch").mockImplementation((input) => {
      const url = String(input);
      if (url.includes("/cases?")) return json(200, { results: [detail], states: [["draft", "Brouillon"]] });
      if (url.endsWith("/cases/c1")) return json(200, detail);
      if (url.endsWith("/importers")) return json(200, { count: 0, results: [] });
      if (url.endsWith("/tariffs/editions")) return json(200, [revision.target_edition]);
      if (url.endsWith("/documents/limits")) return json(200, { max_bytes: 52428800, accepted: ["PDF (.pdf)"] });
      if (url.endsWith("/audit")) return json(200, { results: [] });
      if (url.endsWith("/decisions")) return json(201, revision.goods_lines[0]);
      return json(404, {});
    });
    render(<I18nProvider><Cases membership={membership} me={{ id: "u1" }} /></I18nProvider>);
    fireEvent.click(await screen.findByRole("button", { name: "DOS-2026-0001" }));
    expect(await screen.findByText("Retrouvé dans le référentiel")).toBeInTheDocument();
    expect(screen.getByText("Importateur à renseigner.", { exact: false })).toBeInTheDocument();
    expect(screen.getByText(/Édition publiée pour consultation historique/)).toBeInTheDocument();
    expect(screen.getAllByText("0101.10.00").length).toBeGreaterThan(0);
    fireEvent.change(screen.getByLabelText(/motif de la confirmation/i), { target: { value: "Conforme à la facture" } });
    fireEvent.click(screen.getByRole("button", { name: "Confirmer le code" }));
    await waitFor(() => expect(fetchMock.mock.calls.some(([u]) => String(u).endsWith("/decisions"))).toBe(true));
    const call = fetchMock.mock.calls.find(([u]) => String(u).endsWith("/decisions"))!;
    expect(JSON.parse(String(call[1]!.body))).toEqual({
      action: "confirm",
      code_check_id: "chk1",
      node_id: null,
      reason: "Conforme à la facture",
      goods_line_version: 3,
    });
  });
});
