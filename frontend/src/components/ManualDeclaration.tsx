import { useState } from 'react';
import './ManualDeclaration.css';
import { SydoniaForm } from './SydoniaForm';

interface TarifResult {
  code_sh: string;
  libelle: string;
  ddi: number;
  dso: number;
  dac: number;
  stt: number;
  tva: number;
  tpm: string;
  tci: number;
  cci: number;
  oad: number;
  taux_total: number;
}

interface SearchResponse {
  query: string;
  total_results: number;
  results: TarifResult[];
}

interface CalculationResult {
  valeur_cif: number;
  code_sh: string;
  libelle: string;
  droits_douane: number;
  tva: number;
  tci: number;
  cci: number;
  oad: number;
  total_taxes: number;
  valeur_totale: number;
}

interface ManualDeclarationProps {
  backendUrl: string;
  onDeclare: (calculation: CalculationResult) => void;
  onBack?: () => void;
}

export function ManualDeclaration({ backendUrl, onDeclare, onBack }: ManualDeclarationProps) {
  const [searchType, setSearchType] = useState<'code' | 'keyword'>('code');
  const [searchQuery, setSearchQuery] = useState('');
  const [results, setResults] = useState<TarifResult[]>([]);
  const [selectedTarif, setSelectedTarif] = useState<TarifResult | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [showSydoniaForm, setShowSydoniaForm] = useState(false);
  const [currentCalculation, setCurrentCalculation] = useState<CalculationResult | null>(null);

  // Données de la déclaration
  const [valeurCIF, setValeurCIF] = useState<string>('');
  const [quantite, setQuantite] = useState<string>('1');
  const [paysOrigine, setPaysOrigine] = useState('');
  const [calculation, setCalculation] = useState<CalculationResult | null>(null);

  const handleSearch = async () => {
    if (!searchQuery.trim()) {
      setError('Veuillez entrer un terme de recherche');
      return;
    }

    setLoading(true);
    setError(null);
    setResults([]);
    setSelectedTarif(null);
    setCalculation(null);

    try {
      const endpoint = searchType === 'code' ? '/api/hs/search/code' : '/api/hs/search/keyword';
      const response = await fetch(
        `${backendUrl}${endpoint}?q=${encodeURIComponent(searchQuery)}&limit=50`
      );

      if (!response.ok) {
        throw new Error(`Erreur: ${response.status}`);
      }

      const data: SearchResponse = await response.json();
      setResults(data.results);

      if (data.results.length === 0) {
        setError('Aucun résultat trouvé');
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Erreur de recherche');
    } finally {
      setLoading(false);
    }
  };

  const handleKeyPress = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter') {
      handleSearch();
    }
  };

  const handleSelectTarif = (tarif: TarifResult) => {
    setSelectedTarif(tarif);
    setCalculation(null);
  };

  const handleCalculate = () => {
    if (!selectedTarif) {
      setError('Veuillez sélectionner un code SH');
      return;
    }

    const cifValue = parseFloat(valeurCIF);
    if (!cifValue || cifValue <= 0) {
      setError('Veuillez entrer une valeur CIF valide');
      return;
    }

    const cif = cifValue;
    const dd = (cif * selectedTarif.ddi) / 100;
    const assiette_tva = cif + dd;
    const tva = (assiette_tva * selectedTarif.tva) / 100;
    const tci = (cif * selectedTarif.tci) / 100;
    const cci = (cif * selectedTarif.cci) / 100;
    const oad = (cif * selectedTarif.oad) / 100;
    const total_taxes = dd + tva + tci + cci + oad;
    const valeur_totale = cif + total_taxes;

    const calc: CalculationResult = {
      valeur_cif: cif,
      code_sh: selectedTarif.code_sh,
      libelle: selectedTarif.libelle,
      droits_douane: dd,
      tva: tva,
      tci: tci,
      cci: cci,
      oad: oad,
      total_taxes: total_taxes,
      valeur_totale: valeur_totale,
    };

    setCalculation(calc);
    setError(null);
  };

  const handleDeclare = () => {
    if (calculation) {
      setCurrentCalculation(calculation);
      setShowSydoniaForm(true);
    }
  };

  const handleCloseSydonia = () => {
    setShowSydoniaForm(false);
  };

  const handleExportSydonia = () => {
    if (currentCalculation) {
      onDeclare(currentCalculation);
    }
    setShowSydoniaForm(false);
  };

  return (
    <div className="manual-declaration">
      <div className="declaration-header">
        {onBack && (
          <button className="btn-back" onClick={onBack} title="Retour à l'accueil">
            ← Retour
          </button>
        )}
        <h2>📝 Déclaration Manuelle</h2>
        <p className="declaration-description">
          Recherchez un code SH, calculez les taxes, et générez une déclaration SYDONIA
        </p>
      </div>

      {/* Section Recherche */}
      <div className="search-section">
        <h3>🔍 Recherche de Code SH</h3>

        <div className="search-controls">
          <div className="search-type-selector">
            <button
              className={`type-btn ${searchType === 'code' ? 'active' : ''}`}
              onClick={() => setSearchType('code')}
            >
              Par Code
            </button>
            <button
              className={`type-btn ${searchType === 'keyword' ? 'active' : ''}`}
              onClick={() => setSearchType('keyword')}
            >
              Par Mot-clé
            </button>
          </div>

          <div className="search-input-group">
            <input
              type="text"
              className="search-input"
              placeholder={
                searchType === 'code'
                  ? 'Ex: 0302, 6109, 8517...'
                  : 'Ex: poisson, téléphone, chemise...'
              }
              value={searchQuery}
              onChange={e => setSearchQuery(e.target.value)}
              onKeyPress={handleKeyPress}
            />
            <button className="search-btn" onClick={handleSearch} disabled={loading}>
              {loading ? '⏳' : '🔍'} Rechercher
            </button>
          </div>
        </div>

        {error && <div className="search-error">⚠️ {error}</div>}

        {results.length > 0 && (
          <div className="search-results">
            <div className="results-header">
              <strong>{results.length}</strong> résultat{results.length > 1 ? 's' : ''} trouvé
              {results.length > 1 ? 's' : ''}
            </div>

            <div className="results-list">
              {results.map(tarif => (
                <div
                  key={tarif.code_sh}
                  className={`result-item ${
                    selectedTarif?.code_sh === tarif.code_sh ? 'selected' : ''
                  }`}
                  onClick={() => handleSelectTarif(tarif)}
                >
                  <div className="result-code">
                    <strong>{tarif.code_sh}</strong>
                  </div>
                  <div className="result-libelle">{tarif.libelle}</div>
                  <div className="result-rates">
                    <span className="rate-badge">DDI: {tarif.ddi}%</span>
                    <span className="rate-badge">TVA: {tarif.tva}%</span>
                    <span className="rate-badge total">Total: {tarif.taux_total}%</span>
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}
      </div>

      {/* Section Calcul */}
      {selectedTarif && (
        <div className="calculation-section">
          <h3>💰 Calcul des Taxes</h3>

          <div className="selected-tarif-info">
            <div className="info-row">
              <label>Code SH:</label>
              <strong>{selectedTarif.code_sh}</strong>
            </div>
            <div className="info-row">
              <label>Libellé:</label>
              <span>{selectedTarif.libelle}</span>
            </div>
          </div>

          <div className="calculation-inputs">
            <div className="input-group">
              <label>Valeur CIF (XAF)</label>
              <input
                type="number"
                className="calc-input"
                placeholder="1000000"
                value={valeurCIF}
                onChange={e => setValeurCIF(e.target.value)}
              />
            </div>

            <div className="input-group">
              <label>Quantité</label>
              <input
                type="number"
                className="calc-input"
                placeholder="1"
                value={quantite}
                onChange={e => setQuantite(e.target.value)}
              />
            </div>

            <div className="input-group">
              <label>Pays d&apos;origine</label>
              <input
                type="text"
                className="calc-input"
                placeholder="Ex: Chine, France..."
                value={paysOrigine}
                onChange={e => setPaysOrigine(e.target.value)}
              />
            </div>
          </div>

          <button className="btn-calculate" onClick={handleCalculate}>
            📊 Calculer les Taxes
          </button>

          {calculation && (
            <div className="calculation-results">
              <h4>Résultats du Calcul</h4>

              <div className="results-grid">
                <div className="result-row">
                  <span>Valeur CIF:</span>
                  <strong>{calculation.valeur_cif.toLocaleString('fr-FR')} XAF</strong>
                </div>
                <div className="result-row highlight">
                  <span>Droits de Douane ({selectedTarif.ddi}%):</span>
                  <strong>{calculation.droits_douane.toLocaleString('fr-FR')} XAF</strong>
                </div>
                <div className="result-row highlight">
                  <span>TVA ({selectedTarif.tva}%):</span>
                  <strong>{calculation.tva.toLocaleString('fr-FR')} XAF</strong>
                </div>
                <div className="result-row">
                  <span>TCI ({selectedTarif.tci}%):</span>
                  <strong>{calculation.tci.toLocaleString('fr-FR')} XAF</strong>
                </div>
                <div className="result-row">
                  <span>CCI ({selectedTarif.cci}%):</span>
                  <strong>{calculation.cci.toLocaleString('fr-FR')} XAF</strong>
                </div>
                <div className="result-row">
                  <span>OAD ({selectedTarif.oad}%):</span>
                  <strong>{calculation.oad.toLocaleString('fr-FR')} XAF</strong>
                </div>
                <div className="result-row total">
                  <span>Total des Taxes:</span>
                  <strong>{calculation.total_taxes.toLocaleString('fr-FR')} XAF</strong>
                </div>
                <div className="result-row grand-total">
                  <span>Valeur Totale:</span>
                  <strong>{calculation.valeur_totale.toLocaleString('fr-FR')} XAF</strong>
                </div>
              </div>

              <button className="btn-declare" onClick={handleDeclare}>
                ✅ Déclarer (Formulaire SYDONIA)
              </button>
            </div>
          )}
        </div>
      )}

      {showSydoniaForm && currentCalculation && (
        <SydoniaForm
          calculation={currentCalculation}
          onClose={handleCloseSydonia}
          onExport={handleExportSydonia}
        />
      )}
    </div>
  );
}
