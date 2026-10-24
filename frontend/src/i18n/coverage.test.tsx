import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { I18nProvider, LanguageSelector, translations, useI18n } from "./index";

function Sample() {
  const { t } = useI18n();
  return <><LanguageSelector/><output>{t("cases")}</output></>;
}

describe("translation coverage", () => {
  it("contains the same nonempty keys in FR, EN, ES and AR", () => {
    const base = Object.keys(translations.fr).sort();
    for (const locale of ["en", "es", "ar"] as const) {
      expect(Object.keys(translations[locale]).sort()).toEqual(base);
      for (const value of Object.values(translations[locale])) {
        expect(value.trim().length).toBeGreaterThan(0);
      }
    }
  });

  it("switches to Arabic RTL and retains LTR for English", async () => {
    localStorage.setItem("clairtransit.interface-locale", "fr");
    render(<I18nProvider><Sample/></I18nProvider>);
    const select = screen.getByRole("combobox", { name: /langue de l'interface/i });
    fireEvent.change(select, {target: {value: "ar"}});
    await waitFor(() => expect(document.documentElement.dir).toBe("rtl"));
    expect(screen.getByText("الملفات")).toBeInTheDocument();
    fireEvent.change(select, {target: {value: "en"}});
    await waitFor(() => expect(document.documentElement.dir).toBe("ltr"));
    expect(screen.getByText("Cases")).toBeInTheDocument();
  });
});
