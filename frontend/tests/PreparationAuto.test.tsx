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
  prefilled: ["planned_declaration_date", "regime", "target_edition"],
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

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

describe("Préparation automatique (T79)", () => {
  it("signale les champs remplis après la lecture et enregistre l'origine pour tout le dossier", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockImplementation((input, init) => {
      const url = String(input);
      if (url.endsWith("/cases/c1")) return json(200, detail);
      if (url.endsWith("/tariffs/editions")) return json(200, [edition]);
      if (url.endsWith("/revisions/r1") && init?.method === "PATCH") return json(200, revision);
      if (url.endsWith("/importers")) return json(200, { count: 0, results: [] });
      if (url.endsWith("/audit")) return json(200, { results: [] });
      return json(404, {});
    });
    render(<CaseDetailView caseId="c1" tab="apercu" membership={membership} me={{ id: "u1" }} />);
    expect(await screen.findByText(/ClairTransit a rempli les champs vides/)).toBeInTheDocument();
    expect(screen.getAllByText("Proposé automatiquement, à confirmer")).toHaveLength(3);
    fireEvent.change(screen.getByPlaceholderText("CN"), { target: { value: "cn" } });
    fireEvent.click(screen.getByRole("button", { name: "Enregistrer" }));
    await waitFor(() => {
      const patch = fetchMock.mock.calls.find(([, init]) => init?.method === "PATCH");
      expect(patch).toBeDefined();
      expect(JSON.parse(String(patch![1]!.body))).toMatchObject({ origin_country: "CN", regime: "IM4", row_version: 4 });
    });
  });
});
