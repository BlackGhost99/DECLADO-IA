# ClairTransit — Dossier de développement V1

Version 1.0, 6 octobre 2026. Ce dossier prépare le développement avec Claude ou une autre équipe. Il contient des spécifications ; aucune application n’a encore été implémentée dans ce lot de travail.

## Documents

1. [Cahier des charges](01-cahier-des-charges.md) : besoins, périmètre, rôles, exigences, écrans et contraintes.
2. [Conception technique](02-conception-technique.md) : architecture, modèle de données, API, calcul, sécurité et exploitation.
3. [Plan et recette](03-plan-et-recette.md) : lots, backlog, 38 scénarios de vérification et questions ouvertes.
4. [Démarrage avec Claude](04-demarrage-claude.md) : message prêt à transmettre.
5. [Audit des sources](../audit-et-conception.md) : examen préalable du PDF et de l’Excel.

La correction métier centrale est intégrée partout : lire les codes douaniers présents, les contrôler et les faire confirmer ; rechercher/proposer seulement lorsque nécessaire. La nature exacte des codes sur les factures réelles reste à vérifier sur échantillon.

## Utilisation

Transmettre à Claude l’archive entière, ou les quatre documents principaux avec l’audit. Coller ensuite le message de démarrage. Les fichiers Markdown sont lisibles et directement exploitables dans un dépôt de développement.

L’archive ne contient pas les factures, le PDF tarifaire ni le classeur original. Les fournir séparément lorsqu’un import réel est nécessaire. Le travail peut commencer avec les fixtures synthétiques décrites.

## Statut des décisions

Le périmètre et la technologie constituent une proposition cohérente pour la V1. Les seuils de performance, limites d’upload, politique de double validation et objectifs de sauvegarde sont des valeurs de conception proposées, à confirmer au pilote. Les paramètres juridiques/fiscaux doivent avoir leurs propres sources et validation.

Pour collaborer ensuite, transmettre les fichiers/diffs produits par Claude et ses résultats de tests. Une revue pourra vérifier les exigences numérotées et les scénarios de recette. Aucun échange automatique avec Claude n’est configuré par ces documents.
