import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import type { ReactElement } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { AISettings, AIState, DocumentField, Importer } from "../src/api";
import { AINote, DocumentFields } from "../src/CaseDetail";
import { I18nProvider } from "../src/i18n";
import { AISettingsPanel, ImporterAIChoice } from "../src/OnlineAI";

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

const span = { id: "s1", document_id: "d1", page: 1, bbox: [0.1, 0.5, 0.3, 0.52] as [number, number, number, number],
  page_size: null, rotation: 0, sheet: null, cell_range: null, excerpt: "Total pieces shipped 12 PALLETS" };
const missing = (field: string, label: string): DocumentField => ({
  field, label, raw: null, parsed: null, status: "missing", origin: "read", notes: [], span: null, proposal: null, entered: null,
});

describe("IA en ligne : écrans (T61 à T63)", () => {
  it("montre la proposition de l'IA à vérifier, avec son extrait, et l'accepte sur demande (T62)", async () => {
    document.cookie = "csrftoken=tok";
    const fetchMock = vi.spyOn(globalThis, "fetch").mockImplementation(() => json(200, {}));
    const onChange = vi.fn(() => Promise.resolve());
    const fields: DocumentField[] = [
      { ...missing("packages", "Colis"), proposal: { raw: "12 PALLETS", parsed: "12 PALLETS", status: "ok", notes: [],
        excerpt: "Total pieces shipped 12 PALLETS", span, created_at: "2026-10-28T09:38:00Z" } },
      { ...missing("measurement", "Volume"), entered: { raw: "24.5 CBM", from_ai: true, by: "Agent Alpha", at: "" } },
      missing("freight_terms", "Conditions de fret"),
    ];
    renderFr(<DocumentFields fields={fields} onSource={() => {}} runId="r1" editable onChange={onChange} />);
    const packages = screen.getByText("Colis").closest(".field-row") as HTMLElement;
    expect(packages).toHaveTextContent("12 PALLETS");
    expect(packages).toHaveTextContent("Extrait cité par l'IA : « Total pieces shipped 12 PALLETS »");
    expect(packages).toHaveTextContent("Proposé par l'IA");
    expect(packages).toHaveTextContent("À vérifier");
    expect(screen.getByText("Volume").closest(".field-row")).toHaveTextContent("Proposition de l'IA retenue par Agent Alpha");
    expect(within(screen.getByText("Conditions de fret").closest(".field-row") as HTMLElement).getByRole("button", { name: "Saisir" })).toBeInTheDocument();
    fireEvent.click(within(packages).getByRole("button", { name: "Accepter" }));
    await waitFor(() => expect(onChange).toHaveBeenCalled());
    const [url, init] = fetchMock.mock.calls[0];
    expect(String(url)).toMatch(/\/extraction-runs\/r1\/fields\/packages\/decision$/);
    expect(JSON.parse(String((init as RequestInit).body))).toEqual({ action: "accept", value: "" });
  });

  it("laisse l'agent saisir une information que ni la lecture ni l'IA n'ont trouvée (T62)", async () => {
    document.cookie = "csrftoken=tok";
    const fetchMock = vi.spyOn(globalThis, "fetch").mockImplementation(() => json(200, {}));
    const onChange = vi.fn(() => Promise.resolve());
    renderFr(<DocumentFields fields={[missing("freight_terms", "Conditions de fret")]} onSource={() => {}} runId="r1" editable onChange={onChange} />);
    fireEvent.click(screen.getByRole("button", { name: "Saisir" }));
    fireEvent.change(screen.getByRole("textbox", { name: "Valeur : Conditions de fret" }), { target: { value: "Selon charte-partie" } });
    fireEvent.click(screen.getByRole("button", { name: "Enregistrer" }));
    await waitFor(() => expect(onChange).toHaveBeenCalled());
    expect(JSON.parse(String((fetchMock.mock.calls[0][1] as RequestInit).body))).toEqual({ action: "set", value: "Selon charte-partie" });
  });

  it("dit qu'une pièce n'a pas été envoyée quand le client refuse, sans bouton (T61)", () => {
    const ai: AIState = { last: { status: "client_refused", status_label: "", trigger: "auto", provider: null, provider_label: null,
      model: null, free_tier: false, requested: 3, found: 0, rejected: 0, error_message: null, created_at: "2026-10-28T09:38:00Z" },
      client_refused: true, can_complete: false, missing: [], proposals: [] };
    renderFr(<AINote linkId="cd1" ai={ai} editable onChange={() => Promise.resolve()} />);
    expect(screen.getByRole("note")).toHaveTextContent("Non envoyée à l'IA : le client du dossier refuse la lecture par IA.");
    expect(screen.queryByRole("button", { name: /Compléter avec l'IA/ })).toBeNull();
  });

  it("propose « Compléter avec l'IA » en mode sur demande et l'envoie (T62)", async () => {
    document.cookie = "csrftoken=tok";
    const fetchMock = vi.spyOn(globalThis, "fetch").mockImplementation(() => json(200, {}));
    const onChange = vi.fn(() => Promise.resolve());
    const ai: AIState = { last: null, client_refused: false, can_complete: true, missing: ["packages", "measurement"], proposals: [] };
    renderFr(<AINote linkId="cd1" ai={ai} editable onChange={onChange} />);
    expect(screen.getByText(/pour chercher 2 information\(s\) non trouvée\(s\)/)).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /Compléter avec l'IA/ }));
    await waitFor(() => expect(onChange).toHaveBeenCalled());
    expect(String(fetchMock.mock.calls[0][0])).toMatch(/\/case-documents\/cd1\/ai-completion$/);
  });

  const settings: AISettings = {
    enabled: false, mode: "auto", monthly_cap: 200, row_version: 0,
    provider: { name: null, label: null, model: null, configured: false, free_tier: false },
    usage: { month_start: "2026-10-01", sent: 0, cap: 200, cost_estimate: "0" },
    refusing_clients: [], journal: [],
  };

  it("grise l'interrupteur tant qu'aucune clé n'est posée sur le serveur (T63)", async () => {
    vi.spyOn(globalThis, "fetch").mockImplementation(() => json(200, settings));
    renderFr(<AISettingsPanel organizationName="Transit Alpha" onManageClients={() => {}} />);
    const toggle = await screen.findByRole("checkbox", { name: "Désactivée" });
    expect(toggle).toBeDisabled();
    expect(screen.getByText(/Aucune clé d'IA n'est posée sur le serveur/)).toBeInTheDocument();
    expect(screen.getByText("Absente")).toBeInTheDocument();
  });

  it("active l'IA, signale l'offre gratuite et un coût inconnu, sans jamais afficher la clé (T63)", async () => {
    document.cookie = "csrftoken=tok";
    const configured: AISettings = { ...settings,
      provider: { name: "gemini", label: "Google Gemini", model: "gemini-2.5-flash-lite", configured: true, free_tier: true },
      refusing_clients: [{ id: "i2", name: "Société Fictive Import Beta", refused_at: "2026-10-27T10:00:00Z", refused_by: "Admin Alpha" }],
      journal: [{ id: "j1", created_at: "2026-10-28T09:38:00Z", case_id: "c1", case_reference: "DOS-2026-0007", file_name: "bl.pdf",
        usage: "transport", detected_type: null, status: "sent", status_label: "Envoyée", trigger: "auto", provider: "gemini",
        model: "gemini-2.5-flash-lite", free_tier: true, requested: 3, found: 2, rejected: 0, cost_estimate: "0", error_message: null, by: "Agent" }],
    };
    const fetchMock = vi.spyOn(globalThis, "fetch").mockImplementation((_input, init) =>
      json(200, init?.method === "PUT" ? { ...configured, enabled: true, row_version: 1 } : configured));
    renderFr(<AISettingsPanel organizationName="Transit Alpha" onManageClients={() => {}} />);
    expect(await screen.findByText(/Offre gratuite d'essai : le fournisseur peut réutiliser/)).toBeInTheDocument();
    expect(screen.getByText("Société Fictive Import Beta")).toBeInTheDocument();
    expect(screen.getByText("DOS-2026-0007").closest("tr")).toHaveTextContent("Envoyée");
    fireEvent.click(screen.getByRole("checkbox", { name: "Désactivée" }));
    expect(await screen.findByText("Activée pour Transit Alpha")).toBeInTheDocument();
    const put = fetchMock.mock.calls.find(([, init]) => init?.method === "PUT")!;
    expect(JSON.parse(String((put[1] as RequestInit).body))).toEqual({ enabled: true, mode: "auto", monthly_cap: 200, row_version: 0 });
    cleanup();
    vi.spyOn(globalThis, "fetch").mockImplementation(() => json(200, { ...configured, provider: { ...configured.provider, free_tier: false },
      usage: { ...configured.usage, cost_estimate: null } }));
    renderFr(<AISettingsPanel organizationName="Transit Alpha" onManageClients={() => {}} />);
    expect(await screen.findByText(/Coût estimé inconnu pour ce modèle/)).toBeInTheDocument();
  });

  const beta: Importer = { id: "i2", name: "Société Fictive Import Beta", identifiers: {}, contacts: [], address: "", notes: "",
    ai_refused: true, ai_refused_at: "2026-10-27T10:00:00Z", row_version: 2 };

  it("seul l'administrateur lève le refus d'un client (T61)", () => {
    renderFr(<ImporterAIChoice importer={beta} isAdmin={false} onSaved={() => {}} onClose={() => {}} />);
    expect(screen.getByRole("checkbox", { name: /Ce client refuse/ })).toBeDisabled();
    expect(screen.getByText("Seul un administrateur de la société peut lever ce refus.")).toBeInTheDocument();
  });

  it("un agent note le refus d'un client (T61)", async () => {
    document.cookie = "csrftoken=tok";
    const fetchMock = vi.spyOn(globalThis, "fetch").mockImplementation(() => json(200, { ...beta }));
    const onSaved = vi.fn();
    renderFr(<ImporterAIChoice importer={{ ...beta, ai_refused: false }} isAdmin={false} onSaved={onSaved} onClose={() => {}} />);
    fireEvent.click(screen.getByRole("checkbox", { name: /Ce client refuse/ }));
    fireEvent.click(screen.getByRole("button", { name: "Enregistrer" }));
    await waitFor(() => expect(onSaved).toHaveBeenCalled());
    const [url, init] = fetchMock.mock.calls[0];
    expect(String(url)).toMatch(/\/importers\/i2\/ai-refusal$/);
    expect((init as RequestInit).method).toBe("PUT");
    expect(JSON.parse(String((init as RequestInit).body))).toEqual({ refused: true });
  });
});
