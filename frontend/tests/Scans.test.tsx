import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { batchProgress, pageRange, ScanScreens } from "../src/Scans";
import type { ScanBatch, ScanPageInfo } from "../src/api";

const membership = {
  organization: { id: "a", name: "Transit Alpha (démo)", is_demo: true, timezone: "Africa/Libreville" },
  roles: ["declarant" as const],
};

const detail = {
  id: "c1", reference: "DOS-2026-0001", title: "Lot fictif", importer: { id: "i1", name: "Société Fictive Import Alpha" },
  assigned_to: null, created_by: { id: "u1", email: "declarant@alpha.demo", full_name: "" }, created_at: "2026-10-24T08:00:00Z",
  row_version: 1, state: "draft", state_label: "Brouillon", mode: "demo", revision_no: 1,
  revision: { id: "r1", is_editable: true, mode_label: "Démonstration", documents: [], invoices: [], goods_lines: [] },
};

const user = { id: "u1", email: "declarant@alpha.demo", full_name: "Déclarant Alpha" };

function page(n: number, extra: Partial<ScanPageInfo> = {}): ScanPageInfo {
  return {
    id: `p${n}`, number: n, source_name: "scan-arrivage.pdf", source_page: n, state: "read", state_label: "Lue", rotation: 0,
    blank: false, hard_to_read: false, removed: "", removed_label: "", replaces_id: null, title: "", reference: "",
    page_marker: "", text_origin: "ocr", notes: [], piece_id: null, has_image: true, ...extra,
  };
}

const batch: ScanBatch = {
  id: "b1", case_id: "c1", source: "scanner", source_label: "Scanner", label: "scan-arrivage.pdf", state: "to_sort",
  state_label: "À trier", created_by: user, created_at: "2026-10-24T08:10:00Z", attached_at: null,
  job: { state: "succeeded", phase: "terminé", progress: { done: 5, total: 5 }, error_message: null },
  counts: { pages: 5, pending: 0, kept: 4, unclassified: 1, blank_removed: 1, hard_to_read: 1, pieces: 2 },
  sources: [{ id: "s1", name: "scan-arrivage.pdf", page_count: 5, error: "" }],
  pieces: [
    { id: "k1", ordinal: 1, usage: "invoice", usage_label: "Facture", reason: "titre « Facture » reconnu en haut de la page 1, n° FE-2026-0417",
      usage_by_user: false, page_ids: ["p1", "p2"], case_document: null },
    { id: "k2", ordinal: 2, usage: "transport", usage_label: "Document de transport", reason: "titre « Connaissement » reconnu en haut de la page 4",
      usage_by_user: false, page_ids: ["p4"], case_document: null },
  ],
  pages: [
    page(1, { piece_id: "k1", title: "Facture", reference: "FE-2026-0417" }),
    page(2, { piece_id: "k1", hard_to_read: true, notes: ["Texte peu lisible : reprendre la page si elle compte pour le dossier."] }),
    page(3, { blank: true, removed: "blank", removed_label: "Page blanche retirée" }),
    page(4, { piece_id: "k2", title: "Connaissement" }),
    page(5),
  ],
  max_pages: 300,
};

function json(status: number, body: unknown) {
  return Promise.resolve(new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } }));
}

function mockApi(current: ScanBatch = batch) {
  return vi.spyOn(globalThis, "fetch").mockImplementation((input, init) => {
    const url = String(input);
    if (url.endsWith("/cases/c1")) return json(200, detail);
    if (url.endsWith("/cases/c1/scan-batches")) {
      if (init?.method === "POST") return json(201, { ...current, id: "b2", source: "camera", state: "open" });
      return json(200, { results: [current], max_pages: 300 });
    }
    if (url.endsWith("/scan-batches/b1")) return json(200, current);
    if (url.endsWith("/scan-batches/b1/attach")) return json(200, { ...current, state: "attached" });
    if (url.includes("/scan-pages/") || url.includes("/scan-pieces/")) return json(200, current);
    return json(404, {});
  });
}

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
  window.location.hash = "";
});

