import { describe, expect, it, vi } from 'vitest';
import {
  DEFAULT_EXCHANGE_RATES,
  fetchExchangeRates,
  formatCurrencyAmount,
  roundCurrency,
  validateExchangeRate,
} from './currencyUtils';

describe('roundCurrency', () => {
  it('arrondit le franc CFA à l’unité et les autres devises au centime', () => {
    expect(roundCurrency(1234.6, 'XAF')).toBe(1235);
    expect(roundCurrency(12.345, 'EUR')).toBe(12.35);
  });

  it('ramène une valeur non finie à zéro', () => {
    expect(roundCurrency(Number.NaN, 'USD')).toBe(0);
    expect(roundCurrency(Number.POSITIVE_INFINITY, 'XAF')).toBe(0);
  });
});

describe('validateExchangeRate', () => {
  it('accepte la parité fixe de l’euro et refuse un taux hors plage', () => {
    expect(validateExchangeRate(655.957, 'EUR')).toBe(true);
    expect(validateExchangeRate(1000, 'EUR')).toBe(false);
    expect(validateExchangeRate(-1, 'USD')).toBe(false);
  });

  it('exige un taux de 1 pour le franc CFA', () => {
    expect(validateExchangeRate(1, 'XAF')).toBe(true);
    expect(validateExchangeRate(2, 'XAF')).toBe(false);
  });
});

describe('formatCurrencyAmount', () => {
  it('affiche le franc CFA sans décimale avec le suffixe FCFA', () => {
    expect(formatCurrencyAmount(1500.4, 'XAF')).toMatch(/^1\s?500 FCFA$/);
  });

  it('affiche les autres devises avec deux décimales', () => {
    expect(formatCurrencyAmount(12.5, 'EUR')).toMatch(/12,50/);
  });
});

describe('fetchExchangeRates', () => {
  it('garde les taux par défaut quand le backend renvoie un taux incohérent', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({
        ok: true,
        json: async () => ({ USD: 610, EUR: 9999, GBP: 790, CNY: 86 }),
      })
    );
    const rates = await fetchExchangeRates('http://backend.invalid');
    expect(rates).toEqual({
      XAF: 1,
      USD: 610,
      EUR: DEFAULT_EXCHANGE_RATES.EUR.rate,
      GBP: 790,
      CNY: 86,
    });
    vi.unstubAllGlobals();
  });
});
