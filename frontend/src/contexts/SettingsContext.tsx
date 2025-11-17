import { createContext, useContext, useState, useEffect, ReactNode } from 'react';
import { DEFAULT_EXCHANGE_RATES, fetchExchangeRates, validateExchangeRate, roundCurrency } from '../utils/currencyUtils';

export type Theme = 'dark' | 'light' | 'custom';
export type Currency = 'XAF' | 'USD' | 'EUR' | 'GBP' | 'CNY';

export interface Settings {
  theme: Theme;
  currency: Currency;
  language: string;
  autoProcess: boolean;
  showPreview: boolean;
  previewSize: 'small' | 'medium' | 'large';
  exchangeRates: Record<Currency, number>;
}

const defaultSettings: Settings = {
  theme: 'dark',
  currency: 'XAF',
  language: 'fr',
  autoProcess: true,
  showPreview: true,
  previewSize: 'medium',
  exchangeRates: {
    XAF: DEFAULT_EXCHANGE_RATES.XAF.rate,
    USD: DEFAULT_EXCHANGE_RATES.USD.rate,
    EUR: DEFAULT_EXCHANGE_RATES.EUR.rate,
    GBP: DEFAULT_EXCHANGE_RATES.GBP.rate,
    CNY: DEFAULT_EXCHANGE_RATES.CNY.rate,
  },
};

interface SettingsContextType {
  settings: Settings;
  updateSettings: (updates: Partial<Settings>) => void;
  resetSettings: () => void;
  formatCurrency: (amount: number) => string;
  convertCurrency: (amount: number, from: Currency, to: Currency) => number;
  refreshExchangeRates: (backendUrl?: string) => Promise<void>;
  validateRate: (rate: number, currency: Currency) => boolean;
}

const SettingsContext = createContext<SettingsContextType | undefined>(undefined);

interface SettingsProviderProps {
  children: ReactNode;
  backendUrl?: string;
}

