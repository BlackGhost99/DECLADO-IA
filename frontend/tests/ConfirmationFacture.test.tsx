import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { CaseDocument, Invoice, Revision } from "../src/api";
import { ExtractedPanel } from "../src/CaseDetail";
import { I18nProvider } from "../src/i18n";

function json(status: number, body: unknown) {
  return Promise.resolve(new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } }));
}

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

const user = { id: "u1", email: "a@x", full_name: "" };
const link = {
  id: "cd1", usage: "invoice", usage_label: "Facture", added_by: user, created_at: "", replaced_by_id: null, row_version: 1,
  document_type: null, type_mismatch: null,
  latest_extraction: { id: "r1", status: "succeeded", invoice_id: "i1", finished_at: null, fields: [], attempt: 1, parser: "pdf_text", warnings: [], options: { reader: "invoice" } },
  document: { id: "d1", original_name: "facture_fictive.pdf", mime: "application/pdf", type_label: "PDF", bytes: 1000, sha256: "ab", version: 1,
    supersedes_id: null, readability: "ok", readability_label: "Lisible", inspection_notes: [], previewable: true, uploaded_by: user, created_at: "" },
} as unknown as CaseDocument;
const invoice = {
  id: "i1", document_id: "cd1", row_version: 4, supplier_name: "Fournisseur fictif Ltd", buyer_name: "Importateur fictif SARL",
  invoice_number: "F-1", invoice_date: "2026-09-14", currency: "USD", declared_total: "100.00", incoterm: "CIF Owendo",
  field_origins: { supplier_name: "inferred" }, field_sources: {}, lines: [],
  review_flags: [{ field: "supplier_name", code: "INFERRED", message: "Émetteur lu en tête de la facture : à vérifier." }],
} as unknown as Invoice;
const revision = { invoices: [invoice], goods_lines: [], documents: [link] } as unknown as Revision;

function show() {
  localStorage.setItem("clairtransit.interface-locale", "fr");
  document.cookie = "csrftoken=tok";
  return render(
    <I18nProvider>
      <ExtractedPanel link={link} caseId="c1" caseVersion={7} revision={revision} importer={null} editable onChange={() => Promise.resolve()} onSource={() => {}} go={() => {}} />
    </I18nProvider>,
  );
}

type Call = [unknown, RequestInit | undefined];
const posted = (mock: { mock: { calls: unknown[][] } }, method: string) =>
  (mock.mock.calls as Call[]).filter(([, i]) => i?.method === method).map(([u, i]) => [String(u), JSON.parse(String(i?.body))]);

describe("Confirmer une valeur lue sur la facture (T72)", () => {
  it("confirme le fournisseur « à vérifier » en un clic, sans le retaper", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockImplementation(() => json(200, invoice));
    show();
    fireEvent.click(screen.getByRole("button", { name: "Confirmer" }));
    await waitFor(() => expect(posted(fetchMock, "POST")).toHaveLength(1));
    const [[url, body]] = posted(fetchMock, "POST");
    expect(url).toMatch(/\/invoices\/i1\/fields\/supplier_name\/confirm$/);
    expect(body).toEqual({ row_version: 4 });
  });

  it("corrige une valeur et rattache l'importateur lu en créant sa fiche", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockImplementation((input, init) => {
      const url = String(input);
      if (url.endsWith("/importers") && (init as RequestInit | undefined)?.method === "POST") return json(201, { id: "imp9", name: "Importateur fictif SARL" });
      if (url.endsWith("/importers")) return json(200, { results: [] });
      return json(200, {});
    });
    show();
    fireEvent.click(screen.getByRole("button", { name: /Corriger/ }));
    fireEvent.change(screen.getByLabelText("Valeur : Fournisseur"), { target: { value: "Fournisseur corrigé" } });
    fireEvent.click(screen.getByRole("button", { name: "Enregistrer" }));
    await waitFor(() => expect(posted(fetchMock, "PATCH")).toHaveLength(1));
    expect(posted(fetchMock, "PATCH")[0]).toEqual([expect.stringMatching(/\/invoices\/i1$/), { supplier_name: "Fournisseur corrigé", row_version: 4 }]);

    fireEvent.click(screen.getByRole("button", { name: "Rattacher" }));
    const select = await screen.findByRole("combobox", { name: "Importateur du dossier" });
    await screen.findByRole("option", { name: "Créer la fiche « Importateur fictif SARL »" });
    fireEvent.change(select, { target: { value: "new" } });
    fireEvent.click(screen.getByRole("button", { name: "Enregistrer" }));
    await waitFor(() => expect(posted(fetchMock, "PATCH")).toHaveLength(2));
    expect(posted(fetchMock, "POST")[0]).toEqual([expect.stringMatching(/\/importers$/), { name: "Importateur fictif SARL" }]);
    expect(posted(fetchMock, "PATCH")[1]).toEqual([expect.stringMatching(/\/cases\/c1$/), { importer_id: "imp9", row_version: 7 }]);
  });
});
