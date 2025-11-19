import { useState } from 'react';
import './SydoniaForm.css';

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

interface SydoniaFormProps {
  calculation: CalculationResult;
  onClose: () => void;
  onExport: () => void;
}

export function SydoniaForm({ calculation, onClose, onExport }: SydoniaFormProps) {
  const [showExportOptions, setShowExportOptions] = useState(false);
  const [formData, setFormData] = useState({
    // Informations générales
    numero_declaration: '',
    date_declaration: new Date().toISOString().split('T')[0],
    bureau_douane: '',
    regime_douanier: '4000', // Importation définitive

    // Importateur
    nom_importateur: '',
    adresse_importateur: '',
    nif_importateur: '',

    // Exportateur
    nom_exportateur: '',
    pays_exportation: '',

    // Transport
    mode_transport: '3', // Route
    pays_provenance: '',
    pays_origine: '',

    // Marchandise
    code_sh: calculation.code_sh,
    designation: calculation.libelle,
    quantite: 1,
    unite_mesure: 'KGM',
    poids_net: 0,
    poids_brut: 0,

    // Valeur
    valeur_cif: calculation.valeur_cif,
    monnaie: 'XAF',
    taux_change: 1,

    // Taxes
    droits_douane: calculation.droits_douane,
    tva: calculation.tva,
    tci: calculation.tci,
    cci: calculation.cci,
    oad: calculation.oad,
    total_taxes: calculation.total_taxes,
    valeur_totale: calculation.valeur_totale,

    // Documents joints
    facture_commerciale: '',
    connaissement: '',
    certificat_origine: '',
  });

  const handleChange = (field: string, value: string | number) => {
    setFormData(prev => ({ ...prev, [field]: value }));
  };

  const handleExportPDF = async () => {
    try {
      // Générer PDF côté serveur ou client
      const response = await fetch(
        `${import.meta.env.VITE_API_URL || 'http://127.0.0.1:8000'}/api/export/sydonia/pdf`,
        {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(formData),
        }
      );

      if (response.ok) {
        const blob = await response.blob();
        const url = window.URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = `SYDONIA_${formData.code_sh}_${formData.date_declaration}.pdf`;
        a.click();
        window.URL.revokeObjectURL(url);
        onExport();
      }
    } catch {
      alert("Erreur lors de l'export PDF");
    }
  };

  const handleExportCSV = () => {
    const csvContent = [
      ['Champ', 'Valeur'],
      ['N° Déclaration', formData.numero_declaration],
      ['Date', formData.date_declaration],
      ['Bureau de Douane', formData.bureau_douane],
      ['Régime Douanier', formData.regime_douanier],
      ['Importateur', formData.nom_importateur],
      ['NIF', formData.nif_importateur],
      ['Exportateur', formData.nom_exportateur],
      ['Pays Exportation', formData.pays_exportation],
      ['Mode Transport', formData.mode_transport],
      ['Pays Provenance', formData.pays_provenance],
      ['Pays Origine', formData.pays_origine],
      ['Code SH', formData.code_sh],
      ['Désignation', formData.designation],
      ['Quantité', formData.quantite],
      ['Unité', formData.unite_mesure],
      ['Poids Net', formData.poids_net],
      ['Poids Brut', formData.poids_brut],
      ['Valeur CIF', `${formData.valeur_cif} ${formData.monnaie}`],
      ['Droits de Douane', `${formData.droits_douane} XAF`],
      ['TVA', `${formData.tva} XAF`],
      ['TCI', `${formData.tci} XAF`],
      ['CCI', `${formData.cci} XAF`],
      ['OAD', `${formData.oad} XAF`],
      ['Total Taxes', `${formData.total_taxes} XAF`],
      ['Valeur Totale', `${formData.valeur_totale} XAF`],
      ['Facture Commerciale', formData.facture_commerciale],
      ['Connaissement', formData.connaissement],
      ['Certificat Origine', formData.certificat_origine],
    ]
      .map(row => row.map(cell => `"${cell}"`).join(';'))
      .join('\n');

    const blob = new Blob([csvContent], { type: 'text/csv;charset=utf-8;' });
    const url = window.URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `SYDONIA_${formData.code_sh}_${formData.date_declaration}.csv`;
    a.click();
    window.URL.revokeObjectURL(url);
    onExport();
  };

  const handleExportXML = () => {
    const xml = `<?xml version="1.0" encoding="UTF-8"?>
<DeclarationSYDONIA>
  <Informations>
    <NumeroDeclaration>${formData.numero_declaration}</NumeroDeclaration>
    <DateDeclaration>${formData.date_declaration}</DateDeclaration>
    <BureauDouane>${formData.bureau_douane}</BureauDouane>
    <RegimeDouanier>${formData.regime_douanier}</RegimeDouanier>
  </Informations>
  <Importateur>
    <Nom>${formData.nom_importateur}</Nom>
    <Adresse>${formData.adresse_importateur}</Adresse>
    <NIF>${formData.nif_importateur}</NIF>
  </Importateur>
  <Exportateur>
    <Nom>${formData.nom_exportateur}</Nom>
    <PaysExportation>${formData.pays_exportation}</PaysExportation>
  </Exportateur>
  <Transport>
    <ModeTransport>${formData.mode_transport}</ModeTransport>
    <PaysProvenance>${formData.pays_provenance}</PaysProvenance>
    <PaysOrigine>${formData.pays_origine}</PaysOrigine>
  </Transport>
  <Marchandise>
    <CodeSH>${formData.code_sh}</CodeSH>
    <Designation>${formData.designation}</Designation>
    <Quantite>${formData.quantite}</Quantite>
    <UniteMesure>${formData.unite_mesure}</UniteMesure>
    <PoidsNet>${formData.poids_net}</PoidsNet>
    <PoidsBrut>${formData.poids_brut}</PoidsBrut>
  </Marchandise>
  <Valeur>
    <ValeurCIF>${formData.valeur_cif}</ValeurCIF>
    <Monnaie>${formData.monnaie}</Monnaie>
    <TauxChange>${formData.taux_change}</TauxChange>
  </Valeur>
  <Taxes>
    <DroitsDouane>${formData.droits_douane}</DroitsDouane>
    <TVA>${formData.tva}</TVA>
    <TCI>${formData.tci}</TCI>
    <CCI>${formData.cci}</CCI>
    <OAD>${formData.oad}</OAD>
    <TotalTaxes>${formData.total_taxes}</TotalTaxes>
    <ValeurTotale>${formData.valeur_totale}</ValeurTotale>
  </Taxes>
  <Documents>
    <FactureCommerciale>${formData.facture_commerciale}</FactureCommerciale>
    <Connaissement>${formData.connaissement}</Connaissement>
    <CertificatOrigine>${formData.certificat_origine}</CertificatOrigine>
  </Documents>
</DeclarationSYDONIA>`;

    const blob = new Blob([xml], { type: 'application/xml' });
    const url = window.URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `SYDONIA_${formData.code_sh}_${formData.date_declaration}.xml`;
    a.click();
    window.URL.revokeObjectURL(url);
    onExport();
  };

  const handleExportImage = async () => {
    alert(
      "Export Image: Installez d'abord html2canvas avec la commande: npm install html2canvas\n\nEn attendant, utilisez PDF, CSV ou XML."
    );
    /*
    try {
      // Capture du formulaire en image
      const formElement = document.querySelector('.sydonia-content') as HTMLElement;
      if (!formElement) return;

      // Utiliser html2canvas (à installer: npm install html2canvas)
      const html2canvas = (await import('html2canvas')).default;
      const canvas = await html2canvas(formElement, {
        scale: 2,
        logging: false,
        backgroundColor: '#ffffff',
      });

      canvas.toBlob((blob: Blob | null) => {
        if (blob) {
          const url = window.URL.createObjectURL(blob);
          const a = document.createElement('a');
          a.href = url;
          a.download = `SYDONIA_${formData.code_sh}_${formData.date_declaration}.png`;
          a.click();
          window.URL.revokeObjectURL(url);
          onExport();
        }
      });
    } catch {
      alert("Erreur lors de l'export image. Installez html2canvas: npm install html2canvas");
    }
    */
  };

  return (
    <div className="sydonia-overlay">
      <div className="sydonia-form">
        <div className="sydonia-header">
          <h2>📋 Déclaration SYDONIA</h2>
          <button className="btn-close-sydonia" onClick={onClose}>
            ✕
          </button>
        </div>

        <div className="sydonia-content">
          {/* Section 1: Informations générales */}
          <div className="form-section">
            <h3>1. Informations Générales</h3>
            <div className="form-grid">
              <div className="form-field">
                <label>N° de Déclaration</label>
                <input
                  type="text"
                  value={formData.numero_declaration}
                  onChange={e => handleChange('numero_declaration', e.target.value)}
                  placeholder="Auto-généré"
                />
              </div>
              <div className="form-field">
                <label>Date de Déclaration</label>
                <input
                  type="date"
                  value={formData.date_declaration}
                  onChange={e => handleChange('date_declaration', e.target.value)}
                />
              </div>
              <div className="form-field">
                <label>Bureau de Douane</label>
                <input
                  type="text"
                  value={formData.bureau_douane}
                  onChange={e => handleChange('bureau_douane', e.target.value)}
                  placeholder="Ex: Douala Port"
                />
              </div>
              <div className="form-field">
                <label>Régime Douanier</label>
                <select
                  value={formData.regime_douanier}
                  onChange={e => handleChange('regime_douanier', e.target.value)}
                >
                  <option value="4000">4000 - Importation définitive</option>
                  <option value="4100">4100 - Admission temporaire</option>
                  <option value="4200">4200 - Entrepôt douanier</option>
                </select>
              </div>
            </div>
          </div>

          {/* Section 2: Importateur */}
          <div className="form-section">
            <h3>2. Importateur</h3>
            <div className="form-grid">
              <div className="form-field full-width">
                <label>Nom / Raison Sociale</label>
                <input
                  type="text"
                  value={formData.nom_importateur}
                  onChange={e => handleChange('nom_importateur', e.target.value)}
                  placeholder="Nom de l'importateur"
                />
              </div>
              <div className="form-field full-width">
                <label>Adresse</label>
                <input
                  type="text"
                  value={formData.adresse_importateur}
                  onChange={e => handleChange('adresse_importateur', e.target.value)}
                  placeholder="Adresse complète"
                />
              </div>
              <div className="form-field">
                <label>NIF (N° Identification Fiscale)</label>
                <input
                  type="text"
                  value={formData.nif_importateur}
                  onChange={e => handleChange('nif_importateur', e.target.value)}
                  placeholder="NIF"
                />
              </div>
            </div>
          </div>

          {/* Section 3: Exportateur */}
          <div className="form-section">
            <h3>3. Exportateur</h3>
            <div className="form-grid">
              <div className="form-field full-width">
                <label>Nom de l&apos;Exportateur</label>
                <input
                  type="text"
                  value={formData.nom_exportateur}
                  onChange={e => handleChange('nom_exportateur', e.target.value)}
                  placeholder="Nom de l'exportateur"
                />
              </div>
              <div className="form-field">
                <label>Pays d&apos;Exportation</label>
                <input
                  type="text"
                  value={formData.pays_exportation}
                  onChange={e => handleChange('pays_exportation', e.target.value)}
                  placeholder="Ex: Chine, France..."
                />
              </div>
            </div>
          </div>

          {/* Section 4: Transport */}
          <div className="form-section">
            <h3>4. Transport et Provenance</h3>
            <div className="form-grid">
              <div className="form-field">
                <label>Mode de Transport</label>
                <select
                  value={formData.mode_transport}
                  onChange={e => handleChange('mode_transport', e.target.value)}
                >
                  <option value="1">1 - Maritime</option>
                  <option value="2">2 - Chemin de fer</option>
                  <option value="3">3 - Route</option>
                  <option value="4">4 - Aérien</option>
                </select>
              </div>
              <div className="form-field">
                <label>Pays de Provenance</label>
                <input
                  type="text"
                  value={formData.pays_provenance}
                  onChange={e => handleChange('pays_provenance', e.target.value)}
                  placeholder="Pays de provenance"
                />
              </div>
              <div className="form-field">
                <label>Pays d&apos;Origine</label>
                <input
                  type="text"
                  value={formData.pays_origine}
                  onChange={e => handleChange('pays_origine', e.target.value)}
                  placeholder="Pays d'origine"
                />
              </div>
            </div>
          </div>

          {/* Section 5: Marchandise */}
          <div className="form-section highlight">
            <h3>5. Description de la Marchandise</h3>
            <div className="form-grid">
              <div className="form-field">
                <label>Code SH</label>
                <input
                  type="text"
                  value={formData.code_sh}
                  onChange={e => handleChange('code_sh', e.target.value)}
                  className="code-sh-input"
                  readOnly
                />
              </div>
              <div className="form-field full-width">
                <label>Désignation Commerciale</label>
                <textarea
                  value={formData.designation}
                  onChange={e => handleChange('designation', e.target.value)}
                  rows={2}
                />
              </div>
              <div className="form-field">
                <label>Quantité</label>
                <input
                  type="number"
                  value={formData.quantite}
                  onChange={e => handleChange('quantite', parseFloat(e.target.value))}
                />
              </div>
              <div className="form-field">
                <label>Unité de Mesure</label>
                <select
                  value={formData.unite_mesure}
                  onChange={e => handleChange('unite_mesure', e.target.value)}
                >
                  <option value="KGM">KGM - Kilogramme</option>
                  <option value="TET">TET - Tête/Unité</option>
                  <option value="MTR">MTR - Mètre</option>
                  <option value="LTR">LTR - Litre</option>
                </select>
              </div>
              <div className="form-field">
                <label>Poids Net (kg)</label>
                <input
                  type="number"
                  value={formData.poids_net}
                  onChange={e => handleChange('poids_net', parseFloat(e.target.value))}
                />
              </div>
              <div className="form-field">
                <label>Poids Brut (kg)</label>
                <input
                  type="number"
                  value={formData.poids_brut}
                  onChange={e => handleChange('poids_brut', parseFloat(e.target.value))}
                />
              </div>
            </div>
          </div>

          {/* Section 6: Valeur */}
          <div className="form-section highlight">
            <h3>6. Valeur en Douane</h3>
            <div className="form-grid">
              <div className="form-field">
                <label>Valeur CIF</label>
                <input
                  type="number"
                  value={formData.valeur_cif}
                  onChange={e => handleChange('valeur_cif', parseFloat(e.target.value))}
                  className="value-input"
                />
              </div>
              <div className="form-field">
                <label>Monnaie</label>
                <select
                  value={formData.monnaie}
                  onChange={e => handleChange('monnaie', e.target.value)}
                >
                  <option value="XAF">XAF - Franc CFA</option>
                  <option value="USD">USD - Dollar</option>
                  <option value="EUR">EUR - Euro</option>
                </select>
              </div>
              <div className="form-field">
                <label>Taux de Change</label>
                <input
                  type="number"
                  value={formData.taux_change}
                  onChange={e => handleChange('taux_change', parseFloat(e.target.value))}
                />
              </div>
            </div>
          </div>

          {/* Section 7: Liquidation */}
          <div className="form-section taxes-section">
            <h3>7. Liquidation des Droits et Taxes</h3>
            <div className="taxes-table">
              <div className="tax-row">
                <span className="tax-label">Droits de Douane (DDI):</span>
                <span className="tax-value">
                  {formData.droits_douane.toLocaleString('fr-FR')} XAF
                </span>
              </div>
              <div className="tax-row">
                <span className="tax-label">TVA:</span>
                <span className="tax-value">{formData.tva.toLocaleString('fr-FR')} XAF</span>
              </div>
              <div className="tax-row">
                <span className="tax-label">TCI (Taxe Communautaire):</span>
                <span className="tax-value">{formData.tci.toLocaleString('fr-FR')} XAF</span>
              </div>
              <div className="tax-row">
                <span className="tax-label">CCI (Contribution Communautaire):</span>
                <span className="tax-value">{formData.cci.toLocaleString('fr-FR')} XAF</span>
              </div>
              <div className="tax-row">
                <span className="tax-label">OAD (Autres Droits):</span>
                <span className="tax-value">{formData.oad.toLocaleString('fr-FR')} XAF</span>
              </div>
              <div className="tax-row total">
                <span className="tax-label">TOTAL DES TAXES:</span>
                <span className="tax-value">
                  {formData.total_taxes.toLocaleString('fr-FR')} XAF
                </span>
              </div>
              <div className="tax-row grand-total">
                <span className="tax-label">VALEUR TOTALE (CIF + Taxes):</span>
                <span className="tax-value">
                  {formData.valeur_totale.toLocaleString('fr-FR')} XAF
                </span>
              </div>
            </div>
          </div>

          {/* Section 8: Documents */}
          <div className="form-section">
            <h3>8. Documents Justificatifs</h3>
            <div className="form-grid">
              <div className="form-field">
                <label>N° Facture Commerciale</label>
                <input
                  type="text"
                  value={formData.facture_commerciale}
                  onChange={e => handleChange('facture_commerciale', e.target.value)}
                  placeholder="N° de facture"
                />
              </div>
              <div className="form-field">
                <label>N° Connaissement / LTA</label>
                <input
                  type="text"
                  value={formData.connaissement}
                  onChange={e => handleChange('connaissement', e.target.value)}
                  placeholder="N° de connaissement"
                />
              </div>
              <div className="form-field">
                <label>N° Certificat d&apos;Origine</label>
                <input
                  type="text"
                  value={formData.certificat_origine}
                  onChange={e => handleChange('certificat_origine', e.target.value)}
                  placeholder="N° de certificat"
                />
              </div>
            </div>
          </div>
        </div>

        <div className="sydonia-footer">
          <button className="btn-cancel" onClick={onClose}>
            Annuler
          </button>

          {!showExportOptions ? (
            <button className="btn-export-sydonia" onClick={() => setShowExportOptions(true)}>
              📤 Exporter la Déclaration
            </button>
          ) : (
            <div className="export-options">
              <button className="export-btn pdf" onClick={handleExportPDF}>
                📄 PDF
              </button>
              <button className="export-btn csv" onClick={handleExportCSV}>
                📊 CSV
              </button>
              <button className="export-btn xml" onClick={handleExportXML}>
                🗂️ XML
              </button>
              <button className="export-btn image" onClick={handleExportImage}>
                🖼️ Image
              </button>
              <button
                className="export-btn cancel-export"
                onClick={() => setShowExportOptions(false)}
              >
                ← Retour
              </button>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
