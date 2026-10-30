import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { CaseDetail, Membership } from "../src/api";
import { ValidationActions } from "../src/CaseDetail";
import { I18nProvider } from "../src/i18n";

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

const user = { id: "u1", email: "validateur@fictif.test", full_name: "Validateur fictif" };
function detail(state: string, blocking = 0, decisions: unknown[] = []): CaseDetail {
  return {
    id: "c1",
    revision: {
      state, state_label: state, row_version: 5, is_editable: ["draft", "in_preparation", "to_correct"].includes(state),
      completeness: { blocking: Array.from({ length: blocking }, (_, i) => ({ id: String(i) })), warnings: [], complete: blocking === 0 },
      decisions,
    },
  } as unknown as CaseDetail;
}
const member = (roles: string[]) => ({ roles }) as unknown as Membership;

function show(d: CaseDetail, roles: string[]) {
  localStorage.setItem("clairtransit.interface-locale", "fr");
  document.cookie = "csrftoken=tok";
  const act = vi.fn(async (a: () => Promise<unknown>) => { await a(); });
  render(<I18nProvider><ValidationActions detail={d} membership={member(roles)} act={act} go={() => {}} /></I18nProvider>);
  return act;
}

function json(status: number, body: unknown) {
  return Promise.resolve(new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } }));
}

describe("Circuit de validation (T73 à T75)", () => {
  it("bloque la soumission tant qu'un point bloquant reste", () => {
    show(detail("in_preparation", 2), ["declarant"]);
    const submit = screen.getByRole("button", { name: /Soumettre pour validation/ });
    expect(submit).toBeDisabled();
    expect(submit).toHaveTextContent("2");
  });

  it("le validateur valide, et ne retourne qu'avec un motif", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockImplementation(() => json(200, {}));
    show(detail("to_validate", 0, [{ kind: "submitted", kind_label: "Soumis pour validation", actor: user, reason: "", created_at: "2026-10-30T03:00:00Z" }]), ["validator"]);
    expect(screen.getByText(/Soumis pour validation par Validateur fictif/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Demander une correction/ })).toBeDisabled();
    fireEvent.click(screen.getByRole("button", { name: /Valider le dossier/ }));
    await waitFor(() => expect(fetchMock).toHaveBeenCalled());
    const [url, init] = fetchMock.mock.calls.find(([, i]) => (i as RequestInit | undefined)?.method === "POST")!;
    expect(String(url)).toMatch(/\/cases\/c1\/workflow\/validate$/);
    expect(JSON.parse(String((init as RequestInit).body))).toEqual({ row_version: 5, reason: "" });
  });

  it("un déclarant voit l'attente d'un validateur, sans bouton Valider", () => {
    show(detail("to_validate"), ["declarant"]);
    expect(screen.queryByRole("button", { name: /Valider le dossier/ })).toBeNull();
    expect(screen.getByText(/en attente d'un validateur/)).toBeInTheDocument();
  });

  it("un dossier validé se rouvre en nouvelle révision, avec un motif obligatoire (WF-04)", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockImplementation(() => json(201, {}));
    show(detail("validated"), ["validator"]);
    const button = screen.getByRole("button", { name: /Créer une nouvelle révision/ });
    expect(button).toBeDisabled();
    fireEvent.change(screen.getByLabelText("Motif de la nouvelle révision"), { target: { value: "Facture rectifiée" } });
    fireEvent.click(button);
    await waitFor(() => expect(fetchMock).toHaveBeenCalled());
    const [url, init] = fetchMock.mock.calls.find(([, i]) => (i as RequestInit | undefined)?.method === "POST")!;
    expect(String(url)).toMatch(/\/cases\/c1\/revisions$/);
    expect(JSON.parse(String((init as RequestInit).body))).toEqual({ reason: "Facture rectifiée" });
  });
});
