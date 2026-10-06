# Registre des questions ouvertes

Reprend `docs/specifications/03-plan-et-recette.md` §7 et ajoute les points relevés au lot 0.

| Question | Impact | Responsable | Lot concerné | État |
|---|---|---|---|---|
| Nature et présence des codes sur les factures | Calibration de l'extraction | Porteur du projet + transitaire | 3 | Ouvert |
| Origine des colonnes spécifiques de l'Excel | Publication des règles | Détenteur du classeur + référent douanier | 1 | Ouvert |
| Tarif/fiscalité Gabon applicables et dates | Calcul opérationnel | Référent douanier | 6 | Ouvert |
| Arrondis et regroupements | Recette calcul | Référent métier | 4–6 | Ouvert |
| Séparation préparateur/validateur | Politique de validation (`require_distinct_validator: true` par défaut) | Société pilote | 5 | Ouvert |
| Formats du système officiel | Intégration | Société pilote / éditeur | ultérieur | Ouvert |
| Hébergement, conservation, fournisseur IA | Pièces réelles, production | Porteur du projet | 3, 6 | Ouvert |
| Volumes et budget | Dimensionnement | Porteur + équipe | après lot 0 | Ouvert |
| PDF 2009 original (reçu : texte extrait seulement) ; `audit-et-conception.md` | Désignations et taux non rattachés aux codes 2009 | Porteur du projet | 1 | Ouvert |
| Fichier « 2015 TARIF EXCEL.xls » visé par les formules du classeur 2016 | STT, TPM, TCI, OAD non vérifiables ; clé TPM décalée | Détenteur du classeur | 1, 4 | Ouvert |
| Intégration avec le code existant du dépôt DECLADO-IA (FastAPI/Electron) | Architecture cible | Porteur du projet | tous | Ouvert |
| Signification des colonnes DSO, STT, TPM (unités ?), OAD, TAUX du CSV | Observations seulement | Détenteur du classeur + référent douanier | 1, 4 | Ouvert |
| Restitution des accents abîmés du classeur (1 055 libellés) | Lisibilité, recherche | Gestionnaire du référentiel | 1 | Ouvert |
| Nom du produit : DECLADO (projet) ou ClairTransit (documents) | Nom de code du dépôt, libellés | Porteur du projet | tous | Ouvert : ClairTransit par défaut |
| Dépôt Git distant | CI réelle, revue | Porteur du projet | 0 | Ouvert |
| Envoi d'e-mails (invitation, mot de passe oublié) | Gestion des comptes | Porteur du projet | 2 | Ouvert |
