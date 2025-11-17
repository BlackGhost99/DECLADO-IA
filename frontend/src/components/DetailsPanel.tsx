import { useState } from 'react';
import type { InvoiceDocument, ExportMeta } from '../types';
import { FilePreview } from './FilePreview';
import { useSettings } from '../contexts/SettingsContext';
import './DetailsPanel.css';

interface DetailsPanelProps {
  document: InvoiceDocument | null;
  onExport: (format: 'pdf' | 'xml_esad' | 'csv' | 'json', meta?: ExportMeta) => void;
}

export function DetailsPanel({ document, onExport }: DetailsPanelProps) {
  const { settings, formatCurrency } = useSettings();
  const [activeTab, setActiveTab] = useState<'preview' | 'ocr' | 'hs' | 'customs' | 'export'>('preview');
  const [exportMeta, setExportMeta] = useState<ExportMeta>({
    declaration_number: '',
    declarant_name: 'DECLADO-IA',
    exporter_name: '',
    importer_name: '',
    customs_office: 'CM-DLA',
    country: 'CM',
    declaration_date: new Date().toISOString().split('T')[0],
  });

  if (!document) {
    return (
      <div className="details-panel">
        <div className="empty-selection">
          <p>📋 Sélectionnez un document pour voir les détails</p>
        </div>
      </div>
    );
  }

  return (
    <div className="details-panel">
      <div className="details-header">
        <h3>{document.filename}</h3>
        <span className="document-id">ID: {document.id}</span>
      </div>

      <div className="tabs">
        {settings.showPreview && (
          <button
            className={`tab ${activeTab === 'preview' ? 'active' : ''}`}
            onClick={() => setActiveTab('preview')}
          >
            👁️ Aperçu
          </button>
        )}
        <button
          className={`tab ${activeTab === 'ocr' ? 'active' : ''}`}
          onClick={() => setActiveTab('ocr')}
        >
          📝 OCR
        </button>
        <button
          className={`tab ${activeTab === 'hs' ? 'active' : ''}`}
          onClick={() => setActiveTab('hs')}
        >
          🏷️ Classification HS
        </button>
        <button
          className={`tab ${activeTab === 'customs' ? 'active' : ''}`}
          onClick={() => setActiveTab('customs')}
        >
          💰 Calcul douanier
        </button>
        <button
          className={`tab ${activeTab === 'export' ? 'active' : ''}`}
          onClick={() => setActiveTab('export')}
        >
          📤 Export
        </button>
      </div>

      <div className="tab-content">
        {activeTab === 'preview' && settings.showPreview && (
          <div className="preview-content">
            <FilePreview document={document} size={settings.previewSize} />
          </div>
        )}

        {activeTab === 'ocr' && (
          <div className="ocr-content">
            <h4>Résultat OCR</h4>
            {document.ocrResult ? (
              <>
                <p>
                  <strong>Pages:</strong> {document.ocrResult.num_pages}
                </p>
                <p>
                  <strong>Source:</strong> {document.ocrResult.source}
                </p>
                {document.ocrResult.cer !== undefined && (
                  <p>
                    <strong>CER:</strong> {(document.ocrResult.cer * 100).toFixed(2)}%
                  </p>
                )}
                {document.ocrResult.warnings && document.ocrResult.warnings.length > 0 && (
                  <div className="ocr-warnings">
                    <h5>⚠️ Avertissements:</h5>
                    <ul>
                      {document.ocrResult.warnings.map((w, i) => (
                        <li key={i}>{w}</li>
                      ))}
                    </ul>
                  </div>
                )}
                {document.ocrResult.pages && document.ocrResult.pages.length > 0 && (
                  <div className="ocr-preview">
                    <h5>Aperçu du texte (page 1)</h5>
                    <pre
                      style={{
                        maxHeight: 200,
                        overflow: 'auto',
                        background: '#f7f7f9',
                        border: '1px solid #eee',
                        padding: '8px',
                        whiteSpace: 'pre-wrap',
                      }}
                    >
                      {document.ocrResult.pages[0].text?.slice(0, 1000) || '—'}
                    </pre>
                  </div>
                )}
                <div className="normalized-fields">
                  <h5>Champs extraits:</h5>
                  {document.ocrResult.normalized.dates?.length > 0 && (
                    <p>
                      <strong>Dates:</strong> {document.ocrResult.normalized.dates.join(', ')}
                    </p>
                  )}
                  {document.ocrResult.normalized.amounts?.length > 0 && (
                    <p>
                      <strong>Montants:</strong> {document.ocrResult.normalized.amounts.join(', ')}
                    </p>
                  )}
                  {document.ocrResult.normalized.currencies?.length > 0 && (
                    <p>
                      <strong>Devises:</strong>{' '}
                      {document.ocrResult.normalized.currencies.join(', ')}
                    </p>
                  )}
                </div>
              </>
            ) : (
              <p className="no-data">Aucune donnée OCR disponible</p>
            )}
          </div>
        )}

        {activeTab === 'hs' && (
          <div className="hs-content">
            <h4>Classifications HS suggérées</h4>
            {document.hsClassifications && document.hsClassifications.length > 0 ? (
              <ul className="hs-list">
                {document.hsClassifications.map((hs, idx) => {
                  const conf = Number(hs.confidence);
                  const hasConf = Number.isFinite(conf);
                  return (
                    <li key={idx} className="hs-item">
                      <div className="hs-code">{hs.code}</div>
                      <div className="hs-description">{hs.description || ''}</div>
                      <div className="hs-confidence">
                        Confiance: {hasConf ? `${(conf * 100).toFixed(1)}%` : '—'}
                      </div>
                    </li>
                  );
                })}
              </ul>
            ) : (
              <p className="no-data">Aucune classification HS disponible</p>
            )}
          </div>
        )}

        {activeTab === 'customs' && (
          <div className="customs-content">
            <h4>Calcul douanier</h4>
            {document.customsCalculation ? (
              <div className="customs-result">
                <div className="customs-section">
                  <h5>Conversion Incoterms</h5>
                  <p>
                    <strong>Incoterm:</strong>{' '}
                    {document.customsCalculation.incoterms_conversion.original_incoterm}
                  </p>
                  <p>
                    <strong>Valeur CIF:</strong>{' '}
                    {formatCurrency(parseInt(document.customsCalculation.incoterms_conversion.cif_value))}
                  </p>
                </div>

                <div className="customs-section">
                  <h5>Taxes</h5>
                  <p>
                    <strong>
                      Droits de douane (
                      {document.customsCalculation.tax_breakdown.customs_duty_rate}%):
                    </strong>{' '}
                    {formatCurrency(parseInt(document.customsCalculation.tax_breakdown.customs_duty_amount))}
                  </p>
                  <p>
                    <strong>TVA ({document.customsCalculation.tax_breakdown.vat_rate}%):</strong>{' '}
                    {formatCurrency(parseInt(document.customsCalculation.tax_breakdown.vat_amount))}
                  </p>
                  <p className="total">
                    <strong>TOTAL:</strong>{' '}
                    {formatCurrency(parseInt(document.customsCalculation.tax_breakdown.total_amount))}
                  </p>
                </div>

                <div className="customs-section">
                  <h5>
                    Documents requis ({document.customsCalculation.required_documents.length})
                  </h5>
                  <ul className="doc-list">
                    {document.customsCalculation.required_documents.slice(0, 5).map((doc, idx) => (
                      <li key={idx}>{doc}</li>
                    ))}
                    {document.customsCalculation.required_documents.length > 5 && (
                      <li>
                        ... et {document.customsCalculation.required_documents.length - 5} autres
                      </li>
                    )}
                  </ul>
                </div>
              </div>
            ) : (
              <p className="no-data">Aucun calcul douanier disponible</p>
            )}
          </div>
        )}

        {activeTab === 'export' && (
          <div className="export-content">
            <h4>Export du dossier</h4>

            <div className="export-meta-form">
              <h5>Métadonnées eSAD (optionnel)</h5>
              <div className="form-grid">
                <div className="form-field">
                  <label>N° déclaration</label>
                  <input
                    type="text"
                    value={exportMeta.declaration_number || ''}
                    onChange={e =>
                      setExportMeta({ ...exportMeta, declaration_number: e.target.value })
                    }
                    placeholder="SAD-2025-0001"
                  />
                </div>
                <div className="form-field">
                  <label>Déclarant</label>
                  <input
                    type="text"
                    value={exportMeta.declarant_name || ''}
                    onChange={e => setExportMeta({ ...exportMeta, declarant_name: e.target.value })}
                  />
                </div>
                <div className="form-field">
                  <label>Exportateur</label>
                  <input
                    type="text"
                    value={exportMeta.exporter_name || ''}
                    onChange={e => setExportMeta({ ...exportMeta, exporter_name: e.target.value })}
                  />
                </div>
                <div className="form-field">
                  <label>Importateur</label>
                  <input
                    type="text"
                    value={exportMeta.importer_name || ''}
                    onChange={e => setExportMeta({ ...exportMeta, importer_name: e.target.value })}
                  />
                </div>
                <div className="form-field">
                  <label>Bureau de douane</label>
                  <input
                    type="text"
                    value={exportMeta.customs_office || ''}
                    onChange={e => setExportMeta({ ...exportMeta, customs_office: e.target.value })}
                  />
                </div>
                <div className="form-field">
                  <label>Date</label>
                  <input
                    type="date"
                    value={exportMeta.declaration_date || ''}
                    onChange={e =>
                      setExportMeta({ ...exportMeta, declaration_date: e.target.value })
                    }
                  />
                </div>
              </div>
            </div>

            <div className="export-buttons">
              <button
                onClick={() => onExport('pdf', exportMeta)}
                className="btn-export btn-export-pdf"
                disabled={!document.customsCalculation}
              >
                📄 Export PDF
              </button>
              <button
                onClick={() => onExport('xml_esad', exportMeta)}
                className="btn-export btn-export-xml"
                disabled={!document.customsCalculation}
              >
                📋 Export XML eSAD
              </button>
              <button
                onClick={() => onExport('csv', exportMeta)}
                className="btn-export btn-export-csv"
                disabled={!document.customsCalculation}
              >
                📊 Export CSV
              </button>
              <button
                onClick={() => onExport('json', exportMeta)}
                className="btn-export btn-export-json"
                disabled={!document.customsCalculation}
              >
                🔧 Export JSON
              </button>
            </div>

            {!document.customsCalculation && (
              <p className="export-hint">
                ⚠️ Effectuez d&apos;abord un calcul douanier pour exporter
              </p>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
