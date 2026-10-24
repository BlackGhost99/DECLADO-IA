# ClairTransit — Principes produit et plan d'amélioration

Date de cadrage : 24 octobre 2026.

Ce document consolide les décisions produit, métier, IA, sécurité et internationalisation retenues pour les prochaines évolutions de ClairTransit. Il sert de référence commune aux assistants et développeurs. En cas de conflit avec une implémentation existante, ne pas contourner silencieusement le problème : documenter l'écart et proposer une migration.

## 1. Positionnement et profils métier

ClairTransit est une **plateforme de préparation douanière CEMAC**. Elle se place avant les systèmes officiels de déclaration : collecte des pièces, structuration des données, rapprochement des codes SH, application des règles et calculs déterministes, contrôles, validation interne et préparation des exports/intégrations.

ClairTransit ne doit jamais se présenter comme la Douane ni comme un remplacement de SYDONIA/ASYCUDA, CAMCIS, eDouanes, SAGE ou d'un autre système officiel.

Profils d'organisation prévus :
- `TRANSIT_COMPANY` — commissionnaire en douane / société de transit, cible V1 ;
- `IMPORTER` — grand importateur ;
- `LOGISTICS_PROVIDER` — logisticien intégré ;
- `CUSTOMS_ADVISOR` — expert/cabinet douanier.

Un même moteur et une même base doivent servir ces profils. Utiliser un `OrganizationProfile`, des modules activables et des capacités/permissions (`case.create`, `document.upload`, `classification.review`, `calculation.run`, `case.validate`, `case.export`, etc.).

## 2. Documents, factures et relations

### Trois niveaux d'exigences
1. Documents demandés au client — configurables par la société.
2. Documents nécessaires au traitement ClairTransit.
3. Documents réglementaires requis — socle CEMAC + règles nationales + régime + transport + marchandise + conditions.

Un admin société peut renforcer sa politique documentaire mais ne peut pas supprimer une obligation réglementaire active.

### Taxonomie minimale
- facture commerciale ;
- facture/attestation de fret ;
- assurance ;
- titre de transport (B/L, LTA/AWB, lettre de voiture) ;
- packing list ;
- certificat d'origine ;
- cargo tracking note / BIETC/BESC/ECTN selon contexte ;
- déclaration d'importation/change ;
- DEV / déclaration de valeur ;
- déclaration douanière précédente ;
- inspection/conformité ;
- certificats sanitaires/phytosanitaires ;
- licences/autorisations ;
- exonérations ;
- garanties ;
- autre pièce.

### Graphe documentaire
Un dossier peut contenir 80 documents, 10 factures, plusieurs expéditions et des milliers de lignes. **Ne jamais supposer 1 document = 1 facture.**

Prévoir un `DocumentRelation` / graphe documentaire avec :
- source ;
- cible (`Invoice`, `Shipment`, `GoodsLine`, `Case`) ;
- relation ;
- méthode ;
- confiance ;
- preuves ;
- confirmation humaine éventuelle.

Priorité : référence exacte > concordances structurées > inférence IA > humain si ambigu. Une association incertaine reste à vérifier ou non classée.

## 3. IA invisible et moteurs déterministes

Pas de chatbot générique.

L'IA sert à :
- classifier les documents ;
- extraire les données structurées ;
- détecter/traduire les langues ;
- résoudre les entités ;
- inférer les relations entre pièces ;
- détecter contradictions/anomalies ;
- assister les codes SH absents/incomplets/ambigus/incohérents ;
- orchestrer les outils internes.

Restent **déterministes** :
- existence d'un code dans une édition ;
- taux ;
- bases fiscales ;
- droits/taxes/frais ;
- arrondis ;
- règles de régime ;
- exigences réglementaires ;
- validation finale.

Un LLM peut demander `calculate_duties()`, mais ne calcule pas librement le résultat.

Créer un `AI Gateway` avec adaptateurs fournisseurs. Le domaine métier ne dépend jamais directement d'un SDK OpenAI/Anthropic/Google/Groq. V1 : fournisseur principal + fallback.

Toute sortie IA suit un schéma structuré, est validée serveur, garde sa provenance et peut répondre « information insuffisante ». Une panne IA ne bloque pas l'application : mode manuel obligatoire.

Construire un benchmark ClairTransit : classification, extraction, relations documentaires, codes SH, contradictions, multilingue, latence, coût, faux positifs et taux de revue humaine.

**Les calculs fiscaux doivent être reproductibles à 100 % pour les mêmes entrées et RuleSet.**

## 4. CEMAC et internationalisation

