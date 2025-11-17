import { useState, useEffect, useRef } from 'react';
import './ProjectNameDialog.css';

interface ProjectNameDialogProps {
  isOpen: boolean;
  onConfirm: (name: string) => void;
  onCancel: () => void;
}

export function ProjectNameDialog({ isOpen, onConfirm, onCancel }: ProjectNameDialogProps) {
  const [name, setName] = useState('');
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (isOpen) {
      // Delay focus to ensure the element is fully rendered
      setTimeout(() => {
        if (inputRef.current) {
          inputRef.current.focus();
          inputRef.current.select();
        }
      }, 100);
      setName(''); // Reset on open
    }
  }, [isOpen]);

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (name.trim()) {
      onConfirm(name.trim());
      setName('');
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Escape') {
      onCancel();
    }
  };

  if (!isOpen) return null;

  return (
    <div className="dialog-overlay" onClick={onCancel}>
      <div className="dialog-content" onClick={e => e.stopPropagation()}>
        <h2>Nouveau projet</h2>
        <form onSubmit={handleSubmit}>
          <input
            ref={inputRef}
            type="text"
            value={name}
            onChange={e => setName(e.target.value)}
            onKeyDown={handleKeyDown}
            onMouseDown={e => e.stopPropagation()}
            onClick={e => e.stopPropagation()}
            placeholder="Nom du projet..."
            className="dialog-input"
            maxLength={100}
            autoFocus
            tabIndex={0}
          />
          <div className="dialog-actions">
            <button type="button" onClick={onCancel} className="btn-cancel">
              Annuler
            </button>
            <button type="submit" disabled={!name.trim()} className="btn-confirm">
              Créer
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
