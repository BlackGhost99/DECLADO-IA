@echo off
REM Script pour entraîner le classificateur HS avec votre dataset CEMAC

echo ====================================
echo Entraînement classificateur HS CEMAC
echo ====================================
echo.

set VENV_PYTHON=C:\Users\BlackGhost\Desktop\DECLADO-IA\.venv\Scripts\python.exe
set CSV_PATH=data\hs_cemac_manual.csv
set MODEL_OUT=models\hs_classifier.joblib

echo Vérification du fichier CSV...
if not exist %CSV_PATH% (
    echo ERREUR: Fichier %CSV_PATH% introuvable!
    echo.
    echo Placez votre CSV dans: backend\data\hs_cemac_manual.csv
    echo Format attendu:
    echo   hs_code,text
    echo   0901,Café même torréfié...
    echo   6109,T-shirts maillots...
    pause
    exit /b 1
)

echo.
echo Lancement de l'entraînement...
echo CSV source: %CSV_PATH%
echo Modèle destination: %MODEL_OUT%
echo.

%VENV_PYTHON% scripts\retrain_hs_classifier.py --csv %CSV_PATH% --out %MODEL_OUT%

echo.
echo ====================================
echo Entraînement terminé!
echo ====================================
pause
