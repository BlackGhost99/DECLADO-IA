import { render as baseRender, screen, fireEvent, waitFor, cleanup } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { ReactElement } from "react";
import { CaseExemptions, ExemptionsPanel } from "../src/Exemptions";
import { I18nProvider } from "../src/i18n";
import type { CaseDetail, Membership } from "../src/api";

const render = (ui: ReactElement) => baseRender(ui, { wrapper: I18nProvider });
const json = (status: number, body: unknown) =>
  Promise.resolve(new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } }));

const regime = {
  id: "r1", territory: "GA", code: "EXO-FICTIF-1", label: "Exonération fictive d'essai", conditions: "",
  taxes: { DDI: "0", TVA: "0" }, hs_prefixes: ["4201"], customs_regimes: [], required_documents: ["Attestation fictive"],
  valid_from: "2026-01-01", valid_to: null, source_kind: "operator", source_reference: "", official: false,
  reason: "Essai fictif", is_active: true, deactivated_at: null, deactivation_reason: "", created_by: "admin",
  created_at: "2026-11-02T10:00:00Z",
};
const claim = {
  id: "c1", regime, status: "requested", goods_line_ids: [], proof_ids: ["d1"], proof_reference: "ATT-1", note: "",
  requested_by: "agent", decided_by: null, decided_at: null, decision_reason: "", created_at: "2026-11-02T10:00:00Z",
  row_version: 1,
};
const detail = {
  id: "case1",
  revision: {
    is_editable: true,
    documents: [{ id: "d1", replaced_by_id: null, document: { original_name: "attestation.pdf" } }],
    goods_lines: [{ id: "g1", ordinal: 1, description: "Selles fictives" }],
  },
} as unknown as CaseDetail;
const validator = { roles: ["validator"] } as unknown as Membership;

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

describe("Exonérations (TAX-04, T23, T94)", () => {
  it("liste les exonérations et signale celle sans texte officiel", async () => {
    vi.spyOn(globalThis, "fetch").mockImplementation((input) =>
      String(input).includes("/fiscal/exemptions") ? json(200, { results: [regime], taxes: ["DDI", "TVA"], can_edit: false }) : json(404, {}),
    );
    render(<ExemptionsPanel />);
    expect(await screen.findByText("EXO-FICTIF-1")).toBeInTheDocument();
    expect(screen.getByText("DDI exonéré · TVA exonéré")).toBeInTheDocument();
    expect(screen.getByText("Sans texte officiel")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Déclarer une exonération" })).toBeNull();
  });

  it("montre la demande en attente et laisse le validateur valider le justificatif", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockImplementation((input, init) => {
      const url = String(input);
      if (url.endsWith("/exemptions/c1/validate") && init?.method === "POST") return json(200, { ...claim, status: "validated" });
      if (url.includes("/cases/case1/exemptions")) return json(200, { results: [claim] });
      if (url.includes("/fiscal/exemptions")) return json(200, { results: [regime], taxes: ["DDI"], can_edit: false });
      if (url.endsWith("/auth/csrf")) return json(200, {});
      return json(404, {});
    });
    const changed = vi.fn();
    render(<CaseExemptions detail={detail} membership={validator} onChanged={changed} />);
    expect(await screen.findByText("Justificatif à valider")).toBeInTheDocument();
    expect(screen.getByText(/Joint : attestation\.pdf · n° ATT-1/)).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Valider le justificatif" }));
    await waitFor(() => expect(changed).toHaveBeenCalled());
    expect(fetchMock.mock.calls.some(([u, i]) => String(u).endsWith("/exemptions/c1/validate") && i?.method === "POST")).toBe(true);
  });
});
