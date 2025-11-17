"""
Configuration de l'application DECLADO-IA
Utilise pydantic-settings pour charger depuis .env
"""

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Configuration de l'application"""

    # Application
    APP_NAME: str = "DECLADO-IA"
    APP_VERSION: str = "0.1.0"
    APP_ENV: str = "development"
    DEBUG: bool = True

    # API
    API_HOST: str = "127.0.0.1"
    API_PORT: int = 8000
    API_RELOAD: bool = True

    # CORS
    CORS_ORIGINS: list[str] = ["http://localhost:5173", "http://127.0.0.1:5173", "app://declado-ia"]

    # Database (SQLCipher)
    DATABASE_URL: str = "sqlite:///./data/declado.db"
    # Legacy fallback; will be ignored when DPAPI-managed key is available
    DATABASE_ENCRYPTION_KEY: str = "changeme_with_32_byte_key_here"
    # Optional passphrase to derive key (PBKDF2). If not set, SECRET_KEY is used as fallback.
    DB_PASSPHRASE: str | None = None
    # DPAPI-protected keystore file for derived key (Windows only). Otherwise, key is derived at runtime.
    DB_KEYSTORE_PATH: Path = Path.home() / "AppData/Roaming/DECLADO-IA/db_key.bin"
    DB_SALT_PATH: Path = Path.home() / "AppData/Roaming/DECLADO-IA/db_key.salt"
    DB_PBKDF2_ITERATIONS: int = 200_000

    # Security
    SECRET_KEY: str = "changeme_super_secret_key_for_jwt_signing"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30

    # OCR
    TESSERACT_CMD: str = "tesseract"  # Chemin vers tesseract
    TESSERACT_LANG: str = "fra+eng"

    # ML
    ML_MODELS_PATH: Path = Path("./ml/models")
    ML_CONFIDENCE_THRESHOLD: float = 0.75

    # Logs
    LOG_LEVEL: str = "INFO"
    LOG_FILE: str = "./logs/declado-ia.log"
    # HMAC signing for append-only logs
    LOG_HMAC_KEY: str | None = None  # If None, derived from SECRET_KEY

    # Antivirus
    AV_SCAN_ENABLED: bool = True
    AV_DEFENDER_PATH: Path | None = None  # If None, auto-detect
    AV_CLAMSCAN_PATH: Path | None = None  # Optional fallback

    # Repository signature verification
    SIGNING_PUBLIC_KEY_PATH: Path | None = None  # ed25519 public key file
    SIGNED_REPOS: list[Path] = [
        Path("./ml/models"),
        Path("./config"),
    ]  # paths to verify if .sig present

    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", case_sensitive=True, extra="ignore"
    )


# Instance globale des settings
settings = Settings()
