"""
Configuration de la base de données avec SQLAlchemy et SQLCipher (optional)
Falls back to standard SQLite if SQLCipher unavailable.
"""

import logging
from collections.abc import Generator

from sqlalchemy import create_engine, event, text
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.config import settings

logger = logging.getLogger(__name__)

# Attempt to import sqlcipher support
try:
    import pysqlcipher3.dbapi2  # noqa: F401

    SQLCIPHER_AVAILABLE = True
except ImportError:
    SQLCIPHER_AVAILABLE = False
    logger.warning("pysqlcipher3 not available; using standard SQLite (unencrypted)")

# URL de base de données
SQLALCHEMY_DATABASE_URL = settings.DATABASE_URL

# Configuration pour SQLite chiffré (SQLCipher)
# Note: sqlcipher3 doit être installé
connect_args = {
    "check_same_thread": False,  # Nécessaire pour SQLite avec FastAPI
}

# Créer le moteur SQLAlchemy
engine = create_engine(
    SQLALCHEMY_DATABASE_URL,
    connect_args=connect_args,
    poolclass=StaticPool,  # Pour éviter les problèmes avec SQLite
    echo=settings.DEBUG,
)


def _set_sqlite_pragma(dbapi_conn, connection_record):
    """
    Configure SQLCipher avec la clé de chiffrement si disponible
    Cette fonction est appelée à chaque nouvelle connexion
    """
    cursor = dbapi_conn.cursor()
    try:
        # Attempt SQLCipher encryption if available
        if SQLCIPHER_AVAILABLE:
            passphrase = settings.DB_PASSPHRASE or settings.SECRET_KEY
            cursor.execute("PRAGMA key = ?", (passphrase.encode("utf-8"),))
            # Vérifier la présence de SQLCipher
            cursor.execute("PRAGMA cipher_version;")
            row = cursor.fetchone()
            if row and row[0]:
                logger.info(f"SQLCipher version: {row[0]}")
            else:
                logger.warning("SQLCipher cipher_version empty; DB may be unencrypted")
        else:
            logger.debug("SQLCipher not available; using standard SQLite")
    except Exception as e:
        logger.warning(f"SQLCipher setup failed (continuing unencrypted): {e}")
    # Optimisations SQLite
    try:
        cursor.execute("PRAGMA foreign_keys = ON")
        cursor.execute("PRAGMA journal_mode = WAL")
    except Exception as e:
        logger.debug(f"Pragma optimization failed: {e}")
    cursor.close()


# Attacher l'événement pour configurer chaque connexion
event.listen(engine, "connect", _set_sqlite_pragma)

# Session factory
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Base pour les modèles
Base = declarative_base()


def get_db() -> Generator:
    """
    Dependency pour obtenir une session de base de données
    Utilisé avec FastAPI Depends()
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db() -> None:
    """
    Initialise la base de données
    Crée toutes les tables si elles n'existent pas
    """
    logger.info("Initialisation de la base de donnees...")
    try:
        # Créer toutes les tables
        Base.metadata.create_all(bind=engine)
        logger.info("Base de donnees initialisee avec succes")
    except Exception as e:
        logger.error(f"Erreur lors de l'initialisation de la base de donnees: {e}")
        raise


def test_db_connection() -> bool:
    """
    Teste la connexion à la base de données chiffrée
    Retourne True si la connexion réussit
    """
    try:
        db = SessionLocal()
        # Test simple: exécuter une requête
        db.execute(text("SELECT 1"))
        db.close()
        logger.info("Connexion a la base de donnees OK")
        return True
    except Exception as e:
        logger.error(f"Erreur de connexion a la base de donnees: {e}")
        return False
