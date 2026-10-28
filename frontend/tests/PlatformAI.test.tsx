import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import { I18nProvider } from "../src/i18n";
import { PlatformAIPanel } from "../src/PlatformAI";

afterEach(() => { cleanup(); vi.restoreAllMocks(); });

const provider = { name: "gemini", label: "Google Gemini", model: "gemini-3.5-flash-lite", configured: true, free_tier: true };
const organization = { id: "org-a", name: "Transit Alpha", monthly_cap: 200, row_version: 2,
  usage: { month_start: "2026-10-01", sent: 10, cap: 200, cost_estimate: "0" } };
const json = (body: unknown, status = 200) => Promise.resolve(new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } }));

it("l'exploitant voit le service et attribue un plafond sans activer la société", async () => {
  localStorage.setItem("clairtransit.interface-locale", "fr");
  document.cookie = "csrftoken=tok";
  const calls = vi.spyOn(globalThis, "fetch").mockImplementation((_url, init) => init?.method === "PUT"
    ? json({ ...organization, monthly_cap: 350, row_version: 3 }) : json({ provider, organizations: [organization] }));
  render(<I18nProvider><PlatformAIPanel /></I18nProvider>);
  expect(await screen.findByText("Google Gemini")).toBeInTheDocument();
  expect(screen.getByText("gemini-3.5-flash-lite")).toBeInTheDocument();
  expect(screen.queryByRole("checkbox")).toBeNull();
  const form = screen.getByRole("form", { name: "Transit Alpha" });
  fireEvent.change(within(form).getByRole("spinbutton"), { target: { value: "350" } });
  fireEvent.click(within(form).getByRole("button", { name: "Enregistrer" }));
  await waitFor(() => expect(screen.getByRole("status")).toHaveTextContent("Réglage enregistré."));
  const put = calls.mock.calls.find(([, init]) => init?.method === "PUT")!;
  expect(String(put[0])).toMatch(/\/platform\/organizations\/org-a\/ai-quota$/);
  expect(JSON.parse(String(put[1]?.body))).toEqual({ monthly_cap: 350, row_version: 2 });
});

it("affiche une erreur d'accès sans donner les contrôles de quota", async () => {
  vi.spyOn(globalThis, "fetch").mockImplementation(() => json({ code: "PERMISSION_DENIED", message: "Accès refusé." }, 403));
  render(<I18nProvider><PlatformAIPanel /></I18nProvider>);
  expect(await screen.findByRole("alert")).toHaveTextContent("Accès refusé.");
  expect(screen.queryByRole("spinbutton")).toBeNull();
});
