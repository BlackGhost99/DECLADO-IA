import { useState } from 'react';
import type { InvoiceDocument } from '../types';
import './DocumentList.css';

interface DocumentListProps {
  documents: InvoiceDocument[];
  selectedDocumentId: string | null;
  onSelectDocument: (docId: string) => void;
  onDeleteDocument: (docId: string) => void;
  onAddFiles: () => void;
}

const statusLabels: Record<InvoiceDocument['status'], string> = {
  pending: '⏳ En attente',
  processing: '⚙️ Traitement...',
  completed: '✅ Terminé',
  error: '❌ Erreur',
};

const statusColors: Record<InvoiceDocument['status'], string> = {
  pending: '#ffa726',
  processing: '#42a5f5',
  completed: '#66bb6a',
  error: '#ef5350',
};

export function DocumentList({
  documents,
  selectedDocumentId,
  onSelectDocument,
  onDeleteDocument,
  onAddFiles,
}: DocumentListProps) {
  const [deletingId, setDeletingId] = useState<string | null>(null);
  const [explodingId, setExplodingId] = useState<string | null>(null);

  const handleDelete = (e: React.MouseEvent, docId: string, filename: string) => {
    e.stopPropagation();
    
    // Animation de shake pour la confirmation
    const button = e.currentTarget as HTMLElement;
    button.style.animation = 'shake 0.5s ease';
    
    setTimeout(() => {
      if (confirm(`Supprimer "${filename}" ?`)) {
        // Animation d'explosion
        setExplodingId(docId);
        
        setTimeout(() => {
          setDeletingId(docId);
          
          // Suppression après animation
          setTimeout(() => {
            onDeleteDocument(docId);
            setDeletingId(null);
            setExplodingId(null);
          }, 400);
        }, 100);
      } else {
        button.style.animation = '';
      }
    }, 500);
  };

  return (
    <div className="document-list">
      <div className="document-list-header">
        <h3>Documents ({documents.length})</h3>
        <button onClick={onAddFiles} className="btn-add-files" title="Ajouter des fichiers">
          ➕ Ajouter
        </button>
      </div>

      {documents.length === 0 ? (
        <div className="empty-documents">
          <p>Aucun document.</p>
          <button onClick={onAddFiles} className="btn-add-files-large">
            ➕ Ajouter des fichiers
          </button>
        </div>
      ) : (
        <ul className="documents">
          {documents.map(doc => (
            <li
              key={doc.id}
              className={`document-item ${selectedDocumentId === doc.id ? 'selected' : ''} ${deletingId === doc.id ? 'deleting' : ''} ${explodingId === doc.id ? 'exploding' : ''}`}
              onClick={() => onSelectDocument(doc.id)}
            >
              <div className="document-info">
                <strong>{doc.filename}</strong>
                <span className="document-status" style={{ color: statusColors[doc.status] }}>
                  {statusLabels[doc.status]}
                </span>
                {doc.error && <span className="document-error">{doc.error}</span>}
              </div>
              <button
                onClick={e => handleDelete(e, doc.id, doc.filename)}
                className="btn-delete-doc"
                aria-label="Supprimer"
                title="Supprimer"
              >
                🗑️
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
