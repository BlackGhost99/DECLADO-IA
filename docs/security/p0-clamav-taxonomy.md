# P0 — Sécurité des fichiers et taxonomie documentaire

## Contrat de sécurité des uploads

**Aucun original provenant d'un utilisateur n'est transformé, exposé, lié à un dossier, ni envoyé à l'OCR/IA avant confirmation de clamd.**

1. Autorisation préalable par société, rôle et état de révision.
2. Réception dans `PRIVATE_STORAGE_ROOT/quarantine/` (fichier 0600, nom aléatoire).
3. Taille bornée pendant la réception, SHA-256 calculé.
4. Analyse ClamAV par `INSTREAM`, sur réseau Docker interne uniquement.
5. `stream: OK` exactement : contrôle MIME et structure, puis promotion atomique vers `documents/<organization_id>/`.
6. Signature détectée : HTTP 422 `MALWARE_DETECTED` ; échec, timeout, réponse non reconnue, daemon absent : HTTP 503 `MALWARE_SCAN_UNAVAILABLE`. Dans les deux cas, aucune ligne Document et aucun accès à l'original.
7. Quarantaine supprimée après résultat et à l'issue de toute erreur. Rejet journalisé sans données du contenu. Le traitement ne se poursuit **jamais** en cas d'échec antivirus.

Le service ClamAV ne publie pas de port hôte. Son TCP n'a ni chiffrement ni authentification : il doit rester sur un réseau de confiance. Le premier démarrage télécharge les signatures et peut prendre du temps ; en attendant, les uploads restent refusés (fail closed). Faire superviser l'âge des signatures et les refus ; prévoir une purge des fichiers orphelins de quarantaine après panne brutale du processus. L'analyse antivirus est un **contrôle parmi d'autres**, pas une garantie de sécurité absolue.

### Configuration

`CLAMAV_HOST=clamav`, `CLAMAV_PORT=3310`, `CLAMAV_CONNECT_TIMEOUT=5`, `CLAMAV_SCAN_TIMEOUT=120`.
Aucune option pour désactiver l'antivirus en production. Les tests remplacent exclusivement le client réseau par un faux scanner dans les fixtures de test ; les scénarios de refus exercent le vrai chemin logiciel.

`docker compose -f infra/compose.yaml up --build` démarre ClamAV et FreshClam. Les machines hors Docker doivent disposer d'un clamd accessible sur un réseau privé. Dimensionner `StreamMaxLength` et `MaxFileSize` au moins pour `DOCUMENT_MAX_BYTES`.

### Limites / exploitation

- Le scan est synchrone en V1 : une API peut bloquer pendant un téléchargement de grande taille. Prévoir des métriques, quotas et workers adaptés ; l'asynchrone exigera de nouveaux états persistants `pending_scan`, `clean`, `infected`, `scan_error`.
- Les PDF/images déjà stockés avant P0 ne possèdent **pas** de preuve d'analyse : les rescanner avant exploitation réelle. Ne pas déclarer l'historique sain par déduction.
- Tout moteur PDF/OCR, y compris numérisation, passe par `documents.store_upload`. Ne jamais injecter directement des octets externes via `LocalPrivateStorage.put`.
- Une erreur d'analyse ne produit aucune pièce exploitable ; surveillance opérationnelle et alertes nécessaires.

## Taxonomie canonique 1.0

Le **code stable** désigne la nature de la pièce, jamais son caractère obligatoire. `regulations.DocumentType` est le registre unique des types et `regulations.taxonomy` le vocabulaire canonique à initialiser avec `python manage.py seed_document_types`.

Familles : `commercial`, `transport`, `insurance`, `origin`, `customs`, `regulatory`, `supporting`. Codes spécifiques : factures commerciale/fret/assurance distinctes, B/L différent de LTA ou lettre de voiture, déclarations et autorisations différenciées.

Trois dimensions indépendantes définissent la checklist :
- **collecte** (politique de la société/importateur) ;
- **traitement/calcul** (pièces nécessaires aux moteurs et à la validation technique) ;
- **obligation réglementaire** (seules les règles CEMAC/nationales vérifiées, datées, publiées et applicables).

La société peut ajouter des exigences internes mais ne peut jamais désactiver une exigence réglementaire. Les types ne créent **aucune règle juridique**. Les catégories génériques (`invoice`, `transport`, `other`) continuent à piloter l'ancien workflow, mais ne prouvent pas un type exact. En particulier une facture de fret ne compte pas comme facture commerciale, et un document de transport générique ne compte ni comme B/L ni comme LTA.

Les nouveaux rattachements acceptent `document_type_code`, contrôlé contre le catalogue. La pièce conserve son type lors d'un remplacement. Pour les anciens rattachements non classifiés, seuls `packing_list` et `origin` se déduisent sans ambiguïté ; les autres attendent une classification humaine. Aucun classement proposé par OCR/IA ne vaut automatiquement validation réglementaire.

## Contrôles d'acceptation

- ClamAV absent, timeout, erreur, réponse vide : HTTP 503, zéro Document, aucun original exploitable.
- EICAR / `FOUND` : HTTP 422 et zéro Document ; zéro lien téléchargeable.
- PDF sain : empreinte inchangée, stockage privé, audit, téléchargements sous contrôle des permissions.
- Deux sociétés avec un même SHA : pas d'accès ni de fuite inter-sociétés.
- Types spécifiques et `usage` compatibles, remplacement conservant le type.
- Checklist reflète le code explicite ; `transport` ou `invoice` générique n'inventent pas un type légal.

**Mise en production conditionnelle** à l'exécution de la CI, à un test d'intégration contre un véritable clamd (EICAR + PDF sain), et à la revue du déploiement (réseaux, volumes, signatures, sauvegardes).
