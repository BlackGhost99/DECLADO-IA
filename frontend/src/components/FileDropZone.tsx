import { useFileImport } from '../hooks/useFileImport';
import './FileDropZone.css';

interface FileDropZoneProps {
  onFilesSelected: (files: File[]) => void;
  accept?: string;
  multiple?: boolean;
}

export function FileDropZone({
  onFilesSelected,
  accept = '.pdf,.png,.jpg,.jpeg,.tif,.tiff',
  multiple = true,
}: FileDropZoneProps) {
  const { inputProps, isDragging, handleDragOver, handleDragLeave, handleDrop, openFilePicker } =
    useFileImport({ onFilesSelected, accept, multiple });

  return (
    <div
      className={`file-drop-zone ${isDragging ? 'dragging' : ''}`}
      onDragOver={handleDragOver}
      onDragLeave={handleDragLeave}
      onDrop={handleDrop}
      onClick={openFilePicker}
      role="button"
      tabIndex={0}
      onKeyDown={e => {
        if (e.key === 'Enter' || e.key === ' ') {
          e.preventDefault();
          openFilePicker();
        }
      }}
      aria-label="Zone de dépôt de fichiers"
    >
      <input {...inputProps} />
      <div className="drop-zone-content">
        <div className="drop-zone-icon">📄</div>
        <p className="drop-zone-text">
          {isDragging ? 'Déposez les fichiers ici' : 'Cliquez ou glissez-déposez des fichiers'}
        </p>
        <p className="drop-zone-hint">Formats acceptés: PDF, PNG, JPG, TIFF</p>
      </div>
    </div>
  );
}
