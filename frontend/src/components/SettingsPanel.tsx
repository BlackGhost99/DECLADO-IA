import { useState } from 'react';
import { useSettings, type Theme, type Currency } from '../contexts/SettingsContext';
import { formatExchangeRate, getInverseRate } from '../utils/currencyUtils';
import './SettingsPanel.css';

interface SettingsPanelProps {
  isOpen: boolean;
  onClose: () => void;
}

export function SettingsPanel({ isOpen, onClose }: SettingsPanelProps) {
  const { settings, updateSettings, resetSettings, refreshExchangeRates, validateRate } =
    useSettings();
  const [activeTab, setActiveTab] = useState<'general' | 'currency' | 'theme' | 'advanced'>(
    'general'
  );
  const [rateErrors, setRateErrors] = useState<Record<string, string>>({});

  if (!isOpen) return null;

  return (
    <div className="settings-overlay" onClick={onClose}>
      <div className="settings-panel" onClick={e => e.stopPropagation()}>
        <div className="settings-header">
          <h2>⚙️ Paramètres</h2>
          <button onClick={onClose} className="btn-close-settings" aria-label="Fermer">
            ✕
          </button>
        </div>

        <div className="settings-tabs">
          <button
            className={`settings-tab ${activeTab === 'general' ? 'active' : ''}`}
            onClick={() => setActiveTab('general')}
          >
            Général
          </button>
          <button
            className={`settings-tab ${activeTab === 'currency' ? 'active' : ''}`}
            onClick={() => setActiveTab('currency')}
          >
            Devises
          </button>
          <button
            className={`settings-tab ${activeTab === 'theme' ? 'active' : ''}`}
            onClick={() => setActiveTab('theme')}
          >
            Thème
          </button>
          <button
            className={`settings-tab ${activeTab === 'advanced' ? 'active' : ''}`}
            onClick={() => setActiveTab('advanced')}
          >
            Avancé
          </button>
        </div>

        <div className="settings-content">
          {activeTab === 'general' && (
            <div className="settings-section">
              <h3>Préférences générales</h3>

              <div className="setting-item">
                <label>
                  <span>Langue</span>
                  <select
                    value={settings.language}
                    onChange={e => updateSettings({ language: e.target.value })}
                  >
                    <option value="fr">Français</option>
                    <option value="en">English</option>
                  </select>
                </label>
              </div>

              <div className="setting-item">
                <label className="checkbox-label">
                  <input
                    type="checkbox"
                    checked={settings.autoProcess}
                    onChange={e => updateSettings({ autoProcess: e.target.checked })}
                  />
                  <span>Traitement automatique après import</span>
                </label>
              </div>

              <div className="setting-item">
                <label className="checkbox-label">
                  <input
                    type="checkbox"
                    checked={settings.showPreview}
                    onChange={e => updateSettings({ showPreview: e.target.checked })}
                  />
                  <span>Afficher la prévisualisation des fichiers</span>
                </label>
              </div>

              <div className="setting-item">
                <label>
                  <span>Taille de prévisualisation</span>
                  <select
                    value={settings.previewSize}
                    onChange={e =>
                      updateSettings({
                        previewSize: e.target.value as 'small' | 'medium' | 'large',
                      })
                    }
                  >
                    <option value="small">Petite</option>
                    <option value="medium">Moyenne</option>
                    <option value="large">Grande</option>
                  </select>
                </label>
              </div>
            </div>
          )}

          {activeTab === 'currency' && (
            <div className="settings-section">
              <h3>Gestion des devises</h3>

              <div className="setting-item">
                <label>
                  <span>Devise par défaut</span>
                  <select
                    value={settings.currency}
                    onChange={e => updateSettings({ currency: e.target.value as Currency })}
                  >
                    <option value="XAF">FCFA (XAF)</option>
                    <option value="USD">Dollar US (USD)</option>
                    <option value="EUR">Euro (EUR)</option>
                    <option value="GBP">Livre Sterling (GBP)</option>
                    <option value="CNY">Yuan Chinois (CNY)</option>
                  </select>
                </label>
              </div>

              <div className="exchange-rates">
                <div className="exchange-rates-header">
                  <h4>Taux de change (vers FCFA)</h4>
                  <button
                    onClick={() => refreshExchangeRates()}
                    className="btn-refresh-rates"
                    title="Rafraîchir depuis le backend"
                  >
                    🔄 Actualiser
                  </button>
                </div>

                {(['USD', 'EUR', 'GBP', 'CNY'] as Currency[]).map(currency => {
                  const rate = settings.exchangeRates[currency];
                  const isValid = validateRate(rate, currency);
                  const error = rateErrors[currency];

                  return (
                    <div key={currency} className="exchange-rate-item">
                      <label>
                        <span className="rate-label">1 {currency} =</span>
                        <input
                          type="number"
                          step="0.0001"
                          min="0.0001"
                          value={rate}
                          onChange={e => {
                            const value = parseFloat(e.target.value);
                            const errors = { ...rateErrors };

                            if (isNaN(value) || value <= 0) {
                              errors[currency] = 'Le taux doit être un nombre positif';
                            } else if (!validateRate(value, currency)) {
                              errors[currency] = 'Taux hors des limites acceptables';
                            } else {
                              delete errors[currency];
                            }

                            setRateErrors(errors);

                            if (!errors[currency]) {
                              const newRates = {
                                ...settings.exchangeRates,
                                [currency]: value,
                              };
                              updateSettings({ exchangeRates: newRates });
                            }
                          }}
                          className={error || !isValid ? 'rate-input-error' : ''}
                        />
                        <span className="rate-unit">FCFA</span>
                      </label>
                      {error && <span className="rate-error-message">{error}</span>}
                      {!error && isValid && (
                        <div className="rate-info">
                          <span className="rate-display">{formatExchangeRate(rate, currency)}</span>
                          <span className="rate-inverse">
                            1 XAF ={' '}
                            {getInverseRate(rate).toLocaleString('fr-FR', {
                              minimumFractionDigits: 6,
                              maximumFractionDigits: 6,
                            })}{' '}
                            {currency}
                          </span>
                        </div>
                      )}
                    </div>
                  );
                })}
              </div>

              <div className="currency-info">
                <p>💡 Les montants seront automatiquement convertis selon ces taux.</p>
              </div>
            </div>
          )}

          {activeTab === 'theme' && (
            <div className="settings-section">
              <h3>Thème visuel</h3>

              <div className="theme-selector">
                {(['dark', 'light', 'custom'] as Theme[]).map(theme => (
                  <button
                    key={theme}
                    className={`theme-option ${settings.theme === theme ? 'active' : ''}`}
                    onClick={() => updateSettings({ theme })}
                  >
                    <div className={`theme-preview theme-${theme}`}>
                      <div className="theme-preview-header"></div>
                      <div className="theme-preview-content"></div>
                    </div>
                    <span>
                      {theme === 'dark'
                        ? '🌙 Sombre'
                        : theme === 'light'
                          ? '☀️ Clair'
                          : '🎨 Personnalisé'}
                    </span>
                  </button>
                ))}
              </div>

              {settings.theme === 'custom' && (
                <div className="custom-theme-editor">
                  <h4>Personnalisation</h4>
                  <p className="coming-soon">🚧 Fonctionnalité à venir</p>
                </div>
              )}
            </div>
          )}

          {activeTab === 'advanced' && (
            <div className="settings-section">
              <h3>Paramètres avancés</h3>

              <div className="setting-item">
                <label>
                  <span>Répertoire de sauvegarde</span>
                  <input
                    type="text"
                    value={localStorage.getItem('export-path') || 'Téléchargements'}
                    onChange={e => localStorage.setItem('export-path', e.target.value)}
                    placeholder="Chemin de sauvegarde"
                  />
                </label>
              </div>

              <div className="setting-item">
                <label>
                  <span>Format d&apos;export par défaut</span>
                  <select defaultValue="pdf">
                    <option value="pdf">PDF</option>
                    <option value="xml_esad">XML eSAD</option>
                    <option value="csv">CSV</option>
                    <option value="json">JSON</option>
                  </select>
                </label>
              </div>

              <div className="settings-actions">
                <button onClick={resetSettings} className="btn-reset-settings">
                  🔄 Réinitialiser les paramètres
                </button>
                <button
                  onClick={() => {
                    const data = JSON.stringify(settings, null, 2);
                    const blob = new Blob([data], { type: 'application/json' });
                    const url = URL.createObjectURL(blob);
                    const a = document.createElement('a');
                    a.href = url;
                    a.download = 'declado-settings.json';
                    a.click();
                    URL.revokeObjectURL(url);
                  }}
                  className="btn-export-settings"
                >
                  💾 Exporter les paramètres
                </button>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
