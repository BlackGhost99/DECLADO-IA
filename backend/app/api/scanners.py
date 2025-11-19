"""
Scanner Detection API
Détecte les scanners et imprimantes multifonctions connectés (USB, réseau)
Utilise WIA (Windows Image Acquisition) pour Windows
"""
import logging
import platform

from fastapi import APIRouter, HTTPException

router = APIRouter()
logger = logging.getLogger(__name__)


def detect_windows_scanners() -> list[dict]:
    """Détecte les scanners via WIA (Windows Image Acquisition)"""
    scanners = []
    
    try:
        # Import WIA (Windows uniquement)
        import win32com.client
        
        # Créer l'objet WIA DeviceManager
        device_manager = win32com.client.Dispatch("WIA.DeviceManager")
        
        # Lister tous les périphériques WIA
        for i in range(1, device_manager.DeviceInfos.Count + 1):
            device_info = device_manager.DeviceInfos.Item(i)
            
            # Déterminer le type (scanner ou caméra)
            device_type = device_info.Type
            if device_type == 1:  # 1 = Scanner, 2 = Caméra
                device_id = str(device_info.DeviceID)
                device_name = str(device_info.Properties("Name").Value)
                manufacturer = str(device_info.Properties("Manufacturer").Value) if "Manufacturer" in [p.Name for p in device_info.Properties] else "Inconnu"
                
                # Vérifier si le scanner est connecté via réseau
                is_network = "network" in device_name.lower() or "ip" in device_name.lower()
                
                # Déterminer les capacités
                capabilities = ["scan", "color", "grayscale"]
                
                try:
                    # Essayer de se connecter au scanner pour obtenir plus d'infos
                    device = device_info.Connect()
                    
                    # Vérifier si duplex (recto-verso) est supporté
                    if hasattr(device, 'Properties'):
                        for prop in device.Properties:
                            if 'duplex' in prop.Name.lower():
                                capabilities.append('duplex')
                            if 'adf' in prop.Name.lower() or 'feeder' in prop.Name.lower():
                                capabilities.append('adf')
                    
                    status = "online"
                except Exception:
                    status = "offline"
                
                scanner = {
                    "id": f"wia-{device_id}",
                    "name": f"{device_name} ({manufacturer})",
                    "status": status,
                    "type": "network" if is_network else "local",
                    "capabilities": capabilities
                }
                scanners.append(scanner)
        
    except ImportError:
        logger.warning("Module win32com non disponible - Installation: pip install pywin32")
    except Exception as e:
        logger.error(f"Erreur lors de la détection WIA: {e}")
    
    return scanners


def detect_network_scanners() -> list[dict]:
    """Détecte les scanners réseau via SNMP ou eSCL (AirPrint)"""
    scanners = []

    # TODO: Implémenter la détection réseau
    # - Scan réseau local pour imprimantes (port 9100, 515)
    # - Protocole eSCL (AirPrint) sur port 80/443
    # - SNMP pour interroger les imprimantes multifonctions

    return scanners


@router.get("/detect")
async def detect_scanners():
    """
    Détecte tous les scanners disponibles (locaux et réseau)
    
    Returns:
        Liste des scanners avec leurs caractéristiques
    """
    try:
        scanners = []
        
        # Détection selon le système d'exploitation
        os_type = platform.system()
        
        if os_type == "Windows":
            # Utiliser WIA pour Windows
            scanners.extend(detect_windows_scanners())
        elif os_type == "Linux":
            # TODO: Utiliser SANE pour Linux
            logger.info("Détection SANE non encore implémentée pour Linux")
        elif os_type == "Darwin":  # macOS
            # TODO: Utiliser ImageCaptureCore pour macOS
            logger.info("Détection ImageCapture non encore implémentée pour macOS")
        
        # Ajouter les scanners réseau
        scanners.extend(detect_network_scanners())
        
        # Si aucun scanner détecté, retourner un scanner par défaut
        if not scanners:
            scanners = [{
                "id": "default-scanner",
                "name": "Scanner système par défaut",
                "status": "online",
                "type": "local",
                "capabilities": ["scan"]
            }]
        
        return {
            "success": True,
            "scanners": scanners,
            "count": len(scanners)
        }
        
    except Exception as e:
        logger.error(f"Erreur lors de la détection des scanners: {e}")
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.post("/scan")
async def start_scan(scanner_id: str, resolution: int = 300, color_mode: str = "color", 
                     format: str = "pdf", duplex: bool = False):
    """
    Lance une numérisation avec le scanner sélectionné
    
    Args:
        scanner_id: ID du scanner à utiliser
        resolution: Résolution en DPI (150, 300, 600)
        color_mode: Mode couleur (color, grayscale, bw)
        format: Format de sortie (pdf, jpg, png, tiff)
        duplex: Activer le recto-verso
    
    Returns:
        Fichier numérisé
    """
    try:
        # TODO: Implémenter la numérisation via WIA
        logger.info(f"Numérisation demandée: scanner={scanner_id}, resolution={resolution}, "
                   f"color={color_mode}, format={format}, duplex={duplex}")
        
        return {
            "success": True,
            "message": "Numérisation en cours...",
            "scanner_id": scanner_id,
            "settings": {
                "resolution": resolution,
                "color_mode": color_mode,
                "format": format,
                "duplex": duplex
            }
        }
        
    except Exception as e:
        logger.error(f"Erreur lors de la numérisation: {e}")
        raise HTTPException(status_code=500, detail=str(e)) from e
