import { useState } from 'react';
import type { Project } from '../types';
import './Sidebar.css';

interface SidebarProps {
  projects: Project[];
  selectedProjectId: string | null;
  onSelectProject: (projectId: string) => void;
  onNewProject: () => void;
  onDeleteProject: (projectId: string) => void;
}

export function Sidebar({
  projects,
  selectedProjectId,
  onSelectProject,
  onNewProject,
  onDeleteProject,
}: SidebarProps) {
  const [deletingId, setDeletingId] = useState<string | null>(null);

  const handleDelete = (e: React.MouseEvent, projectId: string, projectName: string) => {
    e.stopPropagation();
    
    // Animation de shake pour la confirmation
    const button = e.currentTarget as HTMLElement;
    button.style.animation = 'shake 0.5s ease';
    
    setTimeout(() => {
      if (confirm(`Supprimer le projet "${projectName}" et tous ses documents ?`)) {
        setDeletingId(projectId);
        
        // Animation de suppression après un court délai
        setTimeout(() => {
          onDeleteProject(projectId);
          setDeletingId(null);
        }, 500);
      } else {
        button.style.animation = '';
      }
    }, 500);
  };

  return (
    <aside className="sidebar">
      <div className="sidebar-header">
        <h2>Projets</h2>
      </div>

      <>
          <button onClick={onNewProject} className="btn-new-project">
            ➕ Nouveau projet
          </button>

          <ul className="project-list">
            {projects.map(project => (
              <li
                key={project.id}
                className={`project-item ${selectedProjectId === project.id ? 'selected' : ''} ${deletingId === project.id ? 'deleting' : ''}`}
                onClick={() => onSelectProject(project.id)}
              >
                <div className="project-info">
                  <strong>{project.name}</strong>
                  <span className="project-doc-count">{project.documents.length} doc(s)</span>
                </div>
                <button
                  onClick={e => handleDelete(e, project.id, project.name)}
                  className="btn-delete-project"
                  aria-label="Supprimer"
                  title="Supprimer"
                >
                  🗑️
                </button>
              </li>
            ))}
          </ul>

          {projects.length === 0 && <p className="empty-state">Aucun projet. Créez-en un!</p>}
      </>
    </aside>
  );
}