export function SettingsProvider({ children, backendUrl }: SettingsProviderProps) {
  const [settings, setSettings] = useState<Settings>(() => {
    const saved = localStorage.getItem('declado-settings');
    if (saved) {
      try {
        const parsed = JSON.parse(saved);
        // Valider les taux de change sauvegardés
        const validatedRates: Record<Currency, number> = {
          XAF: 1,
          USD: validateExchangeRate(parsed.exchangeRates?.USD, 'USD') 
            ? parsed.exchangeRates.USD 
            : DEFAULT_EXCHANGE_RATES.USD.rate,
          EUR: validateExchangeRate(parsed.exchangeRates?.EUR, 'EUR') 
            ? parsed.exchangeRates.EUR 
            : DEFAULT_EXCHANGE_RATES.EUR.rate,
          GBP: validateExchangeRate(parsed.exchangeRates?.GBP, 'GBP') 
            ? parsed.exchangeRates.GBP 
            : DEFAULT_EXCHANGE_RATES.GBP.rate,
          CNY: validateExchangeRate(parsed.exchangeRates?.CNY, 'CNY') 
            ? parsed.exchangeRates.CNY 
            : DEFAULT_EXCHANGE_RATES.CNY.rate,
        };
        return { ...defaultSettings, ...parsed, exchangeRates: validatedRates };
      } catch {
        return defaultSettings;
      }
    }
    return defaultSettings;
  });

  const updateSettings = (updates: Partial<Settings>) => {
    setSettings(prev => {
      // Valider les taux de change si fournis
      if (updates.exchangeRates) {
        const validatedRates: Record<Currency, number> = { ...prev.exchangeRates };
        for (const [currency, rate] of Object.entries(updates.exchangeRates)) {
          if (validateExchangeRate(rate as number, currency as Currency)) {
            validatedRates[currency as Currency] = rate as number;
          }
        }
        return { ...prev, ...updates, exchangeRates: validatedRates };
      }
      return { ...prev, ...updates };
    });
  };

  const resetSettings = () => {
    setSettings(defaultSettings);
  };

  /**
   * Rafraîchit les taux de change depuis le backend
   */
  const refreshExchangeRates = async (url?: string): Promise<void> => {
    const targetUrl = url || backendUrl;
    if (!targetUrl) return;

    const rates = await fetchExchangeRates(targetUrl);
    if (rates) {
      updateSettings({ exchangeRates: rates });
    }
  };

  /**
   * Valide un taux de change
   */
  const validateRate = (rate: number, currency: Currency): boolean => {
    return validateExchangeRate(rate, currency);
  };

  // Charger les taux depuis le backend au démarrage
  useEffect(() => {
    if (backendUrl) {
      refreshExchangeRates(backendUrl).catch(console.error);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [backendUrl]);

  useEffect(() => {
    localStorage.setItem('declado-settings', JSON.stringify(settings));
    // Appliquer le thème
    document.documentElement.setAttribute('data-theme', settings.theme);
  }, [settings]);

  /**
   * Formate un montant selon la devise configurée
   * @param amount Montant en XAF (FCFA)
   * @returns Montant formaté dans la devise sélectionnée
   */
  const formatCurrency = (amount: number): string => {
    if (!isFinite(amount) || isNaN(amount)) return '0';
    
    const converted = convertCurrency(amount, 'XAF', settings.currency);
    
    // Formatage selon la devise
    const locale = settings.language === 'fr' ? 'fr-FR' : 'en-US';
    
    // Pour XAF, on n'utilise pas le format currency standard (pas de symbole ISO)
    if (settings.currency === 'XAF') {
      return new Intl.NumberFormat(locale, {
        minimumFractionDigits: 0,
        maximumFractionDigits: 0,
      }).format(converted) + ' FCFA';
    }
    
    const formatter = new Intl.NumberFormat(locale, {
      style: 'currency',
      currency: settings.currency,
      minimumFractionDigits: settings.currency === 'JPY' ? 0 : 2,
      maximumFractionDigits: settings.currency === 'JPY' ? 0 : 2,
    });
    
    return formatter.format(converted);
  };

  /**
   * Convertit un montant d'une devise vers une autre
   * Les taux sont stockés comme "1 [devise] = X XAF"
   * 
   * @param amount Montant à convertir
   * @param from Devise source
   * @param to Devise cible
   * @returns Montant converti (arrondi à 2 décimales)
   */
  const convertCurrency = (amount: number, from: Currency, to: Currency): number => {
    // Validation
    if (!isFinite(amount) || isNaN(amount) || amount < 0) return 0;
    if (from === to) return Math.round(amount * 100) / 100; // Arrondi à 2 décimales
    
    const rates = settings.exchangeRates;
    
    // Tous les taux sont exprimés en XAF (1 [devise] = X XAF)
    // Exemple: rates.USD = 600 signifie 1 USD = 600 XAF
    
    // Étape 1: Convertir la source vers XAF
    let amountInXAF: number;
    if (from === 'XAF') {
      amountInXAF = amount; // Déjà en XAF
    } else {
      // Multiplier par le taux: si on a 100 USD et 1 USD = 600 XAF, alors 100 * 600 = 60000 XAF
      amountInXAF = amount * rates[from];
    }
    
    // Étape 2: Convertir de XAF vers la devise cible
    let result: number;
    if (to === 'XAF') {
      result = amountInXAF; // Reste en XAF
    } else {
      // Diviser par le taux: si on a 60000 XAF et 1 USD = 600 XAF, alors 60000 / 600 = 100 USD
      result = amountInXAF / rates[to];
    }
    
    // Arrondi à 2 décimales pour les devises, 0 pour XAF
    if (to === 'XAF') {
      return Math.round(result); // Arrondi au franc le plus proche
    } else {
      return Math.round(result * 100) / 100; // Arrondi à 2 décimales
    }
  };

  return (
    <SettingsContext.Provider
      value={{ 
        settings, 
        updateSettings, 
        resetSettings, 
        formatCurrency, 
        convertCurrency,
        refreshExchangeRates,
        validateRate,
      }}
    >
      {children}
    </SettingsContext.Provider>
  );
}

export function useSettings() {
  const context = useContext(SettingsContext);
  if (!context) {
    throw new Error('useSettings must be used within SettingsProvider');
  }
  return context;
}

