# Contributing to DECLADO-IA

Merci de votre intérêt pour contribuer à DECLADO-IA ! 🎉

## Code de Conduite

Ce projet adhère à un code de conduite. En participant, vous êtes censé respecter ce code.

## Comment contribuer

### Signaler des bugs

Utilisez les [GitHub Issues](https://github.com/votre-org/declado-ia/issues) avec le template bug.

**Inclure :**
- Description du problème
- Steps pour reproduire
- Comportement attendu vs actuel
- Captures d'écran si applicable
- Version de l'application
- OS et version

### Proposer des fonctionnalités

Utilisez les [GitHub Issues](https://github.com/votre-org/declado-ia/issues) avec le template feature.

**Inclure :**
- Description claire de la fonctionnalité
- Cas d'usage
- Bénéfices attendus
- Maquettes/wireframes si applicable

### Pull Requests

1. **Fork** le projet
2. Créer une **branche feature** (`git checkout -b feature/AmazingFeature`)
3. **Commit** vos changements (`git commit -m 'feat: add some AmazingFeature'`)
4. **Push** vers la branche (`git push origin feature/AmazingFeature`)
5. Ouvrir une **Pull Request**

#### Checklist PR

- [ ] Code formaté (black, prettier)
- [ ] Tests ajoutés/mis à jour
- [ ] Documentation mise à jour
- [ ] Pas de warnings linter
- [ ] Types TypeScript corrects
- [ ] Commit messages suivent Conventional Commits

### Standards de code

#### Python

```bash
# Formatter
black backend/

# Linter
ruff check backend/

# Types
mypy backend/
```

#### TypeScript/React

```bash
# Formatter
npm run format

# Linter
npm run lint

# Types
npm run type-check
```

### Tests

Tous les nouveaux codes doivent inclure des tests.

```bash
# Backend
pytest backend/tests/

# Frontend
npm test
```

### Documentation

Mettre à jour la documentation pertinente dans `docs/` pour tout changement.

## Workflow Git

### Branches

- `main` : Production stable
- `develop` : Développement principal
- `feature/*` : Nouvelles fonctionnalités
- `fix/*` : Corrections de bugs
- `hotfix/*` : Correctifs urgents

### Commits

Utiliser [Conventional Commits](https://www.conventionalcommits.org/) :

```
type(scope): description

[body optionnel]

[footer optionnel]
```

**Types :**
- `feat`: Nouvelle fonctionnalité
- `fix`: Correction bug
- `docs`: Documentation
- `style`: Formatage
- `refactor`: Refactoring
- `test`: Tests
- `chore`: Maintenance

**Exemples :**
```
feat(ocr): add support for TIFF images
fix(tax): correct CIF calculation for FOB+freight
docs(readme): update installation instructions
```

## Questions ?

Contact : dev@declado-ia.com
