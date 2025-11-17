/**
 * Utilitaires pour la gestion des devises
 * Amélioration de la précision et des conversions
 */

import type { Currency } from '../contexts/SettingsContext';

export interface ExchangeRate {
  currency: Currency;
  rate: number; // 1 [currency] = rate XAF
  lastUpdated?: string;
  source?: string;
}

/**
 * Taux de change par défaut (mis à jour régulièrement)
 * Format: 1 [devise] = X XAF (Franc CFA)
 */
export const DEFAULT_EXCHANGE_RATES: Record<Currency, ExchangeRate> = {
  XAF: {
    currency: 'XAF',
    rate: 1.0,
    source: 'Base',
    lastUpdated: new Date().toISOString(),
  },
  USD: {
    currency: 'USD',
    rate: 600.0, // 1 USD = 600 XAF (indicatif, varie selon marché)
    source: 'CEMAC',
    lastUpdated: new Date().toISOString(),
  },
  EUR: {
    currency: 'EUR',
    rate: 655.957, // 1 EUR = 655.957 XAF (taux fixe depuis 1999)
    source: 'BEAC',
    lastUpdated: new Date().toISOString(),
  },
  GBP: {
    currency: 'GBP',
    rate: 780.0, // 1 GBP = 780 XAF (indicatif, aligné avec backend)
    source: 'CEMAC',
    lastUpdated: new Date().toISOString(),
  },
  CNY: {
    currency: 'CNY',
    rate: 85.0, // 1 CNY = 85 XAF (indicatif)
    source: 'CEMAC',
    lastUpdated: new Date().toISOString(),
  },
};

/**
 * Récupère les taux de change depuis le backend (si disponible)
 * Le backend stocke les taux dans data/tariffs/exchange_rates.yaml
 */
export async function fetchExchangeRates(backendUrl: string): Promise<Record<Currency, number> | null> {
  try {
    // Option 1: Essayer un endpoint dédié (à créer dans le backend si nécessaire)
    const response = await fetch(`${backendUrl}/api/exchange-rates`, {
      method: 'GET',
      headers: { 'Content-Type': 'application/json' },
    });

    if (response.ok) {
      const data = await response.json();
      // Convertir le format backend vers notre format
      const rates: Record<Currency, number> = {
        XAF: 1.0,
        USD: validateExchangeRate(data.USD, 'USD') 
          ? parseFloat(data.USD) 
          : DEFAULT_EXCHANGE_RATES.USD.rate,
        EUR: validateExchangeRate(data.EUR, 'EUR') 
          ? parseFloat(data.EUR) 
          : DEFAULT_EXCHANGE_RATES.EUR.rate,
        GBP: validateExchangeRate(data.GBP, 'GBP') 
          ? parseFloat(data.GBP) 
          : DEFAULT_EXCHANGE_RATES.GBP.rate,
        CNY: validateExchangeRate(data.CNY, 'CNY') 
          ? parseFloat(data.CNY) 
          : DEFAULT_EXCHANGE_RATES.CNY.rate,
      };
      return rates;
    }
  } catch (error) {
    // Si l'endpoint n'existe pas, utiliser les valeurs par défaut
    console.warn('Endpoint exchange-rates non disponible, utilisation des taux par défaut:', error);
  }
  
  // Retourner les taux par défaut si le backend n'est pas disponible
  return {
    XAF: DEFAULT_EXCHANGE_RATES.XAF.rate,
    USD: DEFAULT_EXCHANGE_RATES.USD.rate,
    EUR: DEFAULT_EXCHANGE_RATES.EUR.rate,
    GBP: DEFAULT_EXCHANGE_RATES.GBP.rate,
    CNY: DEFAULT_EXCHANGE_RATES.CNY.rate,
  };
}

/**
 * Valide un taux de change
 */
export function validateExchangeRate(rate: number, currency: Currency): boolean {
  if (!isFinite(rate) || isNaN(rate) || rate <= 0) return false;
  
  // Vérifications de cohérence selon la devise
  if (currency === 'XAF') {
    return rate === 1; // XAF doit toujours être 1
  }
  
  // Plages raisonnables basées sur les taux historiques CEMAC
  const minRates: Record<Currency, number> = {
    XAF: 1,
    USD: 400,   // Minimum historique récent
    EUR: 600,   // Proche de la parité fixe (655.957)
    GBP: 600,   // Minimum historique
    CNY: 50,    // Minimum historique
  };
  
  const maxRates: Record<Currency, number> = {
    XAF: 1,
    USD: 800,   // Maximum historique récent
    EUR: 700,   // Légèrement au-dessus de la parité fixe
    GBP: 1000,  // Maximum historique
    CNY: 150,   // Maximum historique
  };
  
  return rate >= minRates[currency] && rate <= maxRates[currency];
}

/**
 * Arrondit un montant selon les règles de la devise
 */
export function roundCurrency(amount: number, currency: Currency): number {
  if (!isFinite(amount) || isNaN(amount)) return 0;
  
  if (currency === 'XAF') {
    // Arrondi au franc le plus proche (pas de centimes)
    return Math.round(amount);
  } else {
    // Arrondi à 2 décimales pour les autres devises
    return Math.round(amount * 100) / 100;
  }
}

/**
 * Formate un montant avec précision selon la devise
 */
export function formatCurrencyAmount(
  amount: number,
  currency: Currency,
  locale: string = 'fr-FR'
): string {
  const rounded = roundCurrency(amount, currency);
  
  if (currency === 'XAF') {
    return new Intl.NumberFormat(locale, {
      minimumFractionDigits: 0,
      maximumFractionDigits: 0,
    }).format(rounded) + ' FCFA';
  }
  
  return new Intl.NumberFormat(locale, {
    style: 'currency',
    currency: currency,
    minimumFractionDigits: currency === 'JPY' ? 0 : 2,
    maximumFractionDigits: currency === 'JPY' ? 0 : 2,
  }).format(rounded);
}

/**
 * Calcule le taux inverse (1 XAF = X [devise])
 */
export function getInverseRate(rate: number): number {
  if (rate === 0 || !isFinite(rate)) return 0;
  return 1 / rate;
}

/**
 * Formate un taux de change pour l'affichage
 */
export function formatExchangeRate(rate: number, currency: Currency): string {
  if (currency === 'XAF') return '1 XAF = 1 XAF';
  
  // Format: "1 USD = 600.00 XAF"
  // Pour EUR, afficher avec plus de précision (taux fixe)
  const decimals = currency === 'EUR' ? 3 : 2;
  
  return `1 ${currency} = ${rate.toLocaleString('fr-FR', { 
    minimumFractionDigits: decimals, 
    maximumFractionDigits: decimals 
  })} XAF`;
}

