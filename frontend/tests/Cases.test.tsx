import { render as baseRender, screen, fireEvent, waitFor, cleanup } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { Cases } from "../src/Cases";
import { CaseDetailView, decimalInput } from "../src/CaseDetail";
import { addDecimals, fmtAmount, fmtQty } from "../src/ui";
import { guessUsage } from "../src/NewCase";
import type { ReactElement } from "react";
import { I18nProvider } from "../src/i18n";

const render = (ui: ReactElement) => baseRender(ui, { wrapper: I18nProvider });

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
  window.location.hash = "";
});

function mockApi() {
  return vi.spyOn(globalThis, "fetch").mockImplementation((input) => {
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
}

describe("Dossiers", () => {
  it("garde les codes en texte et convertit la virgule décimale", () => {
    expect(decimalInput("1 500,25")).toBe("1500.25");
    expect(decimalInput("")).toBeNull();
    expect(decimalInput("0101")).toBe("0101");
    expect(fmtAmount("61187.5")).toBe("61\u202f187,50");
    expect(fmtAmount("-27.5")).toBe("-27,50");
    expect(fmtAmount("12.345")).toBe("12,345");
    expect(fmtAmount(null)).toBe("");
    expect(fmtQty("2.500")).toBe("2,5");
    expect(addDecimals(["57500.00", "3400", "287.5"])).toBe("61187.50");
    expect(addDecimals(["0.1", "0.2"])).toBe("0.3");
    expect(addDecimals(["-10.05", "2"])).toBe("-8.05");
    expect(fmtQty("1000")).toBe("1\u202f000");
  });

  it("devine le rôle d'une pièce d'après son nom, sans rien imposer", () => {
    expect(guessUsage("INV-2026-0017.pdf")).toBe("invoice");
    expect(guessUsage("Facture FE-0417.pdf")).toBe("invoice");
    expect(guessUsage("BL-2026-0456.pdf")).toBe("transport");
    expect(guessUsage("Packing-List-0017.pdf")).toBe("packing_list");
    expect(guessUsage("CO-EU-2026-0009.pdf")).toBe("origin");
    expect(guessUsage("photo.jpg")).toBe("other");
  });

  it("ouvre un dossier depuis la liste", async () => {
    // Vue équipe par défaut : chaque dossier est une carte du tableau par état.
    mockApi();
    render(<Cases membership={membership} me={{ id: "u1" }} />);
    fireEvent.click(await screen.findByRole("button", { name: /DOS-2026-0001/ }));
    expect(window.location.hash).toBe("#/dossiers/c1");
  });

  it("range les dossiers par état réel et sépare les archives", async () => {
    mockApi();
    render(<Cases membership={membership} me={{ id: "u1" }} />);
    await screen.findByRole("button", { name: /DOS-2026-0001/ });
    for (const label of ["Brouillons", "En préparation", "À corriger", "À valider", "Validés en interne"])
      expect(screen.getByRole("region", { name: label })).toBeInTheDocument();
    fireEvent.click(screen.getByRole("tab", { name: /Archives/ }));
    expect(await screen.findByText("Aucun dossier archivé.")).toBeInTheDocument();
  });

  it("liste les manques du dossier dans l'aperçu, sans calcul ni export inventés", async () => {
    mockApi();
    render(<CaseDetailView caseId="c1" tab="apercu" membership={membership} me={{ id: "u1" }} />);
    expect(await screen.findByText("Importateur à renseigner.", { exact: false })).toBeInTheDocument();
    // Rien n'est compté comme fait sans calcul soumis ni fichier généré.
    const calc = screen.getByRole("button", { name: "Étape 4 : Calcul" }).closest("li")!;
    const exp = screen.getByRole("button", { name: "Étape 6 : Export" }).closest("li")!;
    expect(calc).toHaveTextContent("droits et taxes à vérifier");
    expect(exp).toHaveTextContent("PDF et Excel");
    expect(calc.className).not.toContain("step-done");
    expect(exp.className).not.toContain("step-done");
  });

  it("affiche le contrôle du code présent et envoie une confirmation motivée liée au contrôle", async () => {
    document.cookie = "csrftoken=tok";
    const fetchMock = mockApi();
    render(<CaseDetailView caseId="c1" tab="marchandises" membership={membership} me={{ id: "u1" }} />);
    expect(await screen.findByText("Retrouvé dans le référentiel")).toBeInTheDocument();
    expect(screen.getByText(/Édition publiée pour consultation historique/)).toBeInTheDocument();
    expect(screen.getAllByText("0101.10.00").length).toBeGreaterThan(0);
    expect(screen.getAllByText("À valider").length).toBeGreaterThan(0);
    fireEvent.change(screen.getByLabelText(/motif de la confirmation/i), { target: { value: "Conforme à la facture" } });
    fireEvent.click(screen.getByRole("button", { name: "Valider le code" }));
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

  it("confirme en une fois les codes reconnus, avec un seul motif, une décision par marchandise", async () => {
    document.cookie = "csrftoken=tok";
    const fetchMock = mockApi();
    render(<CaseDetailView caseId="c1" tab="marchandises" membership={membership} me={{ id: "u1" }} />);
    fireEvent.click(await screen.findByRole("button", { name: "Confirmer les codes reconnus (1)" }));
    expect(screen.getByText(/0101\.10\.00\./)).toBeInTheDocument();
    const reason = screen.getAllByLabelText(/motif de la confirmation/i).find((el) => el.closest(".bulk-confirm"))!;
    fireEvent.change(reason, { target: { value: "Codes conformes aux factures" } });
    fireEvent.submit(reason.closest("form")!);
    await waitFor(() => expect(fetchMock.mock.calls.some(([u]) => String(u).endsWith("/decisions"))).toBe(true));
    const call = fetchMock.mock.calls.find(([u]) => String(u).endsWith("/decisions"))!;
    expect(JSON.parse(String(call[1]!.body))).toEqual({
      action: "confirm",
      code_check_id: "chk1",
      node_id: null,
      reason: "Codes conformes aux factures",
      goods_line_version: 3,
    });
  });

  it("réunit les manques et les codes à traiter dans les contrôles", async () => {
    mockApi();
    render(<CaseDetailView caseId="c1" tab="controles" membership={membership} me={{ id: "u1" }} />);
    // 3 points du serveur, plus la facture absente (bloquante) et les trois pièces habituelles (informations).
    expect(await screen.findByText("Liste des contrôles (7)")).toBeInTheDocument();
    expect(screen.getAllByText("Facture commerciale manquante dans le dossier").length).toBeGreaterThan(0);
    expect(screen.getAllByText("Bloquant").length).toBeGreaterThan(0);
    expect(screen.getAllByText(/Marchandise 1 \(Chevaux fictifs\) : à valider 0101\.10\.00/).length).toBeGreaterThan(0);
  });
});
