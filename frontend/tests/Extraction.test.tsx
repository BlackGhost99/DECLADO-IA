import { render, screen, fireEvent, waitFor, cleanup } from "@testing-library/react";
import type { ReactElement } from "react";
import { I18nProvider } from "../src/i18n";

function renderWithLanguage(element: ReactElement) {
  localStorage.setItem("clairtransit.interface-locale", "fr");
  return render(<I18nProvider>{element}</I18nProvider>);
}
import { afterEach, describe, expect, it, vi } from "vitest";
import type { CaseDocument, CodeCheck, GoodsLine, Invoice, InvoiceLine } from "../src/api";
import { Divergences, ExtractionControls, Flags, LineEditor, OriginBadge, TotalsPanel, spanText } from "../src/Extraction";
import { ProposalsPanel, actionFor } from "../src/Proposals";
import { decimalInput } from "../src/CaseDetail";

function json(status: number, body: unknown) {
  return Promise.resolve(new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } }));
}

function bodyOf(mock: ReturnType<typeof vi.spyOn>, suffix: string) {
  const call = mock.mock.calls.find(([u]: unknown[]) => String(u).endsWith(suffix));
  return call ? JSON.parse(String((call[1] as RequestInit).body)) : undefined;
}

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

const span = { id: "s1", document_id: "d1", page: 2, bbox: [0.1, 0.14, 0.5, 0.16] as [number, number, number, number],
  page_size: [595, 842] as [number, number], rotation: 0, sheet: null, cell_range: null, excerpt: "3 000,00" };

const link: CaseDocument = {
  id: "cd1", usage: "invoice", usage_label: "Facture", added_by: { id: "u1", email: "a@x", full_name: "" },
  created_at: "", replaced_by_id: null, row_version: 1, latest_extraction: null,
  document: { id: "d1", original_name: "facture.pdf", mime: "application/pdf", type_label: "PDF", bytes: 1000, sha256: "ab",
    version: 1, supersedes_id: null, readability: "ok", readability_label: "Lisible", inspection_notes: [], previewable: true,
    uploaded_by: { id: "u1", email: "a@x", full_name: "" }, created_at: "" },
};

const job = (state: string) => ({ id: "j1", kind: "extraction", state, state_label: state, phase: "lecture",
  progress: { done: 1, total: 2 }, attempts: 1, error_code: null, error_message: null, hint: null, note: "" });

