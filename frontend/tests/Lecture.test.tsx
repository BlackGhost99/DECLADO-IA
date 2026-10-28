import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import type { ReactElement } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { CaseDocument, DocumentField } from "../src/api";
import { DocumentFields, TypeNote } from "../src/CaseDetail";
import { I18nProvider } from "../src/i18n";
import { PieceTypeSelect, uploadChoice } from "../src/PieceTypeSelect";
import { readerOf } from "../src/pieceTypes";

function renderFr(element: ReactElement) {
  localStorage.setItem("clairtransit.interface-locale", "fr");
  return render(<I18nProvider>{element}</I18nProvider>);
}

function json(status: number, body: unknown) {
  return Promise.resolve(new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } }));
}

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

const user = { id: "u1", email: "a@x", full_name: "" };
const link: CaseDocument = {
  id: "cd1", usage: "invoice", usage_label: "Facture", added_by: user, created_at: "", replaced_by_id: null, row_version: 1,
  latest_extraction: null, document_type: null, type_mismatch: null,
  document: { id: "d1", original_name: "03_facture_assurance.pdf", mime: "application/pdf", type_label: "PDF", bytes: 1000,
    sha256: "ab", version: 1, supersedes_id: null, readability: "ok", readability_label: "Lisible", inspection_notes: [],
    previewable: true, uploaded_by: user, created_at: "" },
};
const insurance = { code: "insurance_invoice", label: "Facture d'assurance", label_en: "Insurance invoice" };

describe("Lecture des pièces", () => {
  it("choisit la lecture d'après le type, et aucune pour un type confirmé sans lecture (T57)", () => {
    expect(readerOf({ usage: "invoice", document_type: null })).toBe("invoice");
    expect(readerOf({ usage: "invoice", document_type: { ...insurance, source: "confirmed", evidence: {} } })).toBe("insurance");
    expect(readerOf({ usage: "transport", document_type: { code: "packing_list", label: "", label_en: "", source: "confirmed", evidence: {} } })).toBeNull();
    expect(readerOf({ usage: "other", document_type: null })).toBeNull();
  });

  it("propose d'abord la reconnaissance par le titre, puis les pièces demandées par la société (T55)", async () => {
    vi.spyOn(globalThis, "fetch").mockImplementation((input) => {
      const url = String(input);
      if (url.endsWith("/document-types")) return json(200, { results: [
        { code: "bill_of_lading", label_fr: "Connaissement", label_en: "Bill of lading", family: "transport" },
        { code: "insurance_invoice", label_fr: "Facture d'assurance", label_en: "Insurance invoice", family: "insurance" },
        { code: "packing_list", label_fr: "Liste de colisage", label_en: "Packing list", family: "packing" },
      ] });
      if (url.endsWith("/organization/document-policies")) return json(200, { results: [
        { document_type: "bill_of_lading", active: true }, { document_type: "insurance_invoice", active: true },
      ] });
      return json(404, {});
    });
    const onChange = vi.fn();
    renderFr(<PieceTypeSelect value="auto" onChange={onChange} label="Type" />);
    const requested = await screen.findByRole("group", { name: "Demandées par votre société" });
    expect(requested).toHaveTextContent("Facture d'assurance");
    expect(screen.getByRole("group", { name: "Autres types de pièce" })).toHaveTextContent("Liste de colisage");
    fireEvent.change(screen.getByRole("combobox", { name: "Type" }), { target: { value: "type:insurance_invoice" } });
    expect(uploadChoice(onChange.mock.calls[0][0])).toEqual({ usage: "auto", documentType: "insurance_invoice" });
    expect(uploadChoice("auto")).toEqual({ usage: "auto", documentType: "" });
  });

  it("signale un titre qui contredit le rôle choisi et confirme avec le titre lu pour motif (T57)", async () => {
    document.cookie = "csrftoken=tok";
    const fetchMock = vi.spyOn(globalThis, "fetch").mockImplementation(() => json(201, {}));
    const onChange = vi.fn(() => Promise.resolve());
    const mismatch = { ...insurance, evidence: { method: "title" as const, excerpt: "FACTURE D'ASSURANCE" } };
    renderFr(<TypeNote link={{ ...link, type_mismatch: mismatch }} editable onChange={onChange} />);
    expect(screen.getByRole("note")).toHaveTextContent("Le titre « FACTURE D'ASSURANCE » indique : Facture d'assurance. La pièce a été déposée comme « Facture ».");
    fireEvent.click(screen.getByRole("button", { name: "Utiliser ce type" }));
    await waitFor(() => expect(onChange).toHaveBeenCalled());
    const [url, init] = fetchMock.mock.calls[0];
    expect(String(url)).toMatch(/\/case-documents\/cd1\/confirm-type$/);
    expect(JSON.parse(String((init as RequestInit).body))).toEqual({ document_type: "insurance_invoice", reason: "Titre lu : « FACTURE D'ASSURANCE »" });
  });

  it("affiche les informations lues sur l'assurance, avec leur source, et l'inconnu comme inconnu (T54)", () => {
    const span = { id: "s1", document_id: "d1", page: 1, bbox: [0.1, 0.5, 0.3, 0.52] as [number, number, number, number],
      page_size: [595, 842] as [number, number], rotation: 0, sheet: null, cell_range: null, excerpt: "111,93" };
    const fields: DocumentField[] = [
      { field: "premium_total", label: "Prime totale", raw: "111,93", parsed: "111.93", status: "ok", origin: "read", notes: [], span },
      { field: "policy_number", label: "N° de police", raw: null, parsed: null, status: "missing", origin: "read", notes: ["Non trouvé dans la pièce."], span: null },
    ];
    renderFr(<DocumentFields fields={fields} onSource={() => undefined} />);
    expect(screen.getByText("Prime totale").closest(".field-row")).toHaveTextContent("111,93Voir la source (p. 1) Extrait");
    expect(screen.getByText("N° de police").closest(".field-row")).toHaveTextContent("—");
    expect(screen.getByText("N° de police").closest(".field-row")).not.toHaveTextContent("Non trouvé");
  });
});
