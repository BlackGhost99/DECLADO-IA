const { app, BrowserWindow, ipcMain } = require('electron');
const path = require('path');
const fs = require('fs');
const { spawn } = require('child_process');
const axios = require('axios');

// Configuration
const BACKEND_HOST = '127.0.0.1';
let BACKEND_PORT = 8000; // mutable: peut basculer sur un port de repli
const BACKEND_PORT_FALLBACK = 8001;
const getBackendUrl = () => `http://${BACKEND_HOST}:${BACKEND_PORT}`;

// Supprimer l'avertissement CSP en mode développement (optionnel)
// L'avertissement est normal car Vite nécessite 'unsafe-eval' pour HMR
if (!app.isPackaged) {
  // Optionnel : supprimer l'avertissement console (l'avertissement reste dans DevTools)
  process.env.ELECTRON_DISABLE_SECURITY_WARNINGS = 'true';
}

let mainWindow;
let backendProcess;

/**
 * Démarre le serveur backend Python
 */
function startBackend() {
  console.log('🚀 Démarrage du backend Python...');

  const isDev = !app.isPackaged;
  let pythonPath;
  let scriptPath;

  if (isDev) {
    // Mode développement
    const projectRoot = path.resolve(__dirname, '..', '..');
    const venvPython = path.join(projectRoot, 'backend', 'venv', 'Scripts', 'python.exe');
    pythonPath = fs.existsSync(venvPython) ? venvPython : 'python'; // utilise le venv si présent
    scriptPath = path.join(__dirname, '../../backend/app/main.py');
  } else {
    // Mode production (après packaging)
    pythonPath = path.join(process.resourcesPath, 'backend', 'declado-backend.exe');
    scriptPath = null;
  }

  try {
    if (isDev) {
      backendProcess = spawn(
        pythonPath,
        [
          '-m',
          'uvicorn',
          'app.main:app',
          '--host',
          BACKEND_HOST,
          '--port',
          BACKEND_PORT.toString(),
          '--reload',
          '--no-access-log',
        ],
        {
          cwd: path.join(__dirname, '../../backend'),
          stdio: 'pipe',
        }
      );

      backendProcess.stdout.on('data', data => {
        console.log(`[Backend] ${data.toString().trim()}`);
      });

      backendProcess.stderr.on('data', data => {
        console.error(`[Backend Error] ${data.toString().trim()}`);
      });

      backendProcess.on('close', code => {
        console.log(`Backend process exited with code ${code}`);
      });

      console.log('✅ Backend démarré (dev mode)');
    } else {
      backendProcess = spawn(pythonPath, [], { stdio: 'pipe' });
      console.log('✅ Backend démarré (prod mode)');
    }
  } catch (error) {
    console.error('❌ Erreur de démarrage du backend:', error);
  }
}

/**
 * Arrête le serveur backend
 */
function stopBackend() {
  if (backendProcess) {
    console.log('🛑 Arrêt du backend...');
    backendProcess.kill();
    backendProcess = null;
  }
}

/**
 * Vérifie si le backend est prêt
 */
async function waitForBackend(maxAttempts = 60) {
  console.log('⏳ Attente du backend...');

  // Attendre 2 secondes avant la première tentative pour laisser le backend démarrer
  await new Promise(resolve => setTimeout(resolve, 2000));

  for (let i = 0; i < maxAttempts; i++) {
    try {
      const response = await axios.get(`${getBackendUrl()}/api/health/ping`, { timeout: 3000 });
      if (response.status === 200) {
        console.log('✅ Backend prêt!');
        return true;
      }
    } catch (error) {
      // Essayer le port de repli si différent
      if (BACKEND_PORT !== BACKEND_PORT_FALLBACK) {
        try {
          const fallbackUrl = `http://${BACKEND_HOST}:${BACKEND_PORT_FALLBACK}`;
          const response2 = await axios.get(`${fallbackUrl}/api/health/ping`, { timeout: 3000 });
          if (response2.status === 200) {
            BACKEND_PORT = BACKEND_PORT_FALLBACK;
            console.log(`🔁 Backend détecté sur le port ${BACKEND_PORT}`);
            return true;
          }
        } catch (_) {
          // ignore et on attend
        }
      }
      // Backend pas encore prêt, réessayer après 500ms
      await new Promise(resolve => setTimeout(resolve, 500));
    }
  }

  console.error('❌ Backend timeout');
  return false;
}

