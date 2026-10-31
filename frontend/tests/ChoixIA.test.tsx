import { render as baseRender, screen, fireEvent, waitFor, cleanup } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { ReactElement } from "react";
import { ProposalsPanel } from "../src/Proposals";
import { I18nProvider } from "../src/i18n";
import type { GoodsLine } from "../src/api";

const render = (ui: ReactElement) => baseRender(ui, { wrapper: I18nProvider });

const check = {
  id: "chk1", observed_code: "0101", observed_field: "HS Code", normalized_code: "0101", target_edition_id: "e1",
  target_edition_label: "Jeu lot 3", recognition_status: "incomplete", recognition_label: "Incomplet", node: null,
  is_current: true, human_confirmation: "pending", operational_applicability: "unverified", findings: [],
  checked_at: "2026-10-31T10:00:00Z", checked_by: "declarant@a.test",
};
const goods = {
  id: "g1", ordinal: 1, description: "Chevaux reproducteurs fictifs", origin_country: "FR", regime: "", row_version: 2,
  sources: [], latest_check: check, decision: null, decision_count: 0,
} as unknown as GoodsLine;
const proposal = (id: string, code: string, label: string) => ({
  id, rank: 1, node_id: `n-${id}`, code, code_display: `${code.slice(0, 4)}.${code.slice(4, 6)}.${code.slice(6)}`, label,
  full_path: label, reasons: ["Subdivision du code présent « 0101 »."], notes: [], distinguishing: [], retrieval_score: null,
});
const set = (aiChoice: unknown) => ({
  id: "s1", goods_line_id: "g1", edition_id: "e1", edition_label: "Jeu lot 3", trigger: "incomplete", query: "", producer: "recherche-referentiel 1.0",
  is_ai: false, ai_available: true, ai_choice: aiChoice, questions: [], is_current: true, created_at: "", created_by: "x",
  proposals: [proposal("p1", "01012100", "Chevaux reproducteurs de race pure"), proposal("p2", "01012900", "Autres chevaux vivants")],
});
const chosen = {
  id: "ai1", status: "sent", status_label: "Envoyée", proposal_id: "p1", node_id: "n-p1", code: "01012100", code_display: "0101.21.00",
  label: "Chevaux reproducteurs de race pure", insufficient: false, reason: "Reproducteurs de race pure.", evidence: "reproducteurs",
  rejected: [], model: "claude-haiku-5-5", free_tier: false, error_message: "", created_at: "",
};

function json(status: number, body: unknown) {
  return Promise.resolve(new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } }));
}

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

describe("Choix du code par l'IA (T80)", () => {
  it("demande le choix à l'IA, l'affiche avec sa raison, et l'agent le retient", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockImplementation((input) => {
      const url = String(input);
      if (url.endsWith("/goods-lines/g1/proposals")) return json(200, { results: [set(null)] });
      if (url.endsWith("/goods-lines/g1/ai-choice")) return json(201, set(chosen));
      return json(404, {});
    });
    const act = vi.fn((a: () => Promise<unknown>) => a().then(() => undefined));
    render(<ProposalsPanel goods={goods} editionId="e1" editable act={act} />);
    fireEvent.click(await screen.findByRole("button", { name: "Demander à l'IA de choisir" }));
    expect(await screen.findByText("Choix de l'IA : 0101.21.00 Chevaux reproducteurs de race pure")).toBeInTheDocument();
    expect(screen.getByText("Passage de la désignation : « reproducteurs »")).toBeInTheDocument();
    expect(screen.getByText(/seul un agent décide le code/)).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Retenir le choix de l'IA" }));
    await waitFor(() => {
      const call = fetchMock.mock.calls.find(([u]) => String(u).endsWith("/goods-lines/g1/decisions"));
      expect(call).toBeDefined();
      expect(JSON.parse(String(call![1]!.body))).toMatchObject({
        action: "complete", proposal_id: "p1", node_id: "n-p1", code_check_id: "chk1",
        reason: "Choix de l'IA vérifié : Reproducteurs de race pure.",
      });
    });
  });

  it("dit quand l'IA ne peut pas trancher, sans rien choisir", async () => {
    vi.spyOn(globalThis, "fetch").mockImplementation(() =>
      json(200, { results: [set({ ...chosen, proposal_id: null, node_id: null, code: null, code_display: null, label: null, insufficient: true, reason: "Race pure ou non : non précisé." })] }),
    );
    render(<ProposalsPanel goods={goods} editionId="e1" editable act={vi.fn()} />);
    expect(await screen.findByText(/L'IA ne peut pas trancher : Race pure ou non/)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Retenir le choix de l'IA" })).toBeNull();
  });
});