describe("Extraction", () => {
  it("dit de quelle information parle chaque signalement d'une ligne", () => {
    renderWithLanguage(<Flags flags={[
      { field: "origin_country", code: "MISSING", message: "Absent du document : à renseigner." },
      { field: "source_reference", code: "MISSING", message: "Absent du document : à renseigner." },
    ]} />);
    expect(screen.getByText(/Origine · Absent du document/)).toBeInTheDocument();
    expect(screen.getByText(/Réf\. fournisseur · Absent du document/)).toBeInTheDocument();
  });

  it("localise une valeur par page et zone, ou par feuille et cellule", () => {
    expect(spanText(span)).toBe("p. 2 · hauteur 14–16 %");
    expect(spanText({ ...span, page: null, bbox: null, sheet: "Facture", cell_range: "F7" })).toBe("Facture!F7");
    expect(spanText(null)).toBe("");
  });

  it("distingue une valeur lue, lue par OCR, déduite ou saisie", () => {
    const source = { observation_id: "o", run_id: "r", label: "Montant", raw: "3 000,00", status: "ok" as const,
      origin: "ocr" as const, confidence: 71, notes: [], span };
    renderWithLanguage(<OriginBadge origin="extracted" source={source} />);
    expect(screen.getByText("OCR · p. 2 · hauteur 14–16 %")).toHaveAttribute("title", expect.stringContaining("Confiance OCR 71"));
    cleanup();
    renderWithLanguage(<OriginBadge origin="manual" source={source} />);
    expect(screen.getByText("saisi")).toBeInTheDocument();
  });

  it("demande l'extraction, suit le travail puis recharge sans rien valider", async () => {
    document.cookie = "csrftoken=tok";
    let polls = 0;
    const fetchMock = vi.spyOn(globalThis, "fetch").mockImplementation((input) => {
      const url = String(input);
      if (url.endsWith("/case-documents/cd1/extractions")) return json(202, { id: "r1", job: job("queued") });
      if (url.endsWith("/jobs/j1")) return json(200, job(++polls < 2 ? "running" : "succeeded"));
      return json(404, {});
    });
    const onDone = vi.fn(() => Promise.resolve());
    renderWithLanguage(<ExtractionControls link={link} editable onDone={onDone} />);
    expect(screen.queryByRole("button", { name: "Relancer" })).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "Extraire" }));
    await waitFor(() => expect(onDone).toHaveBeenCalled(), { timeout: 4000 });
    expect(bodyOf(fetchMock, "/extractions")).toEqual({});
  });

  it("affiche l'échec et la solution de repli sans bloquer la saisie", () => {
    const failed = { ...link, latest_extraction: { id: "r1", attempt: 1, status: "failed", status_label: "Échec (relance possible)",
      parser: "ocr", options: { ocr: true }, warnings: [], error_message: "L'OCR n'est pas installé.",
      hint: "Saisir les lignes manuellement, ou demander l'installation de l'OCR.", job: job("failed") } } as unknown as CaseDocument;
    renderWithLanguage(<ExtractionControls link={failed} editable onDone={() => Promise.resolve()} />);
    expect(screen.getByText("L'OCR n'est pas installé.")).toBeInTheDocument();
    expect(screen.getByText(/Saisir les lignes manuellement/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Relancer" })).toBeInTheDocument();
  });

  it("montre l'écart de total sans le corriger, et les sous-totaux non additionnés", () => {
    renderWithLanguage(
      <TotalsPanel
        currency="EUR"
        totals={{ status: "gap", goods_lines: 2, goods_lines_without_amount: 0,
          components: { goods: "4205", fees: "0", discounts: "0", taxes: "0" }, computed_total: "4205", printed_total: "4300",
          gap: "95", explanations: [], subtotals_not_added: [{ label: "Sous-total page 1", amount: "350", page: 1 }] }}
      />,
    );
    expect(screen.getByText(/rien n'a été corrigé/)).toBeInTheDocument();
    expect(screen.getByText("95")).toBeInTheDocument();
    expect(screen.getByText(/Sous-total page 1 350/)).toBeInTheDocument();
  });

  it("présente une divergence et trace le choix de garder la valeur actuelle", async () => {
    document.cookie = "csrftoken=tok";
    const fetchMock = vi.spyOn(globalThis, "fetch").mockImplementation(() => json(200, {}));
    const invoice = { id: "i1", divergences: [{ id: "dv1", kind: "value", kind_label: "Valeur", invoice_line_id: "l1",
      line_ordinal: 1, field: "quantity", current_value: "3", extracted_value: "2", run_id: "r2", state: "open",
      state_label: "À trancher", resolved_by: null, resolved_at: null, resolution_reason: "", span }] } as unknown as Invoice;
    const act = vi.fn(async (a: () => Promise<unknown>) => { await a(); });
    renderWithLanguage(<Divergences invoice={invoice} editable act={act} />);
    expect(screen.getByText(/Ligne 1, quantité/)).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText("Motif"), { target: { value: "Bon de livraison" } });
    fireEvent.click(screen.getByRole("button", { name: "Garder la valeur actuelle" }));
    await waitFor(() => expect(bodyOf(fetchMock, "/divergences/dv1/resolve")).toEqual({ resolution: "keep", reason: "Bon de livraison" }));
  });

  it("n'envoie que les champs corrigés, avec le motif", async () => {
    document.cookie = "csrftoken=tok";
    const fetchMock = vi.spyOn(globalThis, "fetch").mockImplementation(() => json(200, {}));
    const line = { id: "l1", ordinal: 1, description_raw: "Chevaux", quantity: "2", unit: "U", unit_price: "1500", amount: "3000",
      origin_country: "FR", row_version: 4 } as unknown as InvoiceLine;
    const act = vi.fn(async (a: () => Promise<unknown>) => { await a(); });
    renderWithLanguage(<LineEditor line={line} act={act} toDecimal={decimalInput} onClose={() => undefined} />);
    fireEvent.change(screen.getByLabelText("quantité"), { target: { value: "3" } });
    fireEvent.change(screen.getByLabelText("Motif de la correction"), { target: { value: "3 chevaux livrés" } });
    fireEvent.click(screen.getByRole("button", { name: "Enregistrer la correction" }));
    await waitFor(() =>
      expect(bodyOf(fetchMock, "/invoice-lines/l1")).toEqual({ row_version: 4, correction_reason: "3 chevaux livrés", quantity: "3" }),
    );
  });
});

const missingCheck = { id: "chk2", observed_code: null, normalized_code: null, target_edition_id: "e1", recognition_status: "missing",
  is_current: true, findings: [] } as unknown as CodeCheck;

describe("Aide au classement", () => {
  it("choisit l'action selon l'état du contrôle", () => {
    expect(actionFor(missingCheck, { code: "42010000" })).toBe("classify");
    const incomplete = { ...missingCheck, recognition_status: "incomplete", normalized_code: "0101" } as CodeCheck;
    expect(actionFor(incomplete, { code: "01012100" })).toBe("complete");
    expect(actionFor(incomplete, { code: "42010000" })).toBe("replace");
    expect(actionFor({ ...missingCheck, recognition_status: "not_found" } as CodeCheck, { code: "42010000" })).toBe("replace");
  });

  it("explique chaque piste, indique l'absence d'IA et classe avec un motif lié à la proposition", async () => {
    document.cookie = "csrftoken=tok";
    const set = { id: "ps1", goods_line_id: "g1", edition_id: "e1", edition_label: "Jeu lot 3", trigger: "missing", query: "",
      producer: "recherche-referentiel 1.0", is_ai: false, is_current: true, created_at: "", created_by: "a@x",
      questions: ["De quelle matière la marchandise est-elle faite ?"],
      proposals: [{ id: "p1", rank: 1, node_id: "n42", code: "42010000", code_display: "4201.00.00", label: "Articles de sellerie",
        full_path: "42 › 4201", reasons: ["Termes communs avec la désignation : tapis, selle."], notes: [], distinguishing: [],
        retrieval_score: 0.1 }] };
    const fetchMock = vi.spyOn(globalThis, "fetch").mockImplementation((input) => {
      const url = String(input);
      if (url.endsWith("/proposals")) return json(200, { results: [set] });
      return json(201, {});
    });
    const goods = { id: "g1", description: "Tapis de selle", row_version: 2, latest_check: missingCheck } as unknown as GoodsLine;
    const act = vi.fn(async (a: () => Promise<unknown>) => { await a(); });
    renderWithLanguage(<ProposalsPanel goods={goods} editionId="e1" editable act={act} />);
    expect(await screen.findByText(/Termes communs avec la désignation/)).toBeInTheDocument();
    expect(screen.getByText(/sans IA/)).toBeInTheDocument();
    expect(screen.getByText(/De quelle matière/)).toBeInTheDocument();
    const button = screen.getByRole("button", { name: "Classer sous ce code" });
    expect(button).toBeDisabled();
    fireEvent.change(screen.getByLabelText(/Motif du choix/), { target: { value: "Article de sellerie" } });
    fireEvent.click(button);
    await waitFor(() =>
      expect(bodyOf(fetchMock, "/decisions")).toEqual({ action: "classify", code_check_id: "chk2", node_id: "n42",
        proposal_id: "p1", reason: "Article de sellerie", goods_line_version: 2 }),
    );
  });
});
