import { render as baseRender, screen, fireEvent, waitFor, cleanup } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { ReactElement } from "react";
import { CaseLifecycle } from "../src/Lifecycle";
import { I18nProvider } from "../src/i18n";
import { api, type CaseDetail, type Membership } from "../src/api";

const render = (ui: ReactElement) => baseRender(ui, { wrapper: I18nProvider });
const detail = (revision: object) => ({ id: "case1", revision: { row_version: 4, is_editable: false, ...revision } }) as unknown as CaseDetail;
const roles = (...r: string[]) => ({ roles: r }) as unknown as Membership;
const act = async (a: () => Promise<unknown>) => {
  await a();
};

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

describe("Fin de vie du dossier (T97-T99)", () => {
  it("enregistre le dépôt SYDONIA d'un dossier validé", async () => {
    const lodge = vi.spyOn(api, "lodge").mockResolvedValue({} as CaseDetail);
    render(<CaseLifecycle detail={detail({ state: "validated" })} membership={roles("declarant")} act={act} />);
    expect(screen.queryByRole("button", { name: /Archiver le dossier/ })).toBeNull(); // validateur ou admin seulement
    fireEvent.click(screen.getByRole("button", { name: /Marquer comme déposé en douane/ }));
    fireEvent.change(screen.getByLabelText(/N° de déclaration SYDONIA/), { target: { value: "L 1234" } });
    fireEvent.change(screen.getByLabelText(/Date de dépôt/), { target: { value: "2026-11-02" } });
    fireEvent.submit(screen.getByRole("form", { name: "Marquer comme déposé en douane" }));
    await waitFor(() => expect(lodge).toHaveBeenCalledWith("case1", 4, "L 1234", "2026-11-02"));
  });

  it("affiche le dépôt et propose la sortie des archives à l'administrateur", () => {
    render(
      <CaseLifecycle
        detail={detail({ state: "archived", customs_declaration_number: "L 1234", lodged_on: "2026-11-02" })}
        membership={roles("org_admin")}
        act={act}
      />,
    );
    expect(screen.getByText(/déclaration n° L 1234/)).toBeInTheDocument();
    expect(screen.getByText(/Dossier archivé : lecture seule/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Sortir des archives/ })).toBeInTheDocument();
  });
});
