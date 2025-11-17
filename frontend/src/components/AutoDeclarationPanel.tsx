import { useState } from 'react';
import './AutoDeclarationPanel.css';

interface AutoDeclarationPanelProps {
  isOpen: boolean;
  backendUrl: string;
  onClose: () => void;
}

interface ExtractedDoc {
  kind: string;
  text_sample?: string;
  amounts: number[];
  currencies: string[];
  incoterm?: string;
  invoice_number?: string;
  hs_codes: string[];
  origin_country?: string;
}

interface AutoDeclarationResult {
  extracted: Record<string, ExtractedDoc>;
  calculation_input: Record<string, unknown>;
  calculation_result: Record<string, unknown>;
  export_hint: Record<string, unknown>;
}

export function AutoDeclarationPanel({ isOpen, backendUrl, onClose }: AutoDeclarationPanelProps) {
  const [invoiceFile, setInvoiceFile] = useState<File | null>(null);
  const [transportFile, setTransportFile] = useState<File | null>(null);
  const [insuranceFile, setInsuranceFile] = useState<File | null>(null);
  const [hsOverride, setHsOverride] = useState<string>('');
  const [processing, setProcessing] = useState(false);
  const [result, setResult] = useState<AutoDeclarationResult | null>(null);
  const [error, setError] = useState<string | null>(null);

  const handleProcess = async () => {
    if (!invoiceFile) {
      setError('La facture est obligatoire');
      return;
    }

    setProcessing(true);
    setError(null);
    setResult(null);

    try {
      const formData = new FormData();
      formData.append('invoice', invoiceFile);
      if (transportFile) formData.append('transport', transportFile);
      if (insuranceFile) formData.append('insurance', insuranceFile);
      formData.append('destination_country', 'CM');
      if (hsOverride.trim()) {
        formData.append('hs_override', hsOverride.trim());
      }

      console.log('Sending request to:', `${backendUrl}/api/declaration/auto`);
      console.log('FormData entries:');
      for (const [key, value] of formData.entries()) {
        console.log(`  ${key}:`, value);
      }

      const response = await fetch(`${backendUrl}/api/declaration/auto`, {
        method: 'POST',
        body: formData,
      });

      console.log('Response status:', response.status);

      if (!response.ok) {
        const errorText = await response.text();
        console.error('Error response:', errorText);
        let errorData;
        try {
          errorData = JSON.parse(errorText);
        } catch {
          throw new Error(`HTTP ${response.status}: ${errorText}`);
        }
        throw new Error(errorData.detail || 'Erreur lors du traitement');
      }

      const data: AutoDeclarationResult = await response.json();
      setResult(data);
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Erreur inconnue';
      console.error('Processing error:', err);
      setError(message);
    } finally {
      setProcessing(false);
    }
  };

  const handleExport = async (format: 'pdf' | 'csv' | 'json' | 'xml_esad') => {
    if (!result?.export_hint) return;

    try {
      const exportPayload = {
        ...result.export_hint,
        format,
      };

      const response = await fetch(`${backendUrl}/api/export`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(exportPayload),
      });

      if (!response.ok) {
        throw new Error("Erreur lors de l'export");
      }

      // Download file
      const blob = await response.blob();
      const url = window.URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `declaration.${format === 'xml_esad' ? 'xml' : format}`;
      document.body.appendChild(a);
      a.click();
      window.URL.revokeObjectURL(url);
      document.body.removeChild(a);
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Erreur inconnue';
      setError(message);
    }
  };

  const handleReset = () => {
    setInvoiceFile(null);
    setTransportFile(null);
    setInsuranceFile(null);
    setResult(null);
    setError(null);
  };

  if (!isOpen) return null;

  return (
    <div className="auto-declaration-overlay" onClick={onClose}>
      <div className="auto-declaration-panel" onClick={e => e.stopPropagation()}>
        <div className="panel-header">
          <h2>📄 Déclaration Automatique</h2>
          <button onClick={onClose} className="btn-close" aria-label="Fermer">
            ✕
          </button>
        </div>

        <div className="panel-content">
          {!result ? (
            <div className="upload-section">
              <div className="upload-instructions">
                <p>
                  <strong>Facture obligatoire</strong> - Les documents de transport et assurance
                  sont facultatifs.
                </p>
                <p className="optional-hint">
                  Si vous ne chargez pas les documents optionnels, vous pourrez saisir les montants
                  manuellement lors de la finalisation de la déclaration.
                </p>
                <ul>
                  <li>
                    📋 <strong>Facture commerciale</strong> (obligatoire)
                  </li>
                  <li>🚚 Transport (facultatif - peut être saisi manuellement)</li>
                  <li>🛡️ Assurance (facultatif - peut être saisi manuellement)</li>
                </ul>
              </div>

              <div className="file-inputs">
                <div className="file-input-group">
                  <label htmlFor="invoice">
                    <strong>Facture commerciale *</strong>
                  </label>
                  <input
                    id="invoice"
                    type="file"
                    accept="image/*,application/pdf"
                    onChange={e => setInvoiceFile(e.target.files?.[0] || null)}
                  />
                  {invoiceFile && <span className="file-name">✓ {invoiceFile.name}</span>}
                </div>

                <div className="file-input-group">
                  <label htmlFor="transport">
                    <strong>Facture de transport</strong>
                  </label>
                  <input
                    id="transport"
                    type="file"
                    accept="image/*,application/pdf"
                    onChange={e => setTransportFile(e.target.files?.[0] || null)}
                  />
                  {transportFile && <span className="file-name">✓ {transportFile.name}</span>}
                </div>

                <div className="file-input-group">
                  <label htmlFor="insurance">
                    <strong>Attestation d&apos;assurance</strong>
                  </label>
                  <input
                    id="insurance"
                    type="file"
                    accept="image/*,application/pdf"
                    onChange={e => setInsuranceFile(e.target.files?.[0] || null)}
                  />
                  {insuranceFile && <span className="file-name">✓ {insuranceFile.name}</span>}
                </div>
              </div>

              <div className="manual-hs">
                <label htmlFor="hs_override">
                  <strong>Code HS (optionnel)</strong>
                </label>
                <input
                  id="hs_override"
                  type="text"
                  placeholder="ex: 610910"
                  value={hsOverride}
                  onChange={e => setHsOverride(e.target.value)}
                />
                <small>
                  Sera utilisé si la détection automatique échoue. 4 à 6 chiffres recommandés.
                </small>
              </div>

              {error && (
                <div className="error-message" role="alert" aria-live="assertive">
                  <div className="error-text">
                    <strong>❌ Erreur :</strong> {error}
                  </div>
                  <button
                    type="button"
                    className="btn-error-close"
                    aria-label="Fermer l’erreur"
                    onClick={() => setError(null)}
                  >
                    ✕
                  </button>
                </div>
              )}

              <div className="action-buttons">
                <button
                  onClick={handleProcess}
                  disabled={!invoiceFile || processing}
                  className="btn-primary"
                >
                  {processing ? '⏳ Traitement en cours...' : '🚀 Générer la déclaration'}
                </button>
              </div>
            </div>
          ) : (
            <div className="result-section">
              <div className="result-header">
                <h3>✅ Déclaration générée avec succès</h3>
                <button onClick={handleReset} className="btn-secondary">
                  🔄 Nouvelle déclaration
                </button>
              </div>

              <div className="result-tabs">
                <div className="result-tab">
                  <h4>📊 Données extraites</h4>
                  <div className="extracted-data">
                    {Object.entries(result.extracted).map(([key, doc]) => (
                      <div key={key} className="extracted-doc">
                        <strong>
                          {key === 'invoice'
                            ? '📋 Facture'
                            : key === 'transport'
                              ? '🚚 Transport'
                              : '🛡️ Assurance'}
                        </strong>
                        <ul>
                          {doc.invoice_number && <li>N° Facture: {doc.invoice_number}</li>}
                          {doc.incoterm && <li>Incoterm: {doc.incoterm}</li>}
                          {doc.origin_country && <li>Origine: {doc.origin_country}</li>}
                          {doc.hs_codes.length > 0 && <li>Codes HS: {doc.hs_codes.join(', ')}</li>}
                          {doc.amounts.length > 0 && (
                            <li>
                              Montants: {doc.amounts.join(', ')} {doc.currencies[0] || ''}
                            </li>
                          )}
                        </ul>
                      </div>
                    ))}
                    {!result.extracted.transport && (
                      <div className="extracted-doc optional-doc">
                        <strong>🚚 Transport</strong>
                        <ul>
                          <li>Non fourni - À saisir manuellement si nécessaire</li>
                        </ul>
                      </div>
                    )}
                    {!result.extracted.insurance && (
                      <div className="extracted-doc optional-doc">
                        <strong>🛡️ Assurance</strong>
                        <ul>
                          <li>Non fourni - À saisir manuellement si nécessaire</li>
                        </ul>
                      </div>
                    )}
                  </div>
                </div>

                <div className="result-tab">
                  <h4>💰 Calcul douanier</h4>
                  <div className="calculation-summary">
                    {result.calculation_result && (
                      <div className="calc-details">
                        <div className="calc-row">
                          <span>Valeur en douane (CIF):</span>
                          <strong>
                            {(
                              result.calculation_result as { taxable_base?: number }
                            ).taxable_base?.toLocaleString() || 'N/A'}{' '}
                            FCFA
                          </strong>
                        </div>
                        <div className="calc-row">
                          <span>Droits de douane (DD):</span>
                          <strong>
                            {(
                              result.calculation_result as {
                                tax_breakdown?: { customs_duty_amount?: number };
                              }
                            ).tax_breakdown?.customs_duty_amount?.toLocaleString() || 'N/A'}{' '}
                            FCFA
                          </strong>
                        </div>
                        <div className="calc-row">
                          <span>TVA:</span>
                          <strong>
                            {(
                              result.calculation_result as {
                                tax_breakdown?: { vat_amount?: number };
                              }
                            ).tax_breakdown?.vat_amount?.toLocaleString() || 'N/A'}{' '}
                            FCFA
                          </strong>
                        </div>
                        <div className="calc-row total">
                          <span>Total taxes:</span>
                          <strong>
                            {(
                              result.calculation_result as {
                                tax_breakdown?: { total_taxes?: number };
                              }
                            ).tax_breakdown?.total_taxes?.toLocaleString() || 'N/A'}{' '}
                            FCFA
                          </strong>
                        </div>
                      </div>
                    )}
                  </div>
                </div>
              </div>

              <div className="export-section">
                <h4>📤 Déclaration prête à exporter</h4>
                <p className="export-ready-message">
                  ✅ Votre déclaration est complète et peut être exportée. Les montants de transport
                  et assurance peuvent être ajustés manuellement dans le document exporté si
                  nécessaire.
                </p>
                <div className="export-buttons">
                  <button onClick={() => handleExport('pdf')} className="btn-export">
                    📄 PDF
                  </button>
                  <button onClick={() => handleExport('csv')} className="btn-export">
                    📊 CSV
                  </button>
                  <button onClick={() => handleExport('json')} className="btn-export">
                    💾 JSON
                  </button>
                  <button onClick={() => handleExport('xml_esad')} className="btn-export">
                    📋 XML eSAD
                  </button>
                </div>
              </div>

              {error && (
                <div className="error-message">
                  <strong>❌ Erreur :</strong> {error}
                </div>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
