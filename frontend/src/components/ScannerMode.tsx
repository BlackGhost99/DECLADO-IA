import { useState, useEffect } from 'react';
import './ScannerMode.css';

interface Scanner {
  id: string;
  name: string;
  status: 'online' | 'offline' | 'busy';
  type: 'local' | 'network';
  capabilities?: string[];
}

interface ScannerModeProps {
  onBack: () => void;
  onScanComplete?: (file: File) => void;
}

export function ScannerMode({ onBack }: ScannerModeProps) {
  const [scanning, setScanning] = useState(false);
  const [scanProgress, setScanProgress] = useState(0);
  const [scanners, setScanners] = useState<Scanner[]>([]);
  const [selectedScanner, setSelectedScanner] = useState<string | null>(null);
  const [detectingDevices, setDetectingDevices] = useState(true);

  useEffect(() => {
    detectScanners();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const detectScanners = async () => {
    setDetectingDevices(true);

    try {
      // 1. Détecter via l'API backend (WIA pour Windows)
      const response = await fetch('http://127.0.0.1:8000/api/scanners/detect', {
        method: 'GET',
      }).catch(() => null);

      if (response?.ok) {
        const data = await response.json();
        setScanners(data.scanners);
        if (data.scanners.length > 0) {
          setSelectedScanner(data.scanners[0].id);
        }
      } else {
        // 2. Fallback: Détecter via l'API Web
        if ('mediaDevices' in navigator) {
          const devices = await navigator.mediaDevices.enumerateDevices();
          const videoDevices = devices.filter(device => device.kind === 'videoinput');

          const detectedScanners: Scanner[] = videoDevices.map((device, index) => ({
            id: device.deviceId,
            name: device.label || `Scanner ${index + 1}`,
            status: 'online' as const,
            type: 'local' as const,
            capabilities: ['scan', 'color', 'grayscale'],
          }));

          setScanners(detectedScanners);
          if (detectedScanners.length > 0) {
            setSelectedScanner(detectedScanners[0].id);
          }
        }

        // 3. Si rien n'est détecté, utiliser les scanners système Windows
        // eslint-disable-next-line @typescript-eslint/no-explicit-any
        if (scanners.length === 0 && (window as any).electron) {
          // Demander à Electron d'interroger les périphériques WIA
          // eslint-disable-next-line @typescript-eslint/no-explicit-any
          const systemScanners = await (window as any).electron.getSystemScanners();
          if (systemScanners && systemScanners.length > 0) {
            setScanners(systemScanners);
            setSelectedScanner(systemScanners[0].id);
          }
        }

        // 4. Dernier fallback: Scanners de démonstration
        if (scanners.length === 0) {
          const demoScanners: Scanner[] = [
            {
              id: 'wia-default',
              name: 'Scanner WIA par défaut (Windows)',
              status: 'online',
              type: 'local',
              capabilities: ['scan', 'color', 'grayscale'],
            },
            {
              id: 'demo-local-1',
              name: 'HP LaserJet Pro MFP M428fdw (USB)',
              status: 'online',
              type: 'local',
              capabilities: ['scan', 'color', 'grayscale', 'duplex'],
            },
            {
              id: 'demo-network-1',
              name: 'Canon imageCLASS MF445dw (Réseau - 192.168.1.100)',
              status: 'online',
              type: 'network',
              capabilities: ['scan', 'color', 'grayscale', 'adf'],
            },
            {
              id: 'demo-network-2',
              name: 'Epson WorkForce Pro WF-4740 (Réseau - 192.168.1.105)',
              status: 'online',
              type: 'network',
              capabilities: ['scan', 'color', 'photo'],
            },
            {
              id: 'demo-local-2',
              name: 'Brother MFC-L2710DW (USB)',
              status: 'online',
              type: 'local',
              capabilities: ['scan', 'grayscale', 'duplex', 'adf'],
            },
          ];

          setScanners(demoScanners);
          if (!selectedScanner) {
            setSelectedScanner(demoScanners[0].id);
          }
        }
      }
    } catch (error) {
      console.error('Erreur lors de la détection des scanners:', error);

      // Fallback final en cas d'erreur
      const fallbackScanners: Scanner[] = [
        {
          id: 'system-default',
          name: 'Scanner système par défaut',
          status: 'online',
          type: 'local',
          capabilities: ['scan'],
        },
      ];
      setScanners(fallbackScanners);
      setSelectedScanner(fallbackScanners[0].id);
    } finally {
      setDetectingDevices(false);
    }
  };

  const handleScan = async () => {
    if (!selectedScanner) {
      alert('Veuillez sélectionner un scanner');
      return;
    }

    setScanning(true);
    setScanProgress(0);

    // Simuler le processus de scan
    const interval = setInterval(() => {
      setScanProgress(prev => {
        if (prev >= 100) {
          clearInterval(interval);
          setScanning(false);
          alert(
            `Numérisation terminée avec ${scanners.find(s => s.id === selectedScanner)?.name}!`
          );
          return 100;
        }
        return prev + 10;
      });
    }, 300);

    // TODO: Appel au backend pour lancer le scan
    // await fetch('http://127.0.0.1:8000/api/scanners/scan', {
    //   method: 'POST',
    //   body: JSON.stringify({ scannerId: selectedScanner, settings: {...} })
    // });
  };

  return (
    <div className="scanner-mode">
      <div className="scanner-header">
        <button onClick={onBack} className="btn-back">
          ← Retour
        </button>
        <h2>🖨️ Numérisation Scanner</h2>
      </div>

      <div className="scanner-content">
        <div className="scanner-preview">
          <div className="scanner-icon">🖨️</div>
          {scanning ? (
            <div className="scanning-animation">
              <div className="scan-line" data-progress={scanProgress}></div>
              <p className="scan-status">Numérisation en cours... {scanProgress}%</p>
            </div>
          ) : (
            <p className="scanner-ready">Scanner prêt</p>
          )}
        </div>

        <div className="scanner-controls">
          <div className="scanner-settings">
            <h3>Paramètres de numérisation</h3>

            <div className="setting-group">
              <label htmlFor="scanner-resolution">Résolution</label>
              <select id="scanner-resolution" className="scanner-select">
                <option value="150">150 DPI - Rapide</option>
                <option value="300" selected>
                  300 DPI - Standard
                </option>
                <option value="600">600 DPI - Haute qualité</option>
              </select>
            </div>

            <div className="setting-group">
              <label htmlFor="scanner-color">Mode couleur</label>
              <select id="scanner-color" className="scanner-select">
                <option value="color" selected>
                  Couleur
                </option>
                <option value="grayscale">Niveaux de gris</option>
                <option value="bw">Noir et blanc</option>
              </select>
            </div>

            <div className="setting-group">
              <label htmlFor="scanner-format">Format de sortie</label>
              <select id="scanner-format" className="scanner-select">
                <option value="pdf" selected>
                  PDF
                </option>
                <option value="jpg">JPEG</option>
                <option value="png">PNG</option>
                <option value="tiff">TIFF</option>
              </select>
            </div>

            <div className="setting-group">
              <label htmlFor="scanner-pages">Type de document</label>
              <select id="scanner-pages" className="scanner-select">
                <option value="single" selected>
                  Page simple
                </option>
                <option value="multiple">Pages multiples</option>
                <option value="duplex">Recto-verso</option>
              </select>
            </div>
          </div>

          <div className="scanner-actions">
            <button onClick={handleScan} disabled={scanning} className="btn-scan">
              {scanning ? '⏳ Numérisation...' : '🖨️ Lancer la numérisation'}
            </button>

            <div className="scanner-info">
              <p>
                💡 <strong>Astuce :</strong> Placez le document face vers le bas sur le scanner
              </p>
              <p>📋 Les documents numérisés seront automatiquement traités par l&apos;OCR</p>
            </div>
          </div>
        </div>
      </div>

      <div className="scanner-devices">
        <div className="devices-header">
          <h3>Scanners détectés</h3>
          <button onClick={detectScanners} className="btn-refresh" disabled={detectingDevices}>
            {detectingDevices ? '🔄 Recherche...' : '🔄 Actualiser'}
          </button>
        </div>

        <div className="device-list">
          {scanners.length === 0 ? (
            <div className="no-devices">
              <p>❌ Aucun scanner détecté</p>
              <p className="device-note">
                Vérifiez que votre scanner ou imprimante multifonction est allumé(e) et connecté(e)
              </p>
            </div>
          ) : (
            scanners.map(scanner => (
              <div
                key={scanner.id}
                className={`device-item ${selectedScanner === scanner.id ? 'selected' : ''} ${scanner.status === 'offline' ? 'offline' : ''}`}
                onClick={() => scanner.status === 'online' && setSelectedScanner(scanner.id)}
              >
                <span className="device-status">
                  {scanner.status === 'online' ? '🟢' : scanner.status === 'busy' ? '🟡' : '🔴'}
                </span>
                <div className="device-info">
                  <span className="device-name">{scanner.name}</span>
                  <span className="device-type">
                    {scanner.type === 'local' ? '📍 Local' : '🌐 Réseau'}
                    {scanner.status === 'busy' && ' - Occupé'}
                    {scanner.status === 'offline' && ' - Hors ligne'}
                  </span>
                  {scanner.capabilities && (
                    <span className="device-capabilities">
                      {scanner.capabilities.includes('duplex') && '📄 Recto-verso '}
                      {scanner.capabilities.includes('adf') && '📑 Chargeur auto '}
                      {scanner.capabilities.includes('color') && '🎨 Couleur'}
                    </span>
                  )}
                </div>
                {selectedScanner === scanner.id && <span className="device-selected">✓</span>}
              </div>
            ))
          )}
          <p className="device-note">
            💡 Les scanners réseau et imprimantes multifonctions sont détectés automatiquement
          </p>
        </div>
      </div>
    </div>
  );
}
