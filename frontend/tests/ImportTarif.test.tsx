import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { I18nProvider } from "../src/i18n";
import { ReferenceAdmin } from "../src/Reference";

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

const json = (body: unknown, status = 200) =>
  Promise.resolve(new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } }));

describe("Import du tarif depuis l'écran (T78)", () => {
  it("dépose le classeur et annonce le barème des taxes activé", async () => {
    localStorage.setItem("clairtransit.interface-locale", "fr");
    document.cookie = "csrftoken=tok";
    const fetchMock = vi.spyOn(globalThis, "fetch").mockImplementation((input, init) => {
      const url = String(input);
      if (url.endsWith("/tariffs/imports") && init?.method === "POST")
        return json({ edition: { id: "e1", label: "Tarif CEMAC 2022 (SWD)", publication_state: "consultation" }, counts: { tariff_lines: 5373 }, taxes: { id: "t1", label: "x", active: true } }, 201);
      if (url.includes("/reference-imports")) return json({ results: [], count: 0 });
      return json([]);
    });
    render(<I18nProvider><ReferenceAdmin canSeeImports /></I18nProvider>);
    fireEvent.click(screen.getByRole("tab", { name: /Import Excel/ }));
    const file = new File(["x"], "Tarif_CEMAC_2022_SWD.xlsx");
    fireEvent.change(screen.getByLabelText("Fichier du tarif"), { target: { files: [file] } });
    const button = screen.getByRole("button", { name: /Importer le tarif/ });
    expect(button).not.toBeDisabled();
    fireEvent.submit(button.closest("form")!);
    expect(await screen.findByText(/Barème des taxes activé/)).toBeInTheDocument();
    const call = fetchMock.mock.calls.find(([u, i]) => String(u).endsWith("/tariffs/imports") && i?.method === "POST")!;
    expect((call[1]!.body as FormData).get("file")).toBeInstanceOf(File);
    await waitFor(() => expect(screen.getByText(/5373 lignes/)).toBeInTheDocument());
  });
});