V1 commerciale : transitaires/commissionnaires CEMAC, Gabon comme terrain pilote.

Le modèle doit supporter :
- pays ;
- régime ;
- mode de transport ;
- édition tarifaire ;
- règles nationales ;
- règles documentaires ;
- dates d'effet.

Langues prévues dès maintenant : FR, EN, ES, AR.

Séparer langue interface, langue organisation, langue document/OCR et langue des sorties. Préparer RTL pour l'arabe.

Les libellés officiels du tarif/réglementation restent conservés avec langue, source et version. Une traduction d'affichage ne remplace jamais le texte officiel.

Le code SH de la facture est prioritaire : extraction → normalisation → rapprochement exact → Rule Engine. L'IA intervient seulement si nécessaire.

## 5. Sécurité et confidentialité

Menaces prioritaires : fuite inter-tenant, vol de compte, malware/ransomware dans uploads, secrets/API keys exposés, dépendances vulnérables, accès interne abusif, prompt injection documentaire, fuite vers un fournisseur externe, mauvaise configuration stockage/cloud.

Principes :
- isolation par organisation ;
- MFA à terme ;
- chiffrement transit/repos ;
- secrets backend uniquement ;
- audit append-only ;
- sauvegardes chiffrées et restauration testée ;
- rate limiting ;
- validation MIME/extension/taille/contenu ;
- quarantaine avant traitement.

**Ne pas développer d'antivirus maison.**

V1 recommandée : `Upload → quarantaine → ClamAV auto-hébergé → sain : OCR/IA/stockage métier ; infecté : rejet + alerte + audit`.

Ne jamais envoyer des documents clients vers un service public de scan. Tous les appels IA passent par le backend et transmettent le minimum nécessaire. Le contenu des documents est non fiable et ne peut jamais modifier les règles/outils autorisés.

## 6. Plan d'amélioration

### Phase A — Consolider l'existant
1. Fusionner proprement refonte UI + numérisation.
2. Étendre taxonomie documentaire : fret, assurance, titres de transport.
3. Tests isolation/sécurité.
4. Conserver le mode manuel.

### Phase B — Document Intelligence / relations
1. Extraire ancres : n° facture, PO, B/L, fournisseur, destinataire, dates.
2. Introduire `Shipment` si nécessaire.
3. Relations plusieurs-à-plusieurs.
4. Regroupement déterministe.
5. IA sur ambiguïtés restantes.
6. Écran « associations à vérifier ».

### Phase C — Document Requirements / Rule Engine
1. Socle CEMAC versionné.
2. Règles pays/régime/transport/marchandise.
3. Politique société configurable.
4. Checklist automatique.
5. Calcul provisoire vs final validable.

### Phase D — AI Gateway
1. Interface fournisseur neutre.
2. Structured outputs.
3. Fournisseur principal + fallback.
4. Observabilité coût/latence/erreurs.
5. Benchmark.
6. Mode dégradé.

### Phase E — i18n
1. Infrastructure i18n.
2. Extraire textes codés en dur.
3. FR/EN/ES.
4. AR + RTL.
5. OCR `fra/eng/spa/ara`.
6. Préférences utilisateur et organisation séparées.

### Phase F — Sécurité renforcée
1. Quarantaine.
2. ClamAV.
3. Validation contenu.
4. Rétention/stockage.
5. MFA.
6. Sauvegarde/restauration.
7. Tests sécurité.
8. Défenses contre prompt injection documentaire.

### Phase G — Moteur douanier complet
1. Référentiel CEMAC actuel vérifié.
2. RuleSets datés/sourcés.
3. Valorisation déterministe.
4. Droits/taxes/frais déterministes.
5. DEV/autres documents générables seulement avec spécifications vérifiées.
6. Export systèmes officiels seulement après format confirmé.

### Phase H — Extensions métier
Après validation V1 Transit :
1. grand importateur ;
2. partage importateur ↔ transitaire ;
3. logisticien intégré ;
4. audit/conseil.

## 7. Règle de collaboration

Avant toute modification importante : **lire PR, branches et derniers commits**. Claude et ChatGPT travaillent sur le même produit ; ne jamais travailler à partir d'un état supposé ancien.

État vérifié au 24/10/2026 :
- PR #5 `refonte-interface` : 9 commits, HEAD `ce5fff1e3ef9903c6f54c0f3007a4c94357f26e0`.
- PR #6 `numerisation` : 2 commits, HEAD `c053c2dfdbec25d3d63671a095ec996c6f6e7edf`.

La numérisation actuelle est la première couche du futur moteur documentaire ; regroupement facture/expédition/pièce et relations restent à construire.
