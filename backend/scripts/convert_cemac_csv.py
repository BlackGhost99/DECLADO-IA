"""
Script pour nettoyer et convertir le CSV CEMAC extrait du PDF.
Prend le fichier brut et génère un CSV propre pour l'entraînement.
"""

import csv
import re
from pathlib import Path


def clean_hs_code(code: str) -> str | None:
    """Nettoie et normalise un code HS."""
    if not code:
        return None
    # Enlever les espaces, points, tirets
    code = code.strip().replace(".", "").replace("-", "").replace(" ", "")
    # Garder seulement les chiffres
    code = re.sub(r"[^\d]", "", code)
    if len(code) >= 4:
        # Garder le code complet (6, 8 ou 10 chiffres selon la précision CEMAC)
        # Pour plus de précision, ne pas tronquer à 4
        return code
    return None


def clean_description(desc: str) -> str:
    """Nettoie une description."""
    if not desc:
        return ""
    # Enlever les tirets de début, points, parenthèses vides
    desc = desc.strip().strip("-").strip()
    # Enlever les points de suspension multiples
    desc = re.sub(r"\.{2,}", "", desc)
    # Nettoyer les espaces multiples
    desc = re.sub(r"\s+", " ", desc)
    return desc


def process_cemac_csv(input_path: Path, output_path: Path):
    """Convertit le CSV CEMAC brut en format d'entraînement."""
    pairs = []

    with open(input_path, "r", encoding="utf-8") as f:
        # Lire avec le séparateur point-virgule
        reader = csv.reader(f, delimiter=";")

        # Sauter l'en-tête
        next(reader, None)

        for row in reader:
            if len(row) < 2:
                continue

            # Colonne 0 : NUMERO DU TARIF
            code_raw = row[0].strip()
            # Colonne 1 : DESIGNATION DES PRODUITS
            desc_raw = row[1].strip()

            if not code_raw or not desc_raw:
                continue

            # Nettoyer
            code = clean_hs_code(code_raw)
            desc = clean_description(desc_raw)

            # Valider
            if code and desc and len(desc) >= 10:
                pairs.append((code, desc))

    # Ne pas dédupliquer - on garde toutes les entrées pour l'entraînement
    # Écrire le CSV de sortie
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["hs_code", "text"])
        for code, desc in pairs:
            writer.writerow([code, desc])

    print(f"✅ Conversion terminée!")
    print(f"   Entrées lues : {len(pairs)}")
    print(f"   Codes HS distincts : {len(set(c for c, _ in pairs))}")
    print(f"   Fichier : {output_path}")
    print()
    print("Aperçu des premières lignes :")
    for code, desc in pairs[:5]:
        print(f"  {code} → {desc[:60]}...")


if __name__ == "__main__":
    # Chemins
    input_csv = Path(__file__).parents[2] / "datasets" / "datasets.csv"
    output_csv = Path(__file__).parents[1] / "data" / "hs_cemac_manual.csv"

    if not input_csv.exists():
        print(f"❌ Fichier introuvable : {input_csv}")
        print(f"   Placez votre CSV extrait dans : datasets/datasets.csv")
        exit(1)

    process_cemac_csv(input_csv, output_csv)
