# Étape 7 — Noyau de calcul fiscal traçable

**Statut : moteur arithmétique initial, pas encore calcul légal CEMAC certifié.**

`apps.cases.tax_engine.calculate` réalise des calculs en Decimal, sans taux
inventés et en rejetant les nombres flottants. Chaque règle passée porte un
identifiant de source et une attestation `verified`.

Les chiffres de test (5 %, 10 %, etc.) sont **purement synthétiques** et
ne représentent aucun taux CEMAC applicable.

Les deux bases de calcul couvertes sont `customs_value` et
`customs_value_plus_duties`. Ce sous-ensemble ne couvre ni exemptions,
ni droits spécifiques, ni minimums, ni TVA propre à chaque pays, ni conversion,
ni règles d'origine, ni régimes suspensifs. Il ne doit pas être utilisé pour
déclarer une créance douanière réelle.

**Prochaine intégration requise** : modèles de règles fiscales légalement
vérifiées (pays, régime, code SH, validité, textes sources), workflow de
publication des règles, valeur en douane justifiée, conversion officielle,
instantané immuable du calcul et fingerprint des entrées. Tant que ce
processus n'existe pas, le verrou `validation_readiness` reste actif.

Test : `cd backend && python -m pytest tests/test_tax_engine.py`.
