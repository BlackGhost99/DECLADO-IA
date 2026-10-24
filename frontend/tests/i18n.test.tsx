import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import { ecrans } from "../src/i18n/ecrans";
import { I18nProvider, LanguageSelector, tr, useI18n } from "../src/i18n";

const placeholders = (text: string) => [...text.matchAll(/\{(\w+)\}/g)].map((m) => m[1]).sort();

describe("textes des écrans", () => {
  it("existent dans les quatre langues, avec les mêmes paramètres", () => {
    const keys = Object.keys(ecrans.fr) as (keyof typeof ecrans.fr)[];
    for (const locale of ["en", "es", "ar"] as const) {
      expect(Object.keys(ecrans[locale]).sort()).toEqual([...keys].sort());
      for (const key of keys) {
        expect(ecrans[locale][key].trim(), `${locale} ${key}`).not.toBe("");
        expect(placeholders(ecrans[locale][key]), `${locale} ${key}`).toEqual(placeholders(ecrans.fr[key]));
      }
    }
  });
});

// Comme App : un composant qui lit la langue fait réafficher ses enfants quand elle change.
function Probe() {
  useI18n();
  return (
    <>
      <LanguageSelector />
      <p>{tr("ctl.list", { count: 3 })}</p>
    </>
  );
}

describe("changement de langue", () => {
  afterEach(() => {
    cleanup();
    localStorage.clear();
  });

  it("traduit les textes hors composant et passe l'arabe de droite à gauche", () => {
    render(<I18nProvider><Probe /></I18nProvider>);
    expect(screen.getByText("Liste des contrôles (3)")).toBeTruthy();
    fireEvent.change(screen.getByRole("combobox"), { target: { value: "en" } });
    expect(screen.getByText("Checks list (3)")).toBeTruthy();
    fireEvent.change(screen.getByRole("combobox"), { target: { value: "ar" } });
    expect(screen.getByText("قائمة الفحوص (3)")).toBeTruthy();
    expect(document.documentElement.dir).toBe("rtl");
  });
});
