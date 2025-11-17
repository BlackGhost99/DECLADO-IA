import { useState } from 'react';
import { useSettings, type Currency } from '../contexts/SettingsContext';
import './CurrencyConverter.css';

interface CurrencyConverterProps {
  amount: number;
  from?: Currency;
  onAmountChange?: (amount: number, currency: Currency) => void;
}

export function CurrencyConverter({ amount, from = 'XAF', onAmountChange }: CurrencyConverterProps) {
  const { settings, convertCurrency, formatCurrency } = useSettings();
  const [inputAmount, setInputAmount] = useState(amount.toString());
  const [selectedCurrency, setSelectedCurrency] = useState<Currency>(from);

  const handleAmountChange = (value: string) => {
    setInputAmount(value);
    const numValue = parseFloat(value) || 0;
    if (onAmountChange) {
      onAmountChange(numValue, selectedCurrency);
    }
  };

  const handleCurrencyChange = (currency: Currency) => {
    setSelectedCurrency(currency);
    if (onAmountChange) {
      const numValue = parseFloat(inputAmount) || 0;
      onAmountChange(numValue, currency);
    }
  };

  // Conversion: de la devise sélectionnée vers la devise configurée
  const inputValue = parseFloat(inputAmount) || 0;
  const convertedAmount = convertCurrency(inputValue, selectedCurrency, settings.currency);

  return (
    <div className="currency-converter">
      <div className="currency-input-group">
        <input
          type="number"
          value={inputAmount}
          onChange={e => handleAmountChange(e.target.value)}
          className="currency-input"
          step="0.01"
          min="0"
        />
        <select
          value={selectedCurrency}
          onChange={e => handleCurrencyChange(e.target.value as Currency)}
          className="currency-select"
        >
          <option value="XAF">FCFA</option>
          <option value="USD">USD</option>
          <option value="EUR">EUR</option>
          <option value="GBP">GBP</option>
          <option value="CNY">CNY</option>
        </select>
      </div>
      {selectedCurrency !== settings.currency && inputValue > 0 && (
        <div className="currency-conversion">
          <span className="conversion-label">=</span>
          <span className="conversion-amount">{formatCurrency(convertedAmount)}</span>
          <span className="conversion-note">
            ({inputValue.toLocaleString('fr-FR', { minimumFractionDigits: 2, maximumFractionDigits: 2 })} {selectedCurrency} → {settings.currency})
          </span>
        </div>
      )}
    </div>
  );
}

