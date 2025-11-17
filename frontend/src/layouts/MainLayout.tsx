import { useState, useEffect } from 'react';
import { Sidebar } from '../components/Sidebar';
import { DocumentList } from '../components/DocumentList';
import { FileDropZone } from '../components/FileDropZone';
import { DetailsPanel } from '../components/DetailsPanel';
import { ProjectNameDialog } from '../components/ProjectNameDialog';
import { SettingsPanel } from '../components/SettingsPanel';
import { ToolsPanel } from '../components/ToolsPanel';
import { AutoDeclarationPanel } from '../components/AutoDeclarationPanel';
import { useLocalStorage } from '../hooks/useLocalStorage';
import type { ExportMeta, CustomsInput } from '../types';
import './MainLayout.css';

interface MainLayoutProps {
  backendUrl: string;
}

export function MainLayout({ backendUrl }: MainLayoutProps) {
  const { projects, addProject, deleteProject, addDocument, updateDocument, deleteDocument } =
    useLocalStorage();

  const [selectedProjectId, setSelectedProjectId] = useState<string | null>(null);
  const [selectedDocumentId, setSelectedDocumentId] = useState<string | null>(null);
  const [showFileDropZone, setShowFileDropZone] = useState(false);
  const [showProjectDialog, setShowProjectDialog] = useState(false);
  const [showSettings, setShowSettings] = useState(false);
  const [showTools, setShowTools] = useState(false);
  const [showAutoDeclaration, setShowAutoDeclaration] = useState(false);
  const [processing, setProcessing] = useState(false);

  // Auto-select first project if none selected
  useEffect(() => {
    if (!selectedProjectId && projects.length > 0) {
      setSelectedProjectId(projects[0].id);
    }
  }, [projects, selectedProjectId]);

  const selectedProject = projects.find(p => p.id === selectedProjectId);
  const selectedDocument = selectedProject?.documents.find(d => d.id === selectedDocumentId);

  const handleNewProject = () => {
    setShowProjectDialog(true);
  };

  const handleProjectNameConfirm = (name: string) => {
    const project = addProject({ name });
    setSelectedProjectId(project.id);
    setShowProjectDialog(false);
  };

  const handleProjectNameCancel = () => {
    setShowProjectDialog(false);
  };

  const handleFilesSelected = async (files: File[]) => {
    if (!selectedProjectId) {
      alert("Créez d'abord un projet");
      return;
    }

    console.log('=== DEBUG START ===');
    console.log('Backend URL:', backendUrl);
    console.log('Files:', files);
    console.log('Selected Project ID:', selectedProjectId);

    setShowFileDropZone(false);
    setProcessing(true);

    for (const file of files) {
      console.log('Processing file:', file.name, 'Type:', file.type, 'Size:', file.size);

      let doc;
      try {
        doc = addDocument(selectedProjectId, { filename: file.name });
        console.log('Document created with ID:', doc.id);
      } catch (addErr) {
        console.error('Error creating document:', addErr);
        continue;
      }

      // Process OCR
      try {
        console.log('Setting status to processing for doc:', doc.id);
        updateDocument(selectedProjectId, doc.id, { status: 'processing' });

        const formData = new FormData();
        formData.append('file', file);
        formData.append('lang', 'eng+fra');

        console.log('Sending OCR request to:', `${backendUrl}/api/ocr/process`);
        const ocrRes = await fetch(`${backendUrl}/api/ocr/process`, {
          method: 'POST',
          body: formData,
        });

        if (!ocrRes.ok) {
          const errorText = await ocrRes.text();
          console.error('OCR Error:', errorText);
          throw new Error(`OCR failed: ${errorText}`);
        }

        const ocrResult = await ocrRes.json();
        console.log('OCR Result:', ocrResult);
        updateDocument(selectedProjectId, doc.id, { ocrResult });

        // Auto HS classification if description found
        const fullText = ocrResult.pages?.map((p: { text: string }) => p.text).join(' ') || '';
        const desc = ocrResult.normalized?.vendor || fullText.substring(0, 200);
        console.log('Description extracted:', desc);

        if (desc && desc.trim()) {
          const hsRes = await fetch(`${backendUrl}/api/hs/suggest`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ text: desc, k: 3 }),
          });

          if (hsRes.ok) {
            const hsData = await hsRes.json();
            // Normalize backend suggestions (code, score, keywords[]) to UI model
            const hsClassifications = (hsData?.suggestions || []).map(
              (s: { code: string; score?: number; keywords?: string[] }) => ({
                code: s.code,
                description: (s.keywords && s.keywords.join(', ')) || '',
                confidence: typeof s.score === 'number' ? s.score : 0,
              })
            );
            updateDocument(selectedProjectId, doc.id, { hsClassifications });
          }
        }

        // Auto customs calculation with extracted data
        const amounts = ocrResult.normalized?.amounts || [];
        const currencies = ocrResult.normalized?.currencies || [];

        if (amounts.length > 0) {
          const customsInput: CustomsInput = {
            invoice_number: `AUTO-${doc.id}`,
            hs_code: '6109', // Default, user can change
            description: desc?.substring(0, 100) || 'Auto-imported',
            quantity: 1,
            unit_price: amounts[0],
            currency: currencies[0] || 'USD',
            incoterm: 'CIF',
            origin_country: 'CN',
            destination_country: 'CM',
          };

          const customsRes = await fetch(`${backendUrl}/api/customs/calculate`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
              invoice_number: customsInput.invoice_number,
              hs_code: customsInput.hs_code,
              description: customsInput.description,
              quantity: String(customsInput.quantity),
              unit_price: String(customsInput.unit_price),
              currency: customsInput.currency,
              incoterm: customsInput.incoterm,
              origin_country: customsInput.origin_country,
              destination_country: customsInput.destination_country,
            }),
          });

          if (customsRes.ok) {
            const customsCalculation = await customsRes.json();
            updateDocument(selectedProjectId, doc.id, { customsCalculation });
          }
        }

        updateDocument(selectedProjectId, doc.id, { status: 'completed' });
      } catch (err) {
        const message = err instanceof Error ? err.message : 'Unknown error';
        updateDocument(selectedProjectId, doc.id, {
          status: 'error',
          error: message,
        });
      }
    }

    setProcessing(false);
  };

  const handleExport = async (format: 'pdf' | 'xml_esad' | 'csv' | 'json', meta?: ExportMeta) => {
    if (!selectedDocument?.customsCalculation) return;

    try {
      const response = await fetch(`${backendUrl}/api/export`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          format,
          calculation: selectedDocument.customsCalculation.input,
          meta,
        }),
      });

      if (!response.ok) throw new Error('Export failed');

      const blob = await response.blob();
      const url = window.URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `export_${selectedDocument.id}.${format === 'xml_esad' ? 'xml' : format}`;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      window.URL.revokeObjectURL(url);
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Unknown error';
      alert(`Erreur d'export: ${message}`);
    }
  };

  return (
    <div className="main-layout">
      <ProjectNameDialog
        isOpen={showProjectDialog}
        onConfirm={handleProjectNameConfirm}
        onCancel={handleProjectNameCancel}
      />

      <SettingsPanel isOpen={showSettings} onClose={() => setShowSettings(false)} />
      <ToolsPanel isOpen={showTools} onClose={() => setShowTools(false)} />
      <AutoDeclarationPanel
        isOpen={showAutoDeclaration}
        onClose={() => setShowAutoDeclaration(false)}
        backendUrl={backendUrl}
      />

      <div className="fab-buttons">
        <button
          onClick={() => setShowAutoDeclaration(true)}
          className="btn-auto-declaration-fab"
          aria-label="Déclaration automatique"
          title="Déclaration automatique (3 documents)"
        >
          🚀
        </button>
        <button
          onClick={() => setShowTools(true)}
          className="btn-tools-fab"
          aria-label="Outils"
          title="Outils"
        >
          🛠️
        </button>
        <button
          onClick={() => setShowSettings(true)}
          className="btn-settings-fab"
          aria-label="Paramètres"
          title="Paramètres"
        >
          ⚙️
        </button>
      </div>

      <Sidebar
        projects={projects}
        selectedProjectId={selectedProjectId}
        onSelectProject={setSelectedProjectId}
        onNewProject={handleNewProject}
        onDeleteProject={deleteProject}
      />

      <DocumentList
        documents={selectedProject?.documents || []}
        selectedDocumentId={selectedDocumentId}
        onSelectDocument={setSelectedDocumentId}
        onDeleteDocument={docId => {
          if (selectedProjectId) {
            deleteDocument(selectedProjectId, docId);
            if (selectedDocumentId === docId) {
              setSelectedDocumentId(null);
            }
          }
        }}
        onAddFiles={() => setShowFileDropZone(true)}
      />

      <div className="content-area">
        {showFileDropZone ? (
          <div className="file-drop-container">
            <FileDropZone onFilesSelected={handleFilesSelected} />
            <button onClick={() => setShowFileDropZone(false)} className="btn-cancel">
              Annuler
            </button>
          </div>
        ) : processing ? (
          <div className="processing-indicator">
            <div className="spinner"></div>
            <p>Traitement en cours...</p>
          </div>
        ) : selectedDocument ? (
          <DetailsPanel document={selectedDocument} onExport={handleExport} />
        ) : (
          <div className="welcome-screen">
            <h2>Bienvenue dans DECLADO-IA</h2>
            <p>Workflow: Import → OCR → Classification HS → Calcul douanier → Export</p>
            <div className="quick-start">
              <h3>Démarrage rapide:</h3>
              <ol>
                <li>Créez un projet dans la sidebar</li>
                <li>Ajoutez des documents (PDF, images)</li>
                <li>L&apos;OCR et les calculs se font automatiquement</li>
                <li>Exportez vos résultats (PDF, XML eSAD, CSV, JSON)</li>
              </ol>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

export default MainLayout;
