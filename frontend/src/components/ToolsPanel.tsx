import { useState } from 'react';
import { useSettings } from '../contexts/SettingsContext';
import { CurrencyConverter } from './CurrencyConverter';
import './ToolsPanel.css';

interface ToolsPanelProps {
  isOpen: boolean;
  onClose: () => void;
}

export function ToolsPanel({ isOpen, onClose }: ToolsPanelProps) {
  const { formatCurrency, convertCurrency } = useSettings();
  const [converterAmount, setConverterAmount] = useState(1000000);
  const [converterFrom, setConverterFrom] = useState<'XAF' | 'USD' | 'EUR' | 'GBP' | 'CNY'>('XAF');

  if (!isOpen) return null;

  return (
    <div className="tools-overlay" onClick={onClose}>
      <div className="tools-panel" onClick={e => e.stopPropagation()}>
        <div className="tools-header">
          <h2>🛠️ Outils</h2>
          <button onClick={onClose} className="btn-close-tools" aria-label="Fermer">
            ✕
          </button>
        </div>

        <div className="tools-content">
          <div className="tool-section">
            <h3>💱 Convertisseur de Devise</h3>
            <p className="tool-description">
              Convertissez des montants entre différentes devises selon les taux configurés.
            </p>
            
            <div className="converter-tool">
              <CurrencyConverter
                amount={converterAmount}
                from={converterFrom}
                onAmountChange={(amount, currency) => {
                  setConverterAmount(amount);
                  setConverterFrom(currency);
                }}
              />
              
              <div className="conversion-results">
                <h4>Résultats de conversion</h4>
                <div className="conversion-grid">
                  {(['XAF', 'USD', 'EUR', 'GBP', 'CNY'] as const).map(currency => {
                    const converted = convertCurrency(converterAmount, converterFrom, currency);
                    return (
                      <div key={currency} className="conversion-item">
                        <span className="conversion-currency">{currency}</span>
                        <span className="conversion-value">{formatCurrency(converted)}</span>
                      </div>
                    );
                  })}
                </div>
              </div>
            </div>
          </div>

          <div className="tool-section">
            <h3>📊 Calculatrice Douanière</h3>
            <p className="tool-description">
              Calculez rapidement les droits et taxes pour un montant donné.
            </p>
            
            <div className="calculator-tool">
              <div className="calc-inputs">
                <label>
                  <span>Valeur CIF</span>
                  <input
                    type="number"
                    placeholder="1000000"
                    className="calc-input"
                  />
                </label>
                <label>
                  <span>Taux DD (%)</span>
                  <input
                    type="number"
                    placeholder="20"
                    step="0.1"
                    className="calc-input"
                  />
                </label>
                <label>
                  <span>Taux TVA (%)</span>
                  <input
                    type="number"
                    placeholder="19.25"
                    step="0.1"
                    className="calc-input"
                  />
                </label>
              </div>
              <button className="btn-calculate">Calculer</button>
            </div>
          </div>

          <div className="tool-section">
            <h3>📐 Calculateur de Taux</h3>
            <p className="tool-description">
              Calculez les taux de change inverses et les pourcentages.
            </p>
            
            <div className="rate-calculator">
              <p className="coming-soon">🚧 Fonctionnalité à venir</p>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