// T45 (NUM-01 à NUM-06) : écrans de numérisation.
describe("Numérisation", () => {
  it("écrit les pages d'une pièce comme sur le papier", () => {
    expect(pageRange([3])).toBe("p. 3");
    expect(pageRange([5, 4])).toBe("p. 4 et 5");
    expect(pageRange([1, 2, 3])).toBe("p. 1 à 3");
    expect(pageRange([1, 3])).toBe("p. 1, 3");
    expect(batchProgress(batch)).toEqual({ tone: "amber", text: "À trier : 1 page non classée" });
    expect(batchProgress({ ...batch, state: "processing", job: { ...batch.job!, state: "running", progress: { done: 2, total: 5 } } }).text).toBe(
      "Lecture du texte : page 2 sur 5",
    );
  });

  it("propose trois façons d'ajouter les pièces et liste les lots du dossier", async () => {
    const fetchMock = mockApi();
    render(<ScanScreens caseId="c1" rest={[]} membership={membership} />);
    expect(await screen.findByRole("heading", { name: "Ajouter les pièces du dossier" })).toBeInTheDocument();
    for (const name of ["Lot du scanner", "Téléphone ou webcam", "Fichiers déjà prêts"]) {
      expect(screen.getByRole("heading", { name })).toBeInTheDocument();
    }
    expect(await screen.findByText("À trier : 1 page non classée")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Trier le lot" }));
    expect(window.location.hash).toBe("#/dossiers/c1/numerisation/b1");
    fireEvent.click(screen.getByRole("button", { name: /Commencer la prise de vue/ }));
    await waitFor(() => expect(window.location.hash).toBe("#/dossiers/c1/numerisation/b2/photos"));
    const create = fetchMock.mock.calls.find(([u, i]) => String(u).endsWith("/scan-batches") && i?.method === "POST")!;
    expect(JSON.parse(String(create[1]!.body))).toEqual({ source: "camera", label: "" });
  });

  it("montre les pièces proposées avec leur raison, les pages à classer et la page à reprendre", async () => {
    mockApi();
    render(<ScanScreens caseId="c1" rest={["b1"]} membership={membership} />);
    expect(await screen.findByRole("heading", { name: "Trier le lot : 5 pages, 2 pièces proposées" })).toBeInTheDocument();
    expect(screen.getByText("Proposé : titre « Facture » reconnu en haut de la page 1, n° FE-2026-0417")).toBeInTheDocument();
    expect(screen.getByText("p. 1 et 2")).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Pages non classées" })).toBeInTheDocument();
    // La page peu lisible est ouverte d'office, avec ses actions.
    expect(screen.getByRole("heading", { name: "Page 2" })).toBeInTheDocument();
    expect(screen.getByText("Peu lisible, à reprendre")).toBeInTheDocument();
    for (const name of [/Reprendre la page/, /Pivoter/, /Couper la pièce ici/, /Retirer du lot/]) {
      expect(screen.getByRole("button", { name })).toBeInTheDocument();
    }
    expect(screen.getByText(/1 page retirée du lot/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Rattacher 2 pièces au dossier/ })).toBeEnabled();
  });

  it("envoie les gestes de l'agent au serveur", async () => {
    const fetchMock = mockApi();
    render(<ScanScreens caseId="c1" rest={["b1"]} membership={membership} />);
    await screen.findByRole("heading", { name: "Page 2" });
    fireEvent.click(screen.getByRole("button", { name: /Pivoter/ }));
    fireEvent.click(screen.getByRole("button", { name: /Couper la pièce ici/ }));
    fireEvent.change(screen.getAllByRole("combobox", { name: "Type" })[1], { target: { value: "packing_list" } });
    await waitFor(() => expect(fetchMock.mock.calls.filter(([, i]) => i?.method && i.method !== "GET").length).toBe(3));
    const writes = fetchMock.mock.calls.filter(([, i]) => i?.method && i.method !== "GET").map(([u, i]) => [String(u), i!.method, i!.body]);
    expect(writes).toEqual([
      ["/api/v1/scan-pages/p2", "PATCH", JSON.stringify({ rotation: 90 })],
      ["/api/v1/scan-pages/p2/split", "POST", "{}"],
      ["/api/v1/scan-pieces/k2", "PATCH", JSON.stringify({ usage: "packing_list" })],
    ]);
  });

  it("affiche les pièces rattachées avec leur provenance", async () => {
    const link = (id: string, usage: string, label: string, name: string) => ({
      id, usage, usage_label: label, added_by: user, created_at: "2026-10-24T08:20:00Z", replaced_by_id: null, row_version: 1,
      document: { id: `d${id}`, original_name: name, mime: "application/pdf", bytes: 1000, version: 1, readability: "ok" },
      latest_extraction: usage === "invoice" ? { id: "x1", status: "queued", status_label: "En attente" } : null,
    });
    const attached = {
      ...batch,
      state: "attached" as const,
      pieces: [
        { ...batch.pieces[0], case_document: link("l1", "invoice", "Facture", "DOS-2026-0001 Facture.pdf") },
        { ...batch.pieces[1], case_document: link("l2", "transport", "Document de transport", "DOS-2026-0001 Document de transport.pdf") },
      ],
    } as unknown as ScanBatch;
    mockApi(attached);
    render(<ScanScreens caseId="c1" rest={["b1"]} membership={membership} />);
    expect(await screen.findByRole("heading", { name: "Pièces du dossier" })).toBeInTheDocument();
    expect(screen.getByText("Numérisé · lot scan-arrivage.pdf · p. 1 et 2")).toBeInTheDocument();
    expect(screen.getByText(/2 pièces rattachées depuis le lot scan-arrivage.pdf. 1 page non classée reste dans le lot. La lecture de 1 facture a démarré./)).toBeInTheDocument();
    expect(screen.getByText("En attente")).toBeInTheDocument();
  });
});
