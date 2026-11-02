import { render as baseRender, screen, fireEvent, waitFor, cleanup } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { ReactElement } from "react";
import { Supervision } from "../src/Supervision";
import { I18nProvider } from "../src/i18n";

const render = (ui: ReactElement) => baseRender(ui, { wrapper: I18nProvider });

const event = {
  id: "e1", at: "2026-11-02T09:00:00Z", category: "antivirus", level: "error", code: "MALWARE_DETECTED",
  message: "Signature malveillante détectée par ClamAV : fichier refusé.", organization: "Transit Alpha", actor: "agent",
  request_id: "abcdef123456", details: { extension: "pdf", bytes: 1200, sha256_prefix: "a1b2c3d4e5f6" },
};
const data = {
  period_days: 7, generated_at: "2026-11-02T10:00:00Z",
  antivirus: {
    probe: { state: "ok", engine: "ClamAV 1.5.4", signatures: "27800", signatures_date: "Mon Nov  2 08:00:00 2026", response_ms: 4, checked_at: "2026-11-02T10:00:00Z" },
    mode: "fail_closed", counts: { clean: 12, malware: 1, unavailable: 0 }, last_clean_at: "2026-11-02T09:30:00Z",
    last_test: null, events: [event],
  },
  reading: {
    engines: { pdf_text: true, xlsx: true, ocr: { available: false, version: "", languages: [] },
      ai: { name: null, label: null, model: null, configured: false, free_tier: false } },
    counts: { total: 10, succeeded: 9, failed: 1, running: 0, average_seconds: 2.5 },
    by_reader: [{ reader: "invoice", label: "Facture commerciale", count: 10, failed: 1 }],
    by_parser: [{ parser: "pdf_text", label: "Texte du PDF", count: 10 }],
    failures: [{ id: "r1", at: "2026-11-02T08:00:00Z", organization: "Transit Alpha", case_reference: "DOS-2026-0004",
      reader: "Facture commerciale", parser: "Texte du PDF", attempt: 1, error_code: "NO_TEXT", error_message: "Aucun texte lisible." }],
  },
  ai: {
    provider: { name: null, label: null, model: null, configured: false, free_tier: false }, organizations_enabled: 0,
    counts: { sent: 0 }, status_labels: { sent: "Envoyée" },
    totals: { input_tokens: null, output_tokens: null, cost_estimate: null, average_latency_ms: null, sent_chars: null },
    fields: [], recent: [],
  },
  rejections: [event],
  incidents: { server_errors: 0, refused_actions: 0, events: [], failed_jobs: [] },
  organizations: [{ id: "o1", name: "Transit Alpha", is_demo: false, cases: 3, documents: 12, readings: 9, reading_failures: 1,
    rejected_documents: 1, errors: 0, ai_sent: 0, last_activity: "2026-11-02T09:30:00Z" }],
};

function json(status: number, body: unknown) {
  return Promise.resolve(new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } }));
}

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

describe("Console > Supervision (T90-T93)", () => {
  it("montre l'état de l'antivirus, les refus, les échecs de lecture et lance l'essai EICAR", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockImplementation((input, init) => {
      const url = String(input);
      if (url.includes("/platform/supervision/antivirus-test") && init?.method === "POST")
        return json(200, { ok: true, at: "2026-11-02T10:01:00Z", steps: [
          { step: "eicar", ok: true, message: "Fichier d'essai EICAR détecté et refusé." },
          { step: "clean", ok: true, message: "Contenu sain accepté." }] });
      if (url.includes("/platform/supervision")) return json(200, data);
      if (url.endsWith("/auth/csrf")) return json(200, {});
      return json(404, {});
    });
    render(<Supervision />);
    expect((await screen.findAllByText("Actif, il répond")).length).toBeGreaterThan(0);
    expect(screen.getByText("ClamAV 1.5.4")).toBeInTheDocument();
    expect(screen.getByText(/27800/)).toBeInTheDocument();
    expect(screen.getByText(/Tesseract absent/)).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Lancer l'essai" }));
    expect(await screen.findByText("Fichier d'essai EICAR détecté et refusé.")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("tab", { name: /Pièces refusées/ }));
    expect(screen.getByText(/empreinte : a1b2c3d4e5f6/)).toBeInTheDocument();

    fireEvent.click(screen.getByRole("tab", { name: /Lecture des pièces/ }));
    expect(screen.getByText("DOS-2026-0004")).toBeInTheDocument();
    expect(screen.getByText(/Aucun texte lisible/)).toBeInTheDocument();

    fireEvent.change(screen.getByLabelText("Période"), { target: { value: "30" } });
    await waitFor(() => expect(fetchMock.mock.calls.some(([u]) => String(u).includes("days=30"))).toBe(true));
  });

  it("signale un antivirus qui ne répond pas", async () => {
    vi.spyOn(globalThis, "fetch").mockImplementation(() =>
      json(200, { ...data, antivirus: { ...data.antivirus, probe: { state: "unavailable", message: "ClamAV indisponible ou analyse interrompue.", checked_at: "2026-11-02T10:00:00Z" } } }));
    render(<Supervision />);
    expect((await screen.findAllByText("Ne répond pas")).length).toBeGreaterThan(0);
    expect(screen.getByText("ClamAV indisponible ou analyse interrompue.")).toBeInTheDocument();
  });
});
