import { render as baseRender, screen, fireEvent, waitFor, cleanup } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { ReactElement } from "react";
import { CaseSharing, SharedCases } from "../src/Sharing";
import { I18nProvider } from "../src/i18n";
import { api, type CaseShare, type Membership } from "../src/api";

const render = (ui: ReactElement) => baseRender(ui, { wrapper: I18nProvider });
const roles = (...r: string[]) => ({ roles: r }) as unknown as Membership;
const share = (over: Partial<CaseShare> = {}): CaseShare => ({
  id: "s1", case_reference: "CT-2026-0001", case_title: "Fictif", direction: "incoming",
  organization: { name: "Import Fictif", profiles: ["importer"] }, level: "comment", status: "pending", message: "Pour avis",
  created_at: new Date().toISOString(), created_by: "Agent", decided_at: null, revoked_at: null, row_version: 1, case_id: null, ...over,
});

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

describe("Partage de dossiers (COL-01 à COL-04)", () => {
  it("envoie une invitation par code partenaire", async () => {
    vi.spyOn(api, "caseShares").mockResolvedValue({ results: [] });
    const create = vi.spyOn(api, "createShare").mockResolvedValue(share({ direction: "outgoing" }));
    render(<CaseSharing caseId="c1" membership={roles("declarant")} />);
    fireEvent.change(screen.getByRole("textbox", { name: "Code partenaire" }), { target: { value: " ct-abcd-efgh " } });
    fireEvent.click(screen.getByRole("button", { name: "Envoyer l'invitation" }));
    await waitFor(() => expect(create).toHaveBeenCalledWith("c1", { code: "ct-abcd-efgh", level: "comment", message: "" }));
  });

  it("montre notre code et laisse un validateur accepter, pas un déclarant", async () => {
    vi.spyOn(api, "incomingShares").mockResolvedValue({ results: [share()] });
    vi.spyOn(api, "partnerCode").mockResolvedValue({ code: "CT-ABCD-EFGH" });
    const decide = vi.spyOn(api, "decideShare").mockResolvedValue(share({ status: "accepted" }));
    render(<SharedCases membership={roles("validator")} />);
    expect(await screen.findByText("CT-ABCD-EFGH")).toBeTruthy();
    fireEvent.click(await screen.findByRole("button", { name: "Accepter" }));
    await waitFor(() => expect(decide).toHaveBeenCalledWith("s1", "accept"));
    expect(screen.queryByRole("button", { name: "Changer le code" })).toBeNull(); // administrateur seulement
    cleanup();
    render(<SharedCases membership={roles("declarant")} />);
    await screen.findByText("CT-2026-0001");
    expect(screen.queryByRole("button", { name: "Accepter" })).toBeNull();
  });
});
