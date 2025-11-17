import { useState, useEffect, useCallback } from 'react';
import './App.css';
import MainLayout from './layouts/MainLayout';
import { SettingsProvider } from './contexts/SettingsContext';

declare global {
  interface Window {
    electronAPI?: {
      getBackendUrl: () => Promise<string>;
      checkBackendStatus: () => Promise<{ status: string; data?: unknown; message?: string }>;
      platform: string;
      versions: {
        node: string;
        chrome: string;
        electron: string;
      };
    };
  }
}

function App() {
  const [backendUrl, setBackendUrl] = useState<string>('');
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);

  const checkHealth = useCallback(async () => {
    if (!backendUrl) return;

    try {
      const response = await fetch(`${backendUrl}/api/health`);
      await response.json();
      setError(null);
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Unknown error';
      setError(`Impossible de joindre le backend: ${message}`);
    }
  }, [backendUrl]);

  useEffect(() => {
    const initializeApp = async () => {
      try {
        if (window.electronAPI) {
          const url = await window.electronAPI.getBackendUrl();
          setBackendUrl(url);
        } else {
          setBackendUrl('http://127.0.0.1:8000');
        }
      } catch (err) {
        const message = err instanceof Error ? err.message : 'Unknown error';
        setError(`Erreur d''initialisation: ${message}`);
      } finally {
        setLoading(false);
      }
    };

    initializeApp();
  }, []);

  useEffect(() => {
    if (backendUrl) {
      checkHealth();
    }
  }, [backendUrl, checkHealth]);

  if (loading) {
    return (
      <div className="app">
        <header className="app-header">
          <h1>DECLADO-IA</h1>
          <p>Système d&apos;Extraction de Factures & Calculs Douaniers CEMAC</p>
        </header>
        <main className="app-main">
          <div className="app-loading">
            <div className="spinner"></div>
            <p>Chargement...</p>
          </div>
        </main>
      </div>
    );
  }

  if (error) {
    return (
      <div className="app">
        <header className="app-header">
          <h1>DECLADO-IA</h1>
          <p>Système d&apos;Extraction de Factures & Calculs Douaniers CEMAC</p>
        </header>
        <main className="app-main">
          <div className="error-message">
            <h2>❌ Erreur de connexion</h2>
            <p>{error}</p>
          </div>
        </main>
      </div>
    );
  }

  return (
    <SettingsProvider backendUrl={backendUrl}>
      <MainLayout backendUrl={backendUrl} />
    </SettingsProvider>
  );
}

export default App;
