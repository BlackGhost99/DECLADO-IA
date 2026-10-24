# Instructions pour les assistants

- Spécifications : `docs/specifications/` (cahier des charges, conception, plan et recette). Les exigences sont numérotées (ACC-01…) et les tests de recette aussi (T01…) : référencez-les.
- Un lot à la fois ; compte rendu dans `docs/lots/lot-N.md` (fonctionnalités terminées, commandes, tests exécutés, limites, prochaine étape).
- **Avant toute modification importante, lire les PR, branches et derniers commits du dépôt.** Plusieurs assistants travaillent sur ClairTransit ; ne jamais supposer qu'un état précédent décrit le dernier travail de Claude/ChatGPT.
- Tout modèle propre à une société hérite d'`apps.core.models.OrganizationOwnedModel` et se lit via `objects.for_organization(request.organization)`. Ajouter un test d'accès croisé pour chaque nouvel endpoint.
- Les transitions et modifications passent par des services (`services.py`) qui journalisent via `apps.audit.services.record_event`.
- Codes douaniers et références en texte, jamais en entier ; montants en Decimal.
- Vérifications : `cd backend && ruff check . && ruff format --check . && python manage.py makemigrations --check --dry-run && python -m pytest` ; `cd frontend && npm run typecheck && npm test && npm run build`.

## Principes produit non négociables

- ClairTransit est d'abord une **plateforme de préparation douanière CEMAC**, pas un remplacement des systèmes officiels des Douanes.
- Périmètre commercial V1 : **commissionnaires en douane / sociétés de transit**. L'architecture doit toutefois permettre plus tard des profils `IMPORTER`, `LOGISTICS_PROVIDER` et `CUSTOMS_ADVISOR` sans dupliquer le moteur.
- Un dossier peut contenir plusieurs expéditions, plusieurs factures et des dizaines/centaines de pièces. **Ne jamais modéliser “1 document = 1 facture”.** Les relations document↔facture↔expédition↔marchandise sont potentiellement plusieurs-à-plusieurs.
- Distinguer au minimum : facture commerciale, facture/attestation de fret, assurance, titre de transport (B/L, LTA/AWB, lettre de voiture), packing list, certificat d'origine et autres pièces réglementaires.
- Les documents demandés au client sont configurables par société. Les **obligations réglementaires CEMAC/pays sont versionnées et ne peuvent pas être supprimées par un admin société**.
- Un dossier peut commencer avec une facture seule. Les calculs peuvent être provisoires tant que fret/assurance ou autres éléments nécessaires ne sont pas connus ; la validation finale doit rester bloquée si une exigence réglementaire nécessaire manque.
- Le code SH présent sur la facture est l'entrée prioritaire : normaliser → rapprocher du référentiel CEMAC → appliquer le Rule Engine. Une suggestion IA n'intervient que si le code est absent, incomplet, ambigu ou incohérent.
- Les taux, règles, exonérations, bases, arrondis et calculs douaniers sont **déterministes, versionnés, sourcés et reproductibles**. Un LLM ne calcule ni ne décide librement un droit ou une taxe.
- L'IA est **invisible dans l'interface** : pas de chatbot générique. Elle sert à comprendre les documents, extraire, traduire, résoudre les entités, inférer les relations, détecter les contradictions et orchestrer les outils.
- Toute sortie IA passe par un schéma structuré, validation applicative, provenance et contrôle métier. Une IA doit pouvoir répondre « information insuffisante » ; ne jamais forcer une association ou un classement.
- Les associations documentaires doivent être explicables : références concordantes, fournisseur, PO, B/L, dates, produits, destinataire, etc. Les associations ambiguës restent à vérifier humainement.
- Prévoir un `AI Gateway` multi-fournisseurs ; ne pas disperser les SDK OpenAI/Anthropic/Google/Groq dans le domaine métier. Le système doit continuer à fonctionner en mode manuel si le fournisseur IA est indisponible.
- Langues prévues dès l'architecture : **FR, EN, ES, AR** ; interface, langue de société, langue des documents/OCR et langue des sorties sont séparées. Préparer le RTL. Les textes officiels du référentiel restent conservés dans leur langue/source d'origine.
- Sécurité : isolation multi-tenant stricte, MFA, chiffrement, secrets uniquement backend, audit append-only, sauvegardes, limitation/validation des uploads et antivirus reconnu. **Ne pas développer d'antivirus maison** ; privilégier un scanner auto-hébergé (ClamAV en V1) avant OCR/IA/stockage métier.
- Ne jamais envoyer un document client à un service public d'analyse de fichiers. Les intégrations IA/sécurité externes doivent minimiser les données transmises et respecter les exigences de confidentialité.
- « Validé » dans ClairTransit signifie **validé en interne**, jamais accepté par la Douane.
- Toute donnée fictive de démonstration doit être explicitement marquée fictive ; ne jamais afficher un taux, une taxe, une compatibilité SYDONIA ou une obligation réglementaire comme vraie sans source vérifiée.

## Organisation du travail en 5 conversations

Pour les développements structurants, organiser le travail en **5 conversations distinctes mais coordonnées**, toutes sur le même ClairTransit Core :

1. **Documents douaniers & règles CEMAC** — taxonomie, exigences documentaires, réglementation versionnée, contrôles et readiness.
2. **Multi-métiers & ClairTransit Core** — profils d'organisation, capacités, workflows et parcours Transit/Importateur/Logisticien/Conseil.
3. **IA invisible & intelligence documentaire** — extraction, graphe documentaire, relations M:N, AI Gateway, anomalies et revue humaine.
4. **Multilingue natif** — FR/EN/ES/AR, OCR multilingue, langues organisation/utilisateur/document/sortie et RTL.
5. **Sécurité & fiabilité** — isolation multi-tenant, ClamAV/quarantaine, MFA, API/secrets, sauvegardes, restauration et sécurité IA.

Chaque conversation doit lire `main`, les PR ouvertes et les derniers commits avant de coder ; rester dans son périmètre sauf dépendance vérifiée ; ne pas dupliquer ni écraser le travail d'une autre conversation ; pousser sur une branche dédiée ; exécuter la CI ; fusionner seulement après validation ; documenter ce qui est terminé, les limites et la prochaine priorité.

Ces conversations sont des **axes de travail**, pas cinq produits indépendants : modèles partagés, règles d'isolation, audit, référentiels et conventions restent communs.

## Document de référence

Lire aussi `docs/architecture/principes-produit-plan-amelioration.md` avant toute évolution structurante.

- Interface : le français reste la langue actuelle de développement, mais tout nouveau texte doit être pensé pour l'i18n ; éviter d'augmenter la dette de textes codés en dur.
