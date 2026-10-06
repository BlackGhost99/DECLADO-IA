import { useState, useEffect } from 'react';
import type { InvoiceDocument } from '../types';
import './FilePreview.css';

interface FilePreviewProps {
  document: InvoiceDocument;
  size?: 'small' | 'medium' | 'large';
}

export function FilePreview({ document, size = 'medium' }: FilePreviewProps) {
  const [previewUrl, setPreviewUrl] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    // Si le document a déjà une URL de prévisualisation (depuis OCR)
    if (document.ocrResult?.source) {
      const isImage = /\.(png|jpg|jpeg|gif|webp)$/i.test(document.filename);
      if (isImage) {
        // En production, charger depuis le backend
        // Pour l'instant, créer une URL blob si possible
        setPreviewUrl(document.ocrResult.source);
        setLoading(false);
        return;
      }
    }

    // Pour les PDFs et autres fichiers, on affiche les infos disponibles
    setLoading(false);
    if (!document.ocrResult) {
      setError("Fichier non traité - effectuez d'abord l'OCR");
    }
  }, [document]);

  const isImage = /\.(png|jpg|jpeg|gif|webp)$/i.test(document.filename);
  const isPdf = /\.pdf$/i.test(document.filename);

  if (loading) {
    return (
      <div className={`file-preview file-preview-${size} loading`}>
        <div className="preview-spinner"></div>
        <p>Chargement de la prévisualisation...</p>
      </div>
    );
  }

  if (error && !previewUrl) {
    return (
      <div className={`file-preview file-preview-${size} error`}>
        <div className="preview-icon">📄</div>
        <p>{error}</p>
        <p className="preview-filename">{document.filename}</p>
      </div>
    );
  }

  return (
    <div className={`file-preview file-preview-${size}`}>
      {isImage && previewUrl ? (
        <div className="preview-image-container">
          <img src={previewUrl} alt={document.filename} className="preview-image" />
          <div className="preview-overlay">
            <span className="preview-filename">{document.filename}</span>
          </div>
        </div>
      ) : isPdf ? (
        <div className="preview-pdf-container">
          <div className="preview-pdf-icon">📕</div>
          <p className="preview-filename">{document.filename}</p>
          {document.ocrResult && (
            <div className="preview-pdf-info">
              <span>{document.ocrResult.num_pages} page(s)</span>
              {document.ocrResult.cer !== undefined && (
                <span>CER: {(document.ocrResult.cer * 100).toFixed(1)}%</span>
              )}
            </div>
          )}
          <button className="btn-view-pdf">👁️ Voir le PDF</button>
        </div>
      ) : (
        <div className="preview-generic">
          <div className="preview-icon">📄</div>
          <p className="preview-filename">{document.filename}</p>
          <p className="preview-type">{document.filename.split('.').pop()?.toUpperCase()}</p>
        </div>
      )}

      {document.ocrResult && document.ocrResult.pages && document.ocrResult.pages.length > 0 && (
        <div className="preview-ocr-snippet">
          <h4>Extrait OCR</h4>
          <p>{document.ocrResult.pages[0].text?.substring(0, 200)}...</p>
        </div>
      )}
    </div>
  );
}