/**
 * Crée la fenêtre principale
 */
async function createWindow() {
  mainWindow = new BrowserWindow({
    width: 1200,
    height: 800,
    webPreferences: {
      preload: path.join(__dirname, 'preload.js'),
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: false, // Nécessaire pour preload script
      webSecurity: true, // Activer la sécurité web
    },
    title: 'DECLADO-IA',
    icon: path.join(__dirname, '../assets/icon.png'), // TODO: ajouter l'icône
  });

  // Configurer la Content Security Policy pour Electron
  const isDev = !app.isPackaged;

  if (isDev) {
    // En développement, permettre unsafe-eval pour Vite HMR
    mainWindow.webContents.session.webRequest.onHeadersReceived((details, callback) => {
      callback({
        responseHeaders: {
          ...details.responseHeaders,
          'Content-Security-Policy': [
            "default-src 'self'; " +
              "script-src 'self' 'unsafe-inline' 'unsafe-eval' http://localhost:* http://127.0.0.1:*; " +
              "style-src 'self' 'unsafe-inline'; " +
              "img-src 'self' data: http: https:; " +
              "font-src 'self' data:; " +
              "connect-src 'self' http://localhost:* http://127.0.0.1:* ws://localhost:* ws://127.0.0.1:*; " +
              "frame-src 'none'; " +
              "object-src 'none'; " +
              "base-uri 'self'; " +
              "form-action 'self';",
          ],
        },
      });
    });
  } else {
    // En production, CSP stricte sans unsafe-eval
    mainWindow.webContents.session.webRequest.onHeadersReceived((details, callback) => {
      callback({
        responseHeaders: {
          ...details.responseHeaders,
          'Content-Security-Policy': [
            "default-src 'self'; " +
              "script-src 'self' 'unsafe-inline'; " +
              "style-src 'self' 'unsafe-inline'; " +
              "img-src 'self' data: http: https:; " +
              "font-src 'self' data:; " +
              "connect-src 'self' http://localhost:8000 http://127.0.0.1:8000 http://localhost:8001 http://127.0.0.1:8001; " +
              "frame-src 'none'; " +
              "object-src 'none'; " +
              "base-uri 'self'; " +
              "form-action 'self';",
          ],
        },
      });
    });
  }

  // Attendre que le backend soit prêt
  const backendReady = await waitForBackend();

  if (!backendReady) {
    console.error(
      "⚠️  Backend non disponible, l'application pourrait ne pas fonctionner correctement"
    );
  }

  // Charger l'application
  if (isDev) {
    // Mode développement : Vite dev server (avec fallback de port)
    const devCandidates = ['http://localhost:5173', 'http://localhost:5174'];
    let chosen = devCandidates[0];
    for (const url of devCandidates) {
      try {
        await axios.get(url, { timeout: 1000 });
        chosen = url;
        break;
      } catch (_) {
        // try next
      }
    }
    mainWindow.loadURL(chosen);
    mainWindow.webContents.openDevTools();
  } else {
    // Mode production : fichiers buildés
    mainWindow.loadFile(path.join(__dirname, '../dist/index.html'));
  }

  mainWindow.on('closed', () => {
    mainWindow = null;
  });
}

// Gestion du cycle de vie de l'application
app.whenReady().then(createWindow);

app.on('window-all-closed', () => {
  stopBackend();
  if (process.platform !== 'darwin') {
    app.quit();
  }
});

app.on('activate', () => {
  if (BrowserWindow.getAllWindows().length === 0) {
    createWindow();
  }
});

app.on('before-quit', () => {
  stopBackend();
});

// IPC Handlers pour communication avec le renderer
ipcMain.handle('get-backend-url', () => {
  return getBackendUrl();
});

ipcMain.handle('check-backend-status', async () => {
  try {
    const response = await axios.get(`${getBackendUrl()}/api/health/ping`, {
      timeout: 2000,
    });
    return { status: 'ok', data: response.data };
  } catch (error) {
    return { status: 'error', message: error.message };
  }
});
