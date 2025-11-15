/**
 * ==========================================
 * DECLADO-IA - Windows Code Signing Script
 * ==========================================
 * 
 * Script pour signer automatiquement les builds Windows avec un certificat
 */

const { execSync } = require('child_process');
const path = require('path');
const fs = require('fs');

/**
 * Signe un fichier exécutable Windows
 */
async function signWindows(configuration) {
  console.log('🔐 Signature du build Windows...');

  // Charger les secrets
  const secretsPath = path.join(__dirname, '..', 'secrets.json');
  
  if (!fs.existsSync(secretsPath)) {
    console.warn('⚠️  Fichier secrets.json non trouvé - Signature ignorée (mode dev)');
    return;
  }

  const secrets = JSON.parse(fs.readFileSync(secretsPath, 'utf8'));
  const codeSigningConfig = secrets.code_signing;

  if (!codeSigningConfig || !codeSigningConfig.certificate_path) {
    console.warn('⚠️  Configuration de signature non trouvée - Signature ignorée');
    return;
  }

  const certPath = codeSigningConfig.certificate_path;
  const certPassword = codeSigningConfig.certificate_password;
  const timestampUrl = codeSigningConfig.timestamp_url || 'http://timestamp.digicert.com';

  // Vérifier que le certificat existe
  if (!fs.existsSync(certPath)) {
    throw new Error(`Certificat non trouvé : ${certPath}`);
  }

  // Fichier à signer
  const filePath = configuration.path;
  
  console.log(`📝 Fichier à signer : ${filePath}`);
  console.log(`🔑 Certificat : ${certPath}`);

  try {
    // Utiliser signtool.exe (Windows SDK)
    const signtoolPath = findSignTool();
    
    const command = `"${signtoolPath}" sign /f "${certPath}" /p "${certPassword}" /tr "${timestampUrl}" /td SHA256 /fd SHA256 /v "${filePath}"`;
    
    execSync(command, { stdio: 'inherit' });
    
    console.log('✅ Signature réussie !');
  } catch (error) {
    console.error('❌ Erreur lors de la signature :', error.message);
    throw error;
  }
}

/**
 * Trouve signtool.exe dans le Windows SDK
 */
function findSignTool() {
  const possiblePaths = [
    'C:\\Program Files (x86)\\Windows Kits\\10\\bin\\x64\\signtool.exe',
    'C:\\Program Files (x86)\\Windows Kits\\10\\bin\\10.0.22621.0\\x64\\signtool.exe',
    'C:\\Program Files (x86)\\Windows Kits\\10\\bin\\10.0.22000.0\\x64\\signtool.exe',
  ];

  for (const toolPath of possiblePaths) {
    if (fs.existsSync(toolPath)) {
      return toolPath;
    }
  }

  // Chercher dans toutes les versions du SDK
  const sdkBase = 'C:\\Program Files (x86)\\Windows Kits\\10\\bin';
  if (fs.existsSync(sdkBase)) {
    const versions = fs.readdirSync(sdkBase)
      .filter(v => v.startsWith('10.0.'))
      .sort()
      .reverse();
    
    for (const version of versions) {
      const toolPath = path.join(sdkBase, version, 'x64', 'signtool.exe');
      if (fs.existsSync(toolPath)) {
        return toolPath;
      }
    }
  }

  throw new Error(
    'signtool.exe non trouvé. Installez le Windows SDK : https://developer.microsoft.com/en-us/windows/downloads/windows-sdk/'
  );
}

module.exports = signWindows;
