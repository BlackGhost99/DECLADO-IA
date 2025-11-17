import { useState, useCallback } from 'react';
import type { InvoiceDocument, Project } from '../types';

const STORAGE_KEY = 'declado_projects';

export function useLocalStorage() {
  const [projects, setProjects] = useState<Project[]>(() => {
    try {
      const stored = localStorage.getItem(STORAGE_KEY);
      return stored ? JSON.parse(stored) : [];
    } catch {
      return [];
    }
  });

  const addProject = useCallback((project: Omit<Project, 'id' | 'createdAt' | 'documents'>) => {
    const newProject: Project = {
      id: `proj_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`,
      createdAt: new Date(),
      documents: [],
      ...project,
    };
    setProjects(prevProjects => {
      const updated = [...prevProjects, newProject];
      try {
        localStorage.setItem(STORAGE_KEY, JSON.stringify(updated));
      } catch (err) {
        console.error('Failed to save to localStorage:', err);
      }
      return updated;
    });
    return newProject;
  }, []);

  const updateProject = useCallback((id: string, updates: Partial<Project>) => {
    setProjects(prevProjects => {
      const updated = prevProjects.map(p => (p.id === id ? { ...p, ...updates } : p));
      try {
        localStorage.setItem(STORAGE_KEY, JSON.stringify(updated));
      } catch (err) {
        console.error('Failed to save to localStorage:', err);
      }
      return updated;
    });
  }, []);

  const deleteProject = useCallback((id: string) => {
    setProjects(prevProjects => {
      const updated = prevProjects.filter(p => p.id !== id);
      try {
        localStorage.setItem(STORAGE_KEY, JSON.stringify(updated));
      } catch (err) {
        console.error('Failed to save to localStorage:', err);
      }
      return updated;
    });
  }, []);

  const addDocument = useCallback(
    (projectId: string, document: Omit<InvoiceDocument, 'id' | 'uploadedAt' | 'status'>) => {
      const newDoc: InvoiceDocument = {
        id: `doc_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`,
        uploadedAt: new Date(),
        status: 'pending',
        ...document,
      };

      setProjects(prevProjects => {
        const updated = prevProjects.map(p =>
          p.id === projectId ? { ...p, documents: [...p.documents, newDoc] } : p
        );
        try {
          localStorage.setItem(STORAGE_KEY, JSON.stringify(updated));
        } catch (err) {
          console.error('Failed to save to localStorage:', err);
        }
        return updated;
      });
      return newDoc;
    },
    []
  );

  const updateDocument = useCallback(
    (projectId: string, docId: string, updates: Partial<InvoiceDocument>) => {
      setProjects(prevProjects => {
        const updated = prevProjects.map(p =>
          p.id === projectId
            ? {
                ...p,
                documents: p.documents.map(d => (d.id === docId ? { ...d, ...updates } : d)),
              }
            : p
        );
        try {
          localStorage.setItem(STORAGE_KEY, JSON.stringify(updated));
        } catch (err) {
          console.error('Failed to save to localStorage:', err);
        }
        return updated;
      });
    },
    []
  );

  const deleteDocument = useCallback((projectId: string, docId: string) => {
    setProjects(prevProjects => {
      const updated = prevProjects.map(p =>
        p.id === projectId ? { ...p, documents: p.documents.filter(d => d.id !== docId) } : p
      );
      try {
        localStorage.setItem(STORAGE_KEY, JSON.stringify(updated));
      } catch (err) {
        console.error('Failed to save to localStorage:', err);
      }
      return updated;
    });
  }, []);

  return {
    projects,
    addProject,
    updateProject,
    deleteProject,
    addDocument,
    updateDocument,
    deleteDocument,
  };
}
