# ==========================================
# DECLADO-IA - PyInstaller Build Script
# ==========================================
# Script pour créer un exécutable Windows du backend Python

import PyInstaller.__main__
import os
import sys
from pathlib import Path

# Configuration
PROJECT_ROOT = Path(__file__).parent.parent
BACKEND_DIR = PROJECT_ROOT / "backend"
DIST_DIR = PROJECT_ROOT / "dist" / "backend"
BUILD_DIR = PROJECT_ROOT / "build"

# Nom de l'application
APP_NAME = "declado-ia-backend"
VERSION = "0.1.0"

def build_backend():
    """Construit l'exécutable backend avec PyInstaller"""
    
    print("🔨 Construction du backend avec PyInstaller...")
    print(f"📁 Dossier source : {BACKEND_DIR}")
    print(f"📦 Dossier destination : {DIST_DIR}")
    
    # Options PyInstaller
    options = [
        str(BACKEND_DIR / "app" / "main.py"),  # Point d'entrée
        f"--name={APP_NAME}",
        f"--distpath={DIST_DIR}",
        f"--workpath={BUILD_DIR}",
        "--onefile",  # Un seul fichier exécutable
        "--windowed",  # Pas de console (ou --console pour debug)
        "--noupx",  # Pas de compression UPX
        
        # Icône (si disponible)
        # f"--icon={PROJECT_ROOT / 'assets' / 'icon.ico'}",
        
        # Inclure les données nécessaires
        f"--add-data={BACKEND_DIR / 'app' / 'templates'}:templates",
        f"--add-data={PROJECT_ROOT / 'data' / 'referentials'}:data/referentials",
        
        # Bibliothèques cachées
        "--hidden-import=uvicorn",
        "--hidden-import=fastapi",
        "--hidden-import=sqlalchemy",
        "--hidden-import=pytesseract",
        "--hidden-import=cv2",
        "--hidden-import=sklearn",
        "--hidden-import=onnxruntime",
        
        # Exclure les modules inutiles pour réduire la taille
        "--exclude-module=matplotlib",
        "--exclude-module=tkinter",
        "--exclude-module=notebook",
        
        # Informations de version
        f"--version-file={PROJECT_ROOT / 'version_info.txt'}" if (PROJECT_ROOT / "version_info.txt").exists() else "",
        
        # Options de sécurité
        "--strip",  # Retirer les symboles de debug
        
        # Nom du fichier
        f"--name=DECLADO-IA-Backend-{VERSION}",
    ]
    
    # Nettoyer les options vides
    options = [opt for opt in options if opt]
    
    # Lancer PyInstaller
    try:
        PyInstaller.__main__.run(options)
        print("✅ Build réussi !")
        print(f"📦 Exécutable : {DIST_DIR / f'{APP_NAME}.exe'}")
    except Exception as e:
        print(f"❌ Erreur lors du build : {e}")
        sys.exit(1)

def create_version_info():
    """Crée le fichier version_info.txt pour Windows"""
    version_info = f"""
VSVersionInfo(
  ffi=FixedFileInfo(
    filevers=({VERSION.replace('.', ', ')}, 0),
    prodvers=({VERSION.replace('.', ', ')}, 0),
    mask=0x3f,
    flags=0x0,
    OS=0x40004,
    fileType=0x1,
    subtype=0x0,
    date=(0, 0)
  ),
  kids=[
    StringFileInfo(
      [
      StringTable(
        u'040904B0',
        [StringStruct(u'CompanyName', u'DECLADO-IA'),
        StringStruct(u'FileDescription', u'Backend DECLADO-IA - Extraction Factures & Calculs Douaniers'),
        StringStruct(u'FileVersion', u'{VERSION}'),
        StringStruct(u'InternalName', u'declado-backend'),
        StringStruct(u'LegalCopyright', u'Copyright © 2025 DECLADO-IA'),
        StringStruct(u'OriginalFilename', u'{APP_NAME}.exe'),
        StringStruct(u'ProductName', u'DECLADO-IA Backend'),
        StringStruct(u'ProductVersion', u'{VERSION}')])
      ]), 
    VarFileInfo([VarStruct(u'Translation', [1033, 1200])])
  ]
)
"""
    
    version_file = PROJECT_ROOT / "version_info.txt"
    version_file.write_text(version_info)
    print(f"📝 Fichier version créé : {version_file}")

if __name__ == "__main__":
    print("=" * 60)
    print("DECLADO-IA - Build Backend Windows")
    print("=" * 60)
    
    # Créer le fichier de version
    create_version_info()
    
    # Construire
    build_backend()
    
    print("\n✅ Processus terminé !")
